"""Three readable views of country-to-country connections (test A / B / C).

One self-contained HTML with three tabs over the signed multi-layer data:
  A. Explorer  - pick a country, see all its connections per layer (coop/conflict).
  B. Network   — interactive labelled graph, filter by layer, click a country to focus.
  C. Matrix    — country x country grid, cell = net stance, filter by layer.

    python examples/build_country_views.py  → reports/geonexus_country_views.html

(The Network tab uses vis-network from a CDN; Explorer and Matrix are pure HTML.)
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from multilayer import CAMEO, LAYERS, net_dyads

OUT_PATH = Path("reports") / "geonexus_country_views.html"


def main() -> None:
    if not CAMEO.exists():
        print(f"{CAMEO} not found — run extract_cameo.py first.")
        return
    net = net_dyads(json.loads(CAMEO.read_text(encoding="utf-8")))

    # data: per layer, list of [a, b, net]; plus per-country total degree for ordering
    dyads: dict[str, list] = {}
    degree: dict[str, int] = defaultdict(int)
    for lay in LAYERS:
        rows = []
        for (a, b), s in net[lay].items():
            rows.append([a, b, s])
            degree[a] += 1
            degree[b] += 1
        dyads[lay] = sorted(rows, key=lambda r: abs(r[2]), reverse=True)
    countries = sorted(degree, key=lambda c: degree[c], reverse=True)

    data = {"layers": LAYERS, "dyads": dyads, "countries": countries}
    page = _TEMPLATE.replace("__DATA__", json.dumps(data))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB) — open in a browser")


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GeoNexus — country connections</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  :root { --bg:#f1f5f9; --panel:#fff; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
    --coop:#16a34a; --conf:#dc2626; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
    font-family:system-ui,-apple-system,sans-serif; }
  header { background:linear-gradient(120deg,#0f172a,#1e3a8a); color:#fff; padding:18px 28px; }
  header h1 { margin:0; font-size:20px; }
  header p { margin:4px 0 0; color:#cbd5e1; font-size:13px; }
  nav { position:sticky; top:0; background:var(--panel); border-bottom:1px solid var(--line);
    padding:0 20px; display:flex; gap:4px; z-index:5; }
  nav button { background:none; border:none; padding:13px 16px; font-size:14px;
    color:var(--muted); cursor:pointer; border-bottom:2px solid transparent; }
  nav button.active { color:#2563eb; border-bottom-color:#2563eb; font-weight:600; }
  main { padding:20px 28px; max-width:1180px; margin:0 auto; }
  .tab { display:none; } .tab.active { display:block; }
  .ctrl { margin-bottom:14px; }
  select, .lay-btn { font-size:14px; padding:6px 12px; border:1px solid var(--line);
    border-radius:8px; background:#fff; cursor:pointer; margin-right:6px; }
  .lay-btn.on { background:#2563eb; color:#fff; border-color:#2563eb; }
  .col2 { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
  .layerbox { background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:12px 14px; margin-bottom:12px; }
  .layerbox h3 { margin:0 0 6px; font-size:14px; text-transform:capitalize; }
  .chip { display:inline-block; padding:2px 9px; margin:2px; border-radius:999px; font-size:13px; }
  .coop { background:#dcfce7; color:#166534; } .conf { background:#fee2e2; color:#991b1b; }
  #net { height:640px; border:1px solid var(--line); border-radius:12px; background:#fff; }
  table { border-collapse:collapse; font-size:11px; }
  th.rot { height:90px; white-space:nowrap; }
  th.rot div { transform:rotate(-60deg); width:18px; }
  td.lab, th.lab { text-align:right; padding:2px 6px; font-size:11px; position:sticky; left:0;
    background:var(--bg); }
  td.cell { width:18px; height:18px; text-align:center; border:1px solid #eef2f6; }
  .muted { color:var(--muted); font-size:13px; }
</style></head>
<body>
<header><h1>GeoNexus — connections between countries</h1>
  <p>Signed multi-layer (CAMEO): green = cooperation, red = conflict. Three ways to read it.</p>
</header>
<nav>
  <button class="active" data-tab="explorer">A · Explorer</button>
  <button data-tab="network">B · Network</button>
  <button data-tab="matrix">C · Matrix</button>
</nav>
<main>
  <section class="tab active" id="explorer">
    <div class="ctrl">Country: <select id="csel"></select></div>
    <div id="exp"></div>
  </section>
  <section class="tab" id="network">
    <div class="ctrl" id="netbtns"></div>
    <p class="muted">Click a country to focus its links. Drag to pan, scroll to zoom.</p>
    <div id="net"></div>
  </section>
  <section class="tab" id="matrix">
    <div class="ctrl" id="matbtns"></div>
    <p class="muted">Top 24 most-connected countries.
      Cell = net stance (green coop / red conflict).</p>
    <div style="overflow:auto" id="mat"></div>
  </section>
</main>
<script>
const D = __DATA__;
const LAYERS = D.layers;
const sign = s => s > 0 ? 'coop' : 'conf';

// ---- tabs ----
document.querySelectorAll('nav button').forEach(b => b.onclick = () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  b.classList.add('active'); document.getElementById(b.dataset.tab).classList.add('active');
  if (b.dataset.tab === 'network') drawNet(curLayer);
});

// ---- A: explorer ----
const csel = document.getElementById('csel');
D.countries.forEach(c => {
  const o = document.createElement('option');
  o.value = o.textContent = c; csel.appendChild(o);
});
function renderExplorer(country) {
  let h = '';
  for (const lay of LAYERS) {
    const coop = [], conf = [];
    for (const [a, b, s] of D.dyads[lay]) {
      const other = a === country ? b : (b === country ? a : null);
      if (!other) continue;
      (s > 0 ? coop : conf).push(`<span class="chip ${sign(s)}">${other} ${s>0?'+':''}${s}</span>`);
    }
    if (coop.length || conf.length)
      h += `<div class="layerbox"><h3>${lay}</h3>${coop.join('')} ${conf.join('')}</div>`;
  }
  document.getElementById('exp').innerHTML = h || '<p class="muted">No connections.</p>';
}
csel.onchange = () => renderExplorer(csel.value);
renderExplorer(D.countries[0]);

// ---- B: network (vis-network) ----
let curLayer = LAYERS[0], netObj = null;
const nb = document.getElementById('netbtns');
LAYERS.forEach((lay, i) => {
  const btn = document.createElement('button');
  btn.className = 'lay-btn' + (i === 0 ? ' on' : ''); btn.textContent = lay;
  btn.onclick = () => {
    document.querySelectorAll('#netbtns .lay-btn').forEach(x => x.classList.remove('on'));
    btn.classList.add('on'); curLayer = lay; drawNet(lay);
  };
  nb.appendChild(btn);
});
function drawNet(lay) {
  if (typeof vis === 'undefined') {
    document.getElementById('net').innerHTML =
      '<p class="muted" style="padding:40px">vis-network failed to load (needs internet).</p>';
    return;
  }
  const ids = new Set(), edges = [];
  for (const [a, b, s] of D.dyads[lay]) {
    ids.add(a); ids.add(b);
    edges.push({ from: a, to: b, color: { color: s > 0 ? '#16a34a' : '#dc2626' },
      width: Math.min(6, 1 + Math.abs(s)), title: `${lay}: ${s>0?'+':''}${s}` });
  }
  const nodes = [...ids].map(c => ({ id: c, label: c }));
  netObj = new vis.Network(document.getElementById('net'),
    { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) },
    { nodes: { shape: 'dot', size: 12, font: { size: 14 } },
      edges: { smooth: false }, interaction: { hover: true },
      physics: { stabilization: true, barnesHut: { springLength: 130 } } });
}

// ---- C: matrix ----
let matLayer = 'all';
const mb = document.getElementById('matbtns');
['all', ...LAYERS].forEach((lay, i) => {
  const btn = document.createElement('button');
  btn.className = 'lay-btn' + (i === 0 ? ' on' : ''); btn.textContent = lay;
  btn.onclick = () => {
    document.querySelectorAll('#matbtns .lay-btn').forEach(x => x.classList.remove('on'));
    btn.classList.add('on'); matLayer = lay; renderMatrix();
  };
  mb.appendChild(btn);
});
function netFor(a, b, lay) {
  let tot = 0;
  const lays = lay === 'all' ? LAYERS : [lay];
  for (const L of lays) for (const [x, y, s] of D.dyads[L])
    if ((x === a && y === b) || (x === b && y === a)) tot += s;
  return tot;
}
function renderMatrix() {
  const cs = D.countries.slice(0, 24);
  let h = '<table><tr><th class="lab"></th>';
  for (const c of cs) h += `<th class="rot"><div>${c}</div></th>`;
  h += '</tr>';
  for (const a of cs) {
    h += `<tr><td class="lab">${a}</td>`;
    for (const b of cs) {
      if (a === b) { h += '<td class="cell" style="background:#f1f5f9"></td>'; continue; }
      const s = netFor(a, b, matLayer);
      let bg = '#fff';
      if (s > 0) bg = `rgba(22,163,74,${Math.min(0.85, 0.25 + s/6)})`;
      else if (s < 0) bg = `rgba(220,38,38,${Math.min(0.85, 0.25 + Math.abs(s)/6)})`;
      h += `<td class="cell" title="${a} vs ${b}: ${s}" style="background:${bg}">${s||''}</td>`;
    }
    h += '</tr>';
  }
  document.getElementById('mat').innerHTML = h + '</table>';
}
renderMatrix();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
