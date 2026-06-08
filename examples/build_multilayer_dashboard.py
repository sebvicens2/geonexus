"""Self-contained dashboard for the multi-layer geopolitical network.

Small-multiples: one signed network per layer (green = cooperation, red = conflict)
plus the hard maritime layer, with the cross-layer divergence, signed-network
factions/balance, and chokepoint disruption tables.

    python examples/build_multilayer_dashboard.py
        → reports/geonexus_multilayer_dashboard.html
"""

from __future__ import annotations

import base64
import html
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_dashboard import stat_card, table
from multilayer import CAMEO, LAYERS, MARITIME, build, net_dyads, signed_analysis


def _panels_b64(net: dict, g) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    for ax, lay in zip(axes.flat, LAYERS, strict=False):
        gl = nx.Graph()
        for (a, b), s in net[lay].items():
            gl.add_edge(a, b, sign=s)
        ax.set_title(f"{lay}  ({gl.number_of_edges()} ties)", fontweight="bold")
        ax.set_axis_off()
        if gl.number_of_edges() == 0:
            continue
        pos = nx.spring_layout(gl, seed=3, k=0.9)
        colors = ["#16a34a" if gl[u][v]["sign"] > 0 else "#dc2626" for u, v in gl.edges()]
        widths = [min(4, 0.6 + abs(gl[u][v]["sign"]) / 2) for u, v in gl.edges()]
        nx.draw_networkx_edges(gl, pos, ax=ax, edge_color=colors, width=widths, alpha=0.8)
        deg = dict(gl.degree())
        nx.draw_networkx_nodes(
            gl, pos, ax=ax, node_color="#1e293b", node_size=[60 + deg[n] * 80 for n in gl.nodes()]
        )
        nx.draw_networkx_labels(
            gl,
            pos,
            ax=ax,
            font_size=7,
            font_color="#0f172a",
            labels={n: n[:14] for n in gl.nodes()},
        )

    # 6th panel: hard maritime layer (chokepoints → dependent countries)
    ax = axes.flat[5]
    ax.set_title("maritime (PortWatch chokepoints)", fontweight="bold")
    ax.set_axis_off()
    gm = nx.Graph()
    cps = [o for o in g.nodes() if o.metadata.get("kind") == "chokepoint"]
    for o in cps:
        for n in g.neighbors(o.node_id, direction="out"):
            gm.add_edge(o.name, g.label(n))
    if gm.number_of_edges():
        pos = nx.spring_layout(gm, seed=5, k=0.6)
        cp_names = {o.name for o in cps}
        ncolor = ["#0369a1" if n in cp_names else "#94a3b8" for n in gm.nodes()]
        nsize = [200 if n in cp_names else 40 for n in gm.nodes()]
        nx.draw_networkx_edges(gm, pos, ax=ax, edge_color="#cbd5e1", width=0.6)
        nx.draw_networkx_nodes(gm, pos, ax=ax, node_color=ncolor, node_size=nsize)
        nx.draw_networkx_labels(
            gm, pos, ax=ax, font_size=6, labels={n: n[:12] for n in gm.nodes() if n in cp_names}
        )
    fig.suptitle(
        "Multi-layer geopolitical network — green = cooperation, red = conflict",
        fontsize=15,
        fontweight="bold",
    )
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def main() -> None:
    if not CAMEO.exists():
        print(f"{CAMEO} not found — run extract_cameo.py + extract_maritime.py first.")
        return
    cameo = json.loads(CAMEO.read_text(encoding="utf-8"))
    maritime = json.loads(MARITIME.read_text(encoding="utf-8")) if MARITIME.exists() else []
    g = build(cameo, maritime)
    net = net_dyads(cameo)
    sa = signed_analysis(net)

    n_cp = sum(1 for o in g.nodes() if o.metadata.get("kind") == "chokepoint")
    panel = _panels_b64(net, g)

    cards = "".join(
        [
            stat_card("Countries", str(len(g) - n_cp)),
            stat_card("Chokepoints", str(n_cp)),
            stat_card("Layers", str(len(LAYERS))),
            stat_card("Structural balance", f"{sa['balance_pct']:.0f}%"),
        ]
    )

    # cross-layer divergence
    by_pair: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for lay in LAYERS:
        for pair, s in net[lay].items():
            by_pair[pair][lay] = s
    div_rows = []
    for pair, layers in by_pair.items():
        signs = [s for s in layers.values() if s != 0]
        if any(s > 0 for s in signs) and any(s < 0 for s in signs):
            cells = " · ".join(
                f'<span style="color:{"#16a34a" if s > 0 else "#dc2626"}">{lay} {s:+d}</span>'
                for lay, s in layers.items()
                if s
            )
            div_rows.append([f"{pair[0]} &ndash; {pair[1]}", cells])
    div_tbl = table(["Dyad", "Layers (signed)"], div_rows)

    # maritime
    cps = sorted(
        (o for o in g.nodes() if o.metadata.get("kind") == "chokepoint"),
        key=lambda o: abs((o.metadata.get("disruption") or {}).get("z_score", 0) or 0),
        reverse=True,
    )
    mar_rows = []
    for o in cps:
        d = o.metadata.get("disruption") or {}
        deps = ", ".join(g.label(n) for n in g.neighbors(o.node_id, direction="out")[:5])
        mar_rows.append(
            [
                o.name,
                o.metadata["commodity"],
                str(d.get("z_score", "?")),
                str(d.get("classification", "?")),
                deps,
            ]
        )
    mar_tbl = table(
        ["Chokepoint", "Commodity", "z-score", "Class", "Dependent countries"], mar_rows
    )

    fa, fb = sa["factions"]
    factions_html = (
        f"<p><b>Bloc A:</b> {html.escape(', '.join(fa[:16]))}</p>"
        f"<p><b>Bloc B:</b> {html.escape(', '.join(fb[:16]))}</p>"
        f'<p class="muted">{sa["balance_pct"]:.0f}% of {sa["n_triads"]} triads balanced. '
        "Blocs are a rough signed-partition heuristic on sparse data — read with caution.</p>"
    )

    page = _TEMPLATE.format(
        cards=cards,
        panel=panel,
        divergence=div_tbl,
        maritime=mar_tbl,
        factions=factions_html,
        n_cp=n_cp,
        n_countries=len(g) - n_cp,
    )
    out = Path("reports") / "geonexus_multilayer_dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB) — open it in a browser")


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GeoNexus — multi-layer geopolitical network</title>
<style>
  :root {{ --bg:#f1f5f9; --panel:#fff; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  header {{ background:linear-gradient(120deg,#0f172a,#334155); color:#fff; padding:22px 32px; }}
  header h1 {{ margin:0; font-size:22px; }}
  header p {{ margin:4px 0 0; color:#cbd5e1; font-size:13px; }}
  .disclaimer {{ background:#fef3c7; color:#92400e; font-size:12.5px;
    padding:9px 32px; border-bottom:1px solid #fde68a; }}
  main {{ padding:24px 32px; max-width:1180px; margin:0 auto; }}
  h2.section {{ font-size:15px; text-transform:uppercase; letter-spacing:.5px;
    color:var(--muted); margin:24px 0 14px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
    gap:14px; margin-bottom:8px; }}
  .card {{ background:var(--panel); border:1px solid var(--line);
    border-radius:12px; padding:18px; }}
  .card-value {{ font-size:24px; font-weight:700; }}
  .card-label {{ color:var(--muted); font-size:13px; margin-top:2px; }}
  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:18px; margin-bottom:20px; }}
  .chart {{ width:100%; border:1px solid var(--line); border-radius:12px; }}
  table.tbl {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
  .tbl th {{ text-align:left; color:var(--muted); font-weight:600; font-size:12px;
    text-transform:uppercase; padding:8px 10px; border-bottom:1px solid var(--line); }}
  .tbl td {{ padding:8px 10px; border-bottom:1px solid var(--line); }}
  .muted {{ color:var(--muted); }}
  footer {{ text-align:center; color:var(--muted); font-size:13px; padding:26px; }}
</style></head>
<body>
<header>
  <h1>GeoNexus — multi-layer geopolitical network</h1>
  <p>{n_countries} countries · {n_cp} chokepoints
    · 5 signed news layers + a hard maritime layer.</p>
</header>
<div class="disclaimer">
  News layers = <b>reported stance</b> (CAMEO, LLM-classified, imperfect). The maritime
  layer = <b>hard IMF-PortWatch data</b>. Green = cooperation, red = conflict.
</div>
<main>
  <div class="grid">{cards}</div>
  <h2 class="section">Layers at a glance</h2>
  <div class="panel"><img class="chart" src="data:image/png;base64,{panel}"/></div>
  <h2 class="section">Cross-layer divergence — partners in one layer, rivals in another</h2>
  <div class="panel">{divergence}</div>
  <h2 class="section">Signed-network factions &amp; balance (military + diplomatic)</h2>
  <div class="panel">{factions}</div>
  <h2 class="section">Hard maritime layer — chokepoints by PortWatch disruption</h2>
  <div class="panel">{maritime}</div>
</main>
<footer>Multi-layer signed network — GeoNexus over World Observer.</footer>
</body></html>
"""


if __name__ == "__main__":
    main()
