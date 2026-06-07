"""Self-contained HTML dashboard for the narrative-evolution analysis.

    python examples/build_narrative_dashboard.py
        → reports/eventgraph_narrative_dashboard.html

Shows how WO's LLM narratives drift over time — momentum chart, dated rising
topics with sparklines, a chronological feed, and per-entity enter/fade/timeline.
Reuses the components from build_dashboard.py. Open in any browser; no server.
"""

from __future__ import annotations

import base64
import html
import io
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json

from build_dashboard import bar, stat_card, table
from narrative_evolution import (
    DATA,
    _spark,
    build_memory,
    rising_topics,
    topics_of,
    world_series,
)

OUT_PATH = Path("reports") / "eventgraph_narrative_dashboard.html"
SPOTLIGHT = (
    "gulf_iran",
    "ukraine_russia",
    "israel_gaza",
    "korean_peninsula",
    "taiwan_strait",
    "Iran",
)


def _chart_b64(series: dict[str, dict[str, int]], days: list[str], topics: list[str]) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 5.5))
    for t in topics:
        ax.plot(days, [series[t][d] for d in days], marker="o", linewidth=1.8, label=t)
    ax.set_ylabel("# narratives carrying the topic")
    ax.set_title("Narrative momentum")
    ax.legend(loc="upper left", fontsize=8)
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def main() -> None:
    entities = json.loads(DATA.read_text(encoding="utf-8"))
    memory = build_memory(entities)
    days = memory.dates()
    first, last = days[0], days[-1]
    by_key = {e["key"]: e for e in entities}
    series = world_series(memory, entities)
    rising = rising_topics(series, days)

    n_topics = len(series)
    cards = "".join(
        [
            stat_card("Entities", str(len(entities))),
            stat_card("Days", f"{len(days)}"),
            stat_card("Topics tracked", str(n_topics)),
            stat_card("Window", f"{first} → {last}"),
        ]
    )

    # momentum chart (top rising)
    chart_topics = [t for t, *_ in rising[:6]] or list(series)[:6]
    chart = (
        f'<img class="chart" src="data:image/png;base64,{_chart_b64(series, days, chart_topics)}"/>'
    )

    # rising table with sparklines
    max_end = max((r[2] for r in rising), default=1)
    rising_rows = [
        [
            html.escape(t),
            fday,
            bar(f"{start} → {end}", 100 * end / max_end, "#16a34a"),
            f'<span class="spark">{"".join(_spark(series[t][d]) for d in days)}</span>',
        ]
        for t, start, end, fday in rising[:20]
    ]
    rising_tbl = table(["Topic", "First seen", "Start → End", "Trajectory"], rising_rows)

    # entering-the-world rollup
    entering: Counter[str] = Counter()
    for e in entities:
        ed = sorted(e["by_day"])
        if len(ed) < 2:
            continue
        a = topics_of(memory, ed[0], e["key"])
        b = topics_of(memory, ed[-1], e["key"])
        for topic in b - a:
            entering[topic] += 1
    max_ent = max(entering.values(), default=1)
    enter_rows = [
        [html.escape(t), bar(str(n), 100 * n / max_ent, "#2563eb")]
        for t, n in entering.most_common(20)
    ]
    enter_tbl = table(["Topic", "# narratives it entered"], enter_rows)

    # chronological feed
    feed = ""
    seen: set[str] = set()
    for d in days:
        new_today = sorted(
            ((by_day[d], t) for t, by_day in series.items() if t not in seen and by_day[d] >= 2),
            reverse=True,
        )
        for _, t in new_today:
            seen.add(t)
        if new_today:
            chips = "".join(
                f'<span class="chip2">{html.escape(t)} ({n})</span>' for n, t in new_today[:8]
            )
            feed += f'<div class="feed-row"><span class="feed-day">{d}</span>{chips}</div>'

    # per-entity cards (entered / faded / core + entry timeline)
    ent_cards = ""
    for key in [k for k in SPOTLIGHT if k in by_key]:
        a = topics_of(memory, first, key)
        b = topics_of(memory, last, key)
        entry_day: dict[str, str] = {}
        for d in days:
            for topic in topics_of(memory, d, key):
                entry_day.setdefault(topic, d)
        timeline = "".join(
            f"<li><b>{d}</b> + {html.escape(t)}</li>"
            for t, d in sorted(entry_day.items(), key=lambda kv: kv[1])
            if d != first
        )
        entered_s = html.escape(", ".join(sorted(b - a)[:10]) or "—")
        faded_s = html.escape(", ".join(sorted(a - b)[:8]) or "—")
        core_s = html.escape(", ".join(sorted(a & b)[:8]) or "—")
        ent_cards += f"""
        <div class="ent">
          <h3>{html.escape(key)}</h3>
          <p><span class="lbl in">entered</span> {entered_s}</p>
          <p><span class="lbl out">faded</span> {faded_s}</p>
          <p><span class="lbl core">core</span> {core_s}</p>
          <details><summary>entry timeline</summary><ul class="tl">{timeline}</ul></details>
        </div>"""

    page = _TEMPLATE.format(
        cards=cards,
        chart=chart,
        rising=rising_tbl,
        entering=enter_tbl,
        feed=feed,
        entities=ent_cards,
        first=first,
        last=last,
        n_entities=len(entities),
        n_days=len(days),
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB) — open it in a browser")


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EventGraph — narrative evolution</title>
<style>
  :root {{ --bg:#f1f5f9; --panel:#fff; --ink:#0f172a; --muted:#64748b;
    --line:#e2e8f0; --accent:#2563eb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  header {{ background:linear-gradient(120deg,#0f172a,#155e75); color:#fff; padding:22px 32px; }}
  header h1 {{ margin:0; font-size:22px; }}
  header p {{ margin:4px 0 0; color:#cbd5e1; font-size:13px; }}
  .badge {{ display:inline-block; margin-top:8px; background:rgba(255,255,255,.12);
    padding:3px 10px; border-radius:999px; font-size:12px; }}
  .disclaimer {{ background:#ecfeff; color:#155e75; font-size:12.5px;
    padding:9px 32px; border-bottom:1px solid #cffafe; }}
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
    gap:14px; margin-bottom:22px; }}
  .card {{ background:var(--panel); border:1px solid var(--line);
    border-radius:12px; padding:18px; }}
  .card-value {{ font-size:22px; font-weight:700; }}
  .card-label {{ color:var(--muted); font-size:13px; margin-top:2px; }}
  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:18px; margin-bottom:20px; }}
  .chart {{ width:100%; border:1px solid var(--line); border-radius:12px; background:#fff; }}
  table.tbl {{ width:100%; border-collapse:collapse; font-size:14px; }}
  .tbl th {{ text-align:left; color:var(--muted); font-weight:600; font-size:12px;
    text-transform:uppercase; padding:8px 10px; border-bottom:1px solid var(--line); }}
  .tbl td {{ padding:8px 10px; border-bottom:1px solid var(--line); }}
  .bar {{ position:relative; background:#f1f5f9; border-radius:6px; height:20px; min-width:120px; }}
  .bar-fill {{ position:absolute; left:0; top:0; bottom:0; border-radius:6px; opacity:.25; }}
  .bar-text {{ position:relative; padding-left:8px; line-height:20px;
    font-variant-numeric:tabular-nums; font-size:13px; }}
  .spark {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:15px;
    letter-spacing:1px; color:#0f766e; }}
  .feed-row {{ padding:8px 0; border-bottom:1px solid var(--line); }}
  .feed-day {{ display:inline-block; width:96px; font-weight:600;
    font-variant-numeric:tabular-nums; color:#334155; }}
  .chip2 {{ display:inline-block; background:#ecfeff; color:#155e75; border:1px solid #cffafe;
    border-radius:6px; padding:2px 8px; margin:2px; font-size:12.5px; }}
  .ents {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); gap:16px; }}
  .ent {{ background:var(--panel); border:1px solid var(--line);
    border-radius:12px; padding:16px; }}
  .ent h3 {{ margin:0 0 8px; font-size:15px; }}
  .ent p {{ margin:5px 0; font-size:13px; }}
  .lbl {{ display:inline-block; min-width:62px; font-size:11px; text-transform:uppercase;
    padding:1px 6px; border-radius:5px; margin-right:6px; }}
  .lbl.in {{ background:#dcfce7; color:#166534; }}
  .lbl.out {{ background:#fee2e2; color:#991b1b; }}
  .lbl.core {{ background:#e2e8f0; color:#334155; }}
  .tl {{ font-size:12.5px; color:#334155; margin:8px 0 0; padding-left:18px; }}
  details summary {{ cursor:pointer; color:var(--accent); font-size:13px; margin-top:6px; }}
  footer {{ text-align:center; color:var(--muted); font-size:13px; padding:26px; }}
</style></head>
<body>
<header>
  <h1>EventGraph — narrative evolution</h1>
  <p>How World Observer's LLM syntheses drift over time: what enters, fades and persists.</p>
  <span class="badge">{n_entities} entities · {n_days} days · {first} → {last} · no LLM</span>
</header>
<div class="disclaimer">
  Topics are extracted deterministically from WO's summary bullets (no LLM).
  EventGraph stores one graph per day in an EventMemory and diffs the daily topic sets.
</div>
<nav>
  <button class="active" data-tab="momentum">Momentum</button>
  <button data-tab="rising">Rising topics</button>
  <button data-tab="feed">Chronological feed</button>
  <button data-tab="entities">Per entity</button>
</nav>
<main>
  <section class="tab active" id="momentum">
    <h2 class="section">Overview</h2>
    <div class="grid">{cards}</div>
    <div class="panel">{chart}</div>
    <h2 class="section">Entering the world narrative</h2>
    <div class="panel">{entering}</div>
  </section>
  <section class="tab" id="rising">
    <h2 class="section">Rising topics — dated, with trajectory sparkline</h2>
    <div class="panel">{rising}</div>
  </section>
  <section class="tab" id="feed">
    <h2 class="section">Chronological feed — topics first reaching 2+ narratives</h2>
    <div class="panel">{feed}</div>
  </section>
  <section class="tab" id="entities">
    <h2 class="section">Per entity — entered / faded / core + entry timeline</h2>
    <div class="ents">{entities}</div>
  </section>
</main>
<footer>What enters the world's narrative, and when — diffed from WO's LLM syntheses.</footer>
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
