"""Self-contained HTML dashboard over World Observer's synthesis layer.

    python examples/build_synthesis_dashboard.py
        → reports/geonexus_synthesis_dashboard.html

Reuses the reusable HTML components from ``build_dashboard.py`` (stat_card, table,
bar, the inlined pyvis network) — but ranked by World Observer's *own* instability
and attention scores, with GeoNexus adding the relational layer (co-occurrence
network, blocs, connectivity). Open in any browser; no server.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_dashboard import PALETTE, _backbone, _network_iframe, bar, stat_card, table
from world_observer_synthesis import attention_momentum, build, kind, load

OUT_PATH = Path("reports") / "geonexus_synthesis_dashboard.html"


def _bloc_card(color: str, mean_inst: float, members: list[str]) -> str:
    body = html.escape(", ".join(members[:8]))
    return (
        f'<div class="cluster" style="border-top:3px solid {color}">'
        f'<div class="cluster-head"><span class="dot" style="background:{color}"></span>'
        f"<h3>mean instability {mean_inst:.0f}</h3></div>"
        f'<div class="cluster-sub">{body}</div></div>'
    )


def main() -> None:
    data = load()
    g = build(data)
    by_name = {c["name"]: c for c in data["countries"]}
    countries = [o for o in g.nodes() if kind(g, o.node_id) == "country"]
    theatres = [o for o in g.nodes() if kind(g, o.node_id) == "theatre"]
    degree = g.centrality("degree")

    n_war = sum(1 for c in data["countries"] if c["classification"] == "war")
    cards = "".join(
        [
            stat_card("Countries", str(len(countries))),
            stat_card("Theatres", str(len(theatres))),
            stat_card("Relations", str(g.raw.number_of_edges())),
            stat_card("Co-occurrence edges", str(len(data["cooccurrence"]))),
            stat_card("Countries at war", str(n_war)),
        ]
    )

    # instability table (WO score, bar, classification, driver)
    top_inst = sorted(
        (c for c in data["countries"] if c["instability"] is not None),
        key=lambda c: c["instability"],
        reverse=True,
    )[:12]
    inst_rows = [
        [
            c["name"],
            bar(f"{c['instability']:.0f}", c["instability"], "#dc2626"),
            f'<span class="tag">{html.escape(c["classification"] or "")}</span>',
            html.escape((c["drivers"][0] if c["drivers"] else (c["dominant_signal"] or ""))[:60]),
        ]
        for c in top_inst
    ]
    inst_tbl = table(["Country", "Instability (WO)", "Class", "Top driver"], inst_rows)

    # most-connected (GeoNexus's relational add)
    conn_rows = [
        [
            g.label(o.node_id),
            bar(f"{degree[o.node_id]:.3f}", 100 * degree[o.node_id] / max(degree.values())),
        ]
        for o in sorted(countries, key=lambda o: degree[o.node_id], reverse=True)[:12]
    ]
    conn_tbl = table(["Country", "Co-occurrence degree"], conn_rows)

    # theatres by attention
    top_att = sorted(
        (t for t in data["theatres"] if t["attention_share"] is not None),
        key=lambda t: t["attention_share"],
        reverse=True,
    )[:12]
    att_rows = [
        [t["name"], bar(f"{t['attention_share']:.2f}", 100 * t["attention_share"], "#2563eb")]
        for t in top_att
    ]
    att_tbl = table(["Theatre", "Attention share (WO)"], att_rows)

    # blocs (co-occurrence communities by mean WO instability)
    blocs = []
    for cluster in g.emerging_clusters(min_size=3):
        members = [n for n in cluster if kind(g, n) == "country"]
        insts = [
            by_name[n.split(":", 1)[1]]["instability"]
            for n in members
            if by_name.get(n.split(":", 1)[1], {}).get("instability") is not None
        ]
        if not insts:
            continue
        members.sort(key=lambda n: by_name[n.split(":", 1)[1]]["instability"] or 0, reverse=True)
        blocs.append((sum(insts) / len(insts), [g.label(n) for n in members]))
    blocs.sort(reverse=True)
    blocs_html = "".join(
        _bloc_card(PALETTE[i % len(PALETTE)], m, members)
        for i, (m, members) in enumerate(blocs[:8])
    )

    # narratives (verbatim WO summaries)
    narr_html = ""
    for t in top_att[:5]:
        if t["summary"]:
            lines = "".join(
                f"<li>{html.escape(ln.strip().lstrip('-').strip())}</li>"
                for ln in t["summary"].splitlines()[:4]
                if ln.strip()
            )
            narr_html += (
                f'<div class="asset-block"><h3>{html.escape(t["name"])}</h3><ul>{lines}</ul></div>'
            )

    # attention momentum
    mom = attention_momentum(data["attention_series"]["theatre"])
    mom_rows = []
    for key, f, last, d in [m for m in mom if abs(m[3]) > 0.02][:12]:
        arrow = "▲" if d > 0 else "▼"
        color = "#16a34a" if d > 0 else "#dc2626"
        mom_rows.append(
            [
                f"{arrow} {html.escape(key)}",
                f"{f:.2f}",
                f"{last:.2f}",
                f'<span style="color:{color}">{d:+.2f}</span>',
            ]
        )
    mom_tbl = table(["Theatre", "First", "Last", "Δ (7d)"], mom_rows)

    # network coloured by bloc
    keep, cluster_of, names = _backbone(g)
    network = _network_iframe(g, keep, cluster_of)
    legend = "".join(
        f'<span class="leg"><span class="dot" style="background:{PALETTE[i % len(PALETTE)]}">'
        f"</span>{html.escape(n)}</span>"
        for i, n in enumerate(names)
    )

    page = _TEMPLATE.format(
        cards=cards,
        inst=inst_tbl,
        conn=conn_tbl,
        att=att_tbl,
        blocs=blocs_html,
        narratives=narr_html,
        momentum=mom_tbl,
        network=network,
        legend=legend,
        n_countries=len(countries),
        n_theatres=len(theatres),
        n_war=n_war,
        n_edges=g.raw.number_of_edges(),
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB) — open it in a browser")


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GeoNexus — World Observer synthesis</title>
<style>
  :root {{ --bg:#f1f5f9; --panel:#fff; --ink:#0f172a; --muted:#64748b;
    --line:#e2e8f0; --accent:#2563eb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  header {{ background:linear-gradient(120deg,#0f172a,#7f1d1d); color:#fff; padding:22px 32px; }}
  header h1 {{ margin:0; font-size:22px; }}
  header p {{ margin:4px 0 0; color:#cbd5e1; font-size:13px; }}
  .badge {{ display:inline-block; margin-top:8px; background:rgba(255,255,255,.12);
    padding:3px 10px; border-radius:999px; font-size:12px; }}
  .disclaimer {{ background:#dbeafe; color:#1e40af; font-size:12.5px;
    padding:9px 32px; border-bottom:1px solid #bfdbfe; }}
  nav {{ position:sticky; top:0; z-index:5; background:var(--panel);
    border-bottom:1px solid var(--line); padding:0 24px; display:flex; gap:4px; flex-wrap:wrap; }}
  nav button {{ background:none; border:none; padding:14px 16px; font-size:14px;
    color:var(--muted); cursor:pointer; border-bottom:2px solid transparent; }}
  nav button.active {{ color:var(--accent); border-bottom-color:var(--accent); font-weight:600; }}
  main {{ padding:24px 32px; max-width:1180px; margin:0 auto; }}
  .tab {{ display:none; }} .tab.active {{ display:block; }}
  h2.section {{ font-size:15px; text-transform:uppercase; letter-spacing:.5px;
    color:var(--muted); margin:0 0 14px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
    gap:14px; margin-bottom:26px; }}
  .card {{ background:var(--panel); border:1px solid var(--line);
    border-radius:12px; padding:18px; }}
  .card-value {{ font-size:26px; font-weight:700; }}
  .card-label {{ color:var(--muted); font-size:13px; margin-top:2px; }}
  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:18px; margin-bottom:20px; }}
  .twocol {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
  @media (max-width:820px) {{ .twocol {{ grid-template-columns:1fr; }} }}
  table.tbl {{ width:100%; border-collapse:collapse; font-size:14px; }}
  .tbl th {{ text-align:left; color:var(--muted); font-weight:600; font-size:12px;
    text-transform:uppercase; padding:8px 10px; border-bottom:1px solid var(--line); }}
  .tbl td {{ padding:8px 10px; border-bottom:1px solid var(--line); }}
  .tag {{ background:#fee2e2; color:#991b1b; font-size:12px; padding:2px 8px; border-radius:6px; }}
  .bar {{ position:relative; background:#f1f5f9; border-radius:6px; height:20px; min-width:120px; }}
  .bar-fill {{ position:absolute; left:0; top:0; bottom:0; border-radius:6px; opacity:.25; }}
  .bar-text {{ position:relative; padding-left:8px; line-height:20px;
    font-variant-numeric:tabular-nums; font-size:13px; }}
  .clusters {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
  .cluster {{ background:var(--panel); border:1px solid var(--line);
    border-radius:12px; padding:16px; }}
  .cluster-head {{ display:flex; align-items:center; gap:8px; }}
  .cluster-head h3 {{ margin:0; font-size:15px; }}
  .cluster-sub {{ font-size:13px; margin-top:6px; color:#334155; }}
  .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
  .network-frame {{ width:100%; height:580px; border:1px solid var(--line);
    border-radius:12px; background:#fff; }}
  .network-img {{ width:100%; border:1px solid var(--line); border-radius:12px; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin:12px 0; font-size:13px; }}
  .leg {{ display:flex; align-items:center; gap:6px; color:#334155; }}
  .asset-block {{ margin-bottom:16px; }}
  .asset-block h3 {{ font-size:14px; margin:0 0 6px; }}
  .asset-block ul {{ margin:0; padding-left:18px; font-size:13px; color:#334155; }}
  footer {{ text-align:center; color:var(--muted); font-size:13px; padding:26px; }}
  footer b {{ color:var(--ink); }}
</style></head>
<body>
<header>
  <h1>GeoNexus — World Observer synthesis</h1>
  <p>Ranked by World Observer's own instability &amp; attention;
    GeoNexus adds the relational layer.</p>
  <span class="badge">{n_countries} countries · {n_theatres} theatres
    · {n_edges} relations · {n_war} at war</span>
</header>
<div class="disclaimer">
  <b>Instability, attention and narratives are World Observer's own outputs.</b>
  GeoNexus contributes the relational layer: the country co-occurrence graph,
  the blocs (communities) and the connectivity ranking.
</div>
<nav>
  <button class="active" data-tab="overview">Overview</button>
  <button data-tab="network">Network</button>
  <button data-tab="blocs">Blocs</button>
  <button data-tab="theatres">Theatres</button>
  <button data-tab="momentum">Momentum</button>
  <button data-tab="narratives">Narratives</button>
</nav>
<main>
  <section class="tab active" id="overview">
    <h2 class="section">Overview</h2>
    <div class="grid">{cards}</div>
    <div class="twocol">
      <div><h2 class="section">Most unstable (WO score)</h2><div class="panel">{inst}</div></div>
      <div><h2 class="section">Most connected (GeoNexus)</h2><div class="panel">{conn}</div></div>
    </div>
  </section>
  <section class="tab" id="network">
    <h2 class="section">Country co-occurrence network — coloured by bloc</h2>
    <div class="legend">{legend}</div>
    {network}
  </section>
  <section class="tab" id="blocs">
    <h2 class="section">Blocs — co-occurrence communities, by mean WO instability</h2>
    <div class="clusters">{blocs}</div>
  </section>
  <section class="tab" id="theatres">
    <h2 class="section">Theatres by attention share (WO)</h2>
    <div class="panel">{att}</div>
  </section>
  <section class="tab" id="momentum">
    <h2 class="section">Attention momentum — WO daily share, 7-day change</h2>
    <div class="panel">{momentum}</div>
  </section>
  <section class="tab" id="narratives">
    <h2 class="section">Narratives — World Observer LLM synthesis (verbatim)</h2>
    <div class="panel">{narratives}</div>
  </section>
</main>
<footer>
  <b>GeoNexus</b> layered a {n_edges}-edge relational graph over World Observer's
  synthesis of <b>{n_countries}</b> countries and <b>{n_theatres}</b> theatres.
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


if __name__ == "__main__":
    main()
