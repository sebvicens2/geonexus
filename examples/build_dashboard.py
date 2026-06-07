"""Build a self-contained HTML dashboard from the World Observer results.

    python examples/build_dashboard.py   →   reports/eventgraph_dashboard.html

Open the file in any browser — no server, no app, no runtime dependency. The
interactive network is a pyvis graph inlined into the page (works offline); if
pyvis is not installed it falls back to a static PNG.

This is a *prototype of a future World Observer tab*: the layout, sections and
small HTML "components" below are meant to be lifted into WO later. No LLM —
every figure is computed by EventGraph from real events.
"""

from __future__ import annotations

import base64
import html
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from results_report import ASSETS, add_asset_overlay, causal_paths, collect
from world_observer_common import build_graph, load_events

from eventgraph import EventGraph

OUT_PATH = Path("reports") / "eventgraph_dashboard.html"
PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]


# --------------------------------------------------------------------------- #
# network (interactive pyvis, inlined; PNG fallback)
# --------------------------------------------------------------------------- #
def _backbone(g: EventGraph, n_clusters: int = 4) -> tuple[set[str], dict[str, int], list[str]]:
    clusters = [c for c in g.emerging_clusters(min_size=5) if len(c) >= 20][:n_clusters]
    keep: set[str] = set()
    cluster_of: dict[str, int] = {}
    names: list[str] = []
    for idx, cluster in enumerate(clusters):
        entities = sorted(
            (n for n in cluster if not n.startswith("event:")),
            key=g.influence_score,
            reverse=True,
        )
        events = sorted(
            (n for n in cluster if n.startswith("event:")),
            key=lambda n: g.get(n).severity,
            reverse=True,  # type: ignore[union-attr]
        )
        chosen = entities[:8] + events[:5]
        for n in chosen:
            keep.add(n)
            cluster_of[n] = idx
        names.append(" / ".join(g.label(n) for n in entities[:3]))
    return keep, cluster_of, names


def _network_iframe(g: EventGraph, keep: set[str], cluster_of: dict[str, int]) -> str:
    try:
        from pyvis.network import Network
    except ModuleNotFoundError:
        return _network_png(g, keep, cluster_of)

    net = Network(
        height="560px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#1e293b",
        cdn_resources="in_line",
        directed=True,
    )
    net.barnes_hut(gravity=-12000, spring_length=120)
    for nid in keep:
        is_event = nid.startswith("event:")
        net.add_node(
            nid,
            label="" if is_event else g.label(nid)[:24],
            title=g.label(nid),
            color=PALETTE[cluster_of.get(nid, 0) % len(PALETTE)],
            size=10 if is_event else 26,
        )
    for u, v, _ in g.raw.edges(data=True):
        if u in keep and v in keep:
            net.add_edge(u, v, color="#cbd5e1")
    inner = net.generate_html()
    return (
        f'<iframe class="network-frame" srcdoc="{html.escape(inner, quote=True)}" '
        f'title="EventGraph network"></iframe>'
    )


def _network_png(g: EventGraph, keep: set[str], cluster_of: dict[str, int]) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx

    sub = g.raw.subgraph(keep)
    pos = nx.spring_layout(sub, seed=11, k=0.6)
    colors = [PALETTE[cluster_of.get(n, 0) % len(PALETTE)] for n in sub.nodes]
    sizes = [260 if n.startswith("event:") else 900 for n in sub.nodes]
    labels = {n: g.label(n)[:20] for n in sub.nodes if not n.startswith("event:")}
    fig, ax = plt.subplots(figsize=(13, 8))
    nx.draw_networkx_edges(sub, pos, ax=ax, edge_color="#cbd5e1", width=0.8)
    nx.draw_networkx_nodes(sub, pos, ax=ax, node_color=colors, node_size=sizes, alpha=0.9)
    nx.draw_networkx_labels(sub, pos, labels=labels, font_size=8, ax=ax)
    ax.set_axis_off()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f'<img class="network-img" src="data:image/png;base64,{data}" alt="network"/>'


# --------------------------------------------------------------------------- #
# reusable HTML components
# --------------------------------------------------------------------------- #
def stat_card(label: str, value: str) -> str:
    return (
        f'<div class="card"><div class="card-value">{value}</div>'
        f'<div class="card-label">{html.escape(label)}</div></div>'
    )


def bar(value: float, pct: float, accent: str = "#2563eb") -> str:
    pct = max(0.0, min(100.0, pct))
    return (
        f'<div class="bar"><div class="bar-fill" style="width:{pct:.0f}%;'
        f'background:{accent}"></div><span class="bar-text">{value}</span></div>'
    )


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="tbl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def cluster_card(idx: int, c: dict[str, object], accent: str) -> str:
    nodes = ", ".join(html.escape(n) for n in c["entities"])  # type: ignore[arg-type]
    events = "".join(
        f"<li>{html.escape(str(e))}</li>"
        for e in c["events"]  # type: ignore[union-attr]
    )
    return f"""
    <div class="cluster" style="border-top:3px solid {accent}">
      <div class="cluster-head"><span class="dot" style="background:{accent}"></span>
        <h3>{html.escape(str(c["name"]))}</h3></div>
      <div class="cluster-meta">{c["size"]} nodes · {c["n_events"]} events</div>
      <div class="cluster-sub">Main: {nodes}</div>
      <ul class="cluster-events">{events}</ul>
      <p class="cluster-interp">{html.escape(str(c["interpretation"]))}</p>
    </div>"""


def path_block(ticker: str, name: str, paths: list[list[str]]) -> str:
    if not paths:
        items = '<div class="muted">no chains</div>'
    else:
        items = "".join(
            f'<div class="path"><span class="chip">{score}</span>'
            f'<span class="chain">{html.escape(chain)}</span></div>'
            for chain, score in paths
        )
    return (
        f'<div class="asset-block"><h3>{html.escape(ticker)} '
        f'<span class="muted">{html.escape(name)}</span></h3>{items}</div>'
    )


# --------------------------------------------------------------------------- #
# page assembly
# --------------------------------------------------------------------------- #
def render(
    data: dict[str, object],
    paths: dict[str, list[list[str]]],
    network: str,
    cluster_names: list[str],
) -> str:
    ov = data["overview"]  # type: ignore[index]

    cards = "".join(
        [
            stat_card("Events", str(ov["events"])),
            stat_card("Actors", str(ov["actors"])),
            stat_card("Regions / theatres", str(ov["regions"])),
            stat_card("Categories", str(ov["categories"])),
            stat_card("Relations", str(ov["relations"])),
            stat_card("Graph density", f"{ov['density']:.4f}"),
        ]
    )

    max_inf = max((r[3] for r in data["influence"]), default=1.0)  # type: ignore[index]
    inf_rows = [
        [
            str(i),
            html.escape(label),
            f'<span class="tag">{typ}</span>',
            bar(f"{score:.1f}", 100 * score / max_inf),
        ]
        for i, (_, label, typ, score) in enumerate(data["influence"], 1)  # type: ignore[index]
    ]
    influence_tbl = table(["#", "Node", "Type", "Influence"], inf_rows)

    hot_rows = [
        [
            str(i),
            html.escape(label),
            f'<span class="tag">{typ}</span>',
            bar(f"{s.score:.3f}", 100 * s.score, "#dc2626"),
            f"{s.centrality:.2f}",
            f"{s.influence:.2f}",
            f"{s.density:.2f}",
        ]
        for i, (_, label, typ, s) in enumerate(data["hotspots"], 1)  # type: ignore[index]
    ]
    hotspots_tbl = table(["#", "Node", "Type", "Risk", "Cen", "Inf", "Den"], hot_rows)

    clusters_html = "".join(
        cluster_card(i, c, PALETTE[i % len(PALETTE)])
        for i, c in enumerate(data["clusters"])  # type: ignore[index]
    )

    legend = "".join(
        f'<span class="leg"><span class="dot" style="background:{PALETTE[i % len(PALETTE)]}">'
        f"</span>{html.escape(n)}</span>"
        for i, n in enumerate(cluster_names)
    )

    paths_html = "".join(path_block(t, ASSETS[t][0], paths[t]) for t in ASSETS)

    n_major = len(data["clusters"])  # type: ignore[arg-type]
    total = data["total_clusters"]
    n_hot = len(data["hotspots"])  # type: ignore[arg-type]
    n_events = ov["events"]

    return _TEMPLATE.format(
        cards=cards,
        influence=influence_tbl,
        network=network,
        legend=legend,
        clusters=clusters_html,
        hotspots=hotspots_tbl,
        paths=paths_html,
        n_major=n_major,
        total=total,
        n_hot=n_hot,
        n_events=n_events,
    )


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EventGraph — World Observer dashboard</title>
<style>
  :root {{ --bg:#f1f5f9; --panel:#fff; --ink:#0f172a; --muted:#64748b;
    --line:#e2e8f0; --accent:#2563eb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  header {{ background:linear-gradient(120deg,#0f172a,#1e3a8a); color:#fff;
    padding:22px 32px; }}
  header h1 {{ margin:0; font-size:22px; letter-spacing:.3px; }}
  header p {{ margin:4px 0 0; color:#cbd5e1; font-size:13px; }}
  .badge {{ display:inline-block; margin-top:8px; background:rgba(255,255,255,.12);
    padding:3px 10px; border-radius:999px; font-size:12px; }}
  nav {{ position:sticky; top:0; z-index:5; background:var(--panel);
    border-bottom:1px solid var(--line); padding:0 24px; display:flex; gap:4px; }}
  nav button {{ background:none; border:none; padding:14px 16px; font-size:14px;
    color:var(--muted); cursor:pointer; border-bottom:2px solid transparent; }}
  nav button.active {{ color:var(--accent); border-bottom-color:var(--accent);
    font-weight:600; }}
  main {{ padding:24px 32px; max-width:1180px; margin:0 auto; }}
  .tab {{ display:none; }} .tab.active {{ display:block; }}
  h2.section {{ font-size:15px; text-transform:uppercase; letter-spacing:.5px;
    color:var(--muted); margin:0 0 14px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
    gap:14px; margin-bottom:26px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:18px; }}
  .card-value {{ font-size:26px; font-weight:700; }}
  .card-label {{ color:var(--muted); font-size:13px; margin-top:2px; }}
  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:18px; margin-bottom:20px; }}
  table.tbl {{ width:100%; border-collapse:collapse; font-size:14px; }}
  .tbl th {{ text-align:left; color:var(--muted); font-weight:600; font-size:12px;
    text-transform:uppercase; padding:8px 10px; border-bottom:1px solid var(--line); }}
  .tbl td {{ padding:8px 10px; border-bottom:1px solid var(--line); }}
  .tag {{ background:#eef2ff; color:#4338ca; font-size:12px; padding:2px 8px;
    border-radius:6px; }}
  .bar {{ position:relative; background:#f1f5f9; border-radius:6px; height:20px;
    min-width:120px; }}
  .bar-fill {{ position:absolute; left:0; top:0; bottom:0; border-radius:6px;
    opacity:.25; }}
  .bar-text {{ position:relative; padding-left:8px; line-height:20px;
    font-variant-numeric:tabular-nums; font-size:13px; }}
  .clusters {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
    gap:16px; }}
  .cluster {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:16px; }}
  .cluster-head {{ display:flex; align-items:center; gap:8px; }}
  .cluster-head h3 {{ margin:0; font-size:15px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
  .cluster-meta {{ color:var(--muted); font-size:13px; margin:6px 0; }}
  .cluster-sub {{ font-size:13px; margin-bottom:6px; }}
  .cluster-events {{ margin:6px 0; padding-left:18px; font-size:12px; color:#334155; }}
  .cluster-interp {{ font-size:13px; color:#475569; font-style:italic; margin:8px 0 0; }}
  .network-frame {{ width:100%; height:580px; border:1px solid var(--line);
    border-radius:12px; background:#fff; }}
  .network-img {{ width:100%; border:1px solid var(--line); border-radius:12px; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin:12px 0; font-size:13px; }}
  .leg {{ display:flex; align-items:center; gap:6px; color:#334155; }}
  .asset-block {{ margin-bottom:18px; }}
  .asset-block h3 {{ font-size:15px; margin:0 0 8px; }}
  .path {{ display:flex; align-items:center; gap:10px; padding:6px 0;
    border-bottom:1px dashed var(--line); font-size:13px; }}
  .chip {{ background:#0f172a; color:#fff; font-size:12px; padding:2px 8px;
    border-radius:6px; font-variant-numeric:tabular-nums; }}
  .chain {{ color:#334155; }}
  .muted {{ color:var(--muted); font-weight:400; }}
  footer {{ text-align:center; color:var(--muted); font-size:13px; padding:26px; }}
  footer b {{ color:var(--ink); }}
</style></head>
<body>
<header>
  <h1>EventGraph — World Observer</h1>
  <p>Causal graph intelligence over a real geopolitical event feed.</p>
  <span class="badge">{n_events} real events · {n_hot} hotspots
    · {n_major} major clusters · no LLM</span>
</header>
<nav>
  <button class="active" data-tab="overview">Overview</button>
  <button data-tab="network">Network</button>
  <button data-tab="clusters">Clusters</button>
  <button data-tab="hotspots">Hotspots</button>
  <button data-tab="paths">Causal paths</button>
</nav>
<main>
  <section class="tab active" id="overview">
    <h2 class="section">Overview</h2>
    <div class="grid">{cards}</div>
    <h2 class="section">Top 10 by influence</h2>
    <div class="panel">{influence}</div>
  </section>
  <section class="tab" id="network">
    <h2 class="section">Network — top clusters backbone</h2>
    <div class="legend">{legend}</div>
    {network}
  </section>
  <section class="tab" id="clusters">
    <h2 class="section">Emerging clusters</h2>
    <div class="clusters">{clusters}</div>
  </section>
  <section class="tab" id="hotspots">
    <h2 class="section">Top 10 risk hotspots</h2>
    <div class="panel">{hotspots}</div>
  </section>
  <section class="tab" id="paths">
    <h2 class="section">Causal paths to assets
      <span class="muted">(heuristic asset overlay)</span></h2>
    <div class="panel">{paths}</div>
  </section>
</main>
<footer>
  <b>EventGraph</b> detected <b>{n_major}</b> major geopolitical clusters
  (of {total} communities) and <b>{n_hot}</b> risk hotspots
  from <b>{n_events}</b> real World Observer events.
</footer>
<script>
  document.querySelectorAll('nav button').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      document.querySelectorAll('nav button').forEach(function(b) {{
        b.classList.remove('active'); }});
      document.querySelectorAll('.tab').forEach(function(t) {{
        t.classList.remove('active'); }});
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
    }});
  }});
</script>
</body></html>
"""


def main() -> None:
    g = build_graph(load_events())
    data = collect(g)
    keep, cluster_of, cluster_names = _backbone(g)
    network = _network_iframe(g, keep, cluster_of)

    add_asset_overlay(g)
    paths = causal_paths(g)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(data, paths, network, cluster_names), encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size // 1024
    print(f"wrote {OUT_PATH} ({size_kb} KB) — open it in a browser")


if __name__ == "__main__":
    main()
