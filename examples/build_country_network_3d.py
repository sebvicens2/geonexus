"""Interactive 3D country network — fly through it, with labels and layer filter.

The readable Network view, in navigable 3D: one force-directed cloud of countries,
labelled, edges green (cooperation) / red (conflict). Filter by layer, click a
country to fly to it and focus its links. WebGL via 3d-force-graph + spritetext.

    python examples/build_country_network_3d.py
        → reports/eventgraph_country_network_3d.html

Opens in any browser (loads the libs from a CDN, so needs internet + WebGL).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from multilayer import CAMEO, LAYERS, net_dyads

OUT_PATH = Path("reports") / "eventgraph_country_network_3d.html"
SITUATION = Path(__file__).parent / "data" / "world_observer_situation.json"


def _situation_html() -> str:
    """Cached LLM situation report as HTML paragraphs (empty hint if not generated)."""
    import html as _html

    if not SITUATION.exists():
        return (
            '<p class="muted">No cached report. Run '
            "<code>python examples/synthesize_situation.py</code> (needs Ollama).</p>"
        )
    text = json.loads(SITUATION.read_text(encoding="utf-8")).get("text", "")
    paras = []
    for block in text.split("\n\n"):
        block = block.strip().lstrip("#").strip()
        if block:
            paras.append(f"<p>{_html.escape(block)}</p>")
    return "".join(paras)


def main() -> None:
    if not CAMEO.exists():
        print(f"{CAMEO} not found — run extract_cameo.py first.")
        return
    net = net_dyads(json.loads(CAMEO.read_text(encoding="utf-8")))
    dyads: dict[str, list] = {}
    degree: dict[str, int] = defaultdict(int)
    for lay in LAYERS:
        rows = []
        for (a, b), s in net[lay].items():
            rows.append([a, b, s])
            degree[a] += 1
            degree[b] += 1
        dyads[lay] = rows
    countries = sorted(degree, key=lambda c: -degree[c])
    data = {"layers": LAYERS, "dyads": dyads, "degree": degree, "countries": countries}
    sit = json.loads(SITUATION.read_text(encoding="utf-8")) if SITUATION.exists() else {}
    pairs_js = {
        k: {"text": v.get("text", ""), "edges": v.get("edges", [])}
        for k, v in sit.get("pairs", {}).items()
    }
    page = (
        _TEMPLATE.replace("__DATA__", json.dumps(data))
        .replace("__SITUATION__", _situation_html())
        .replace("__PAIRS__", json.dumps(pairs_js))
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB) — open in a browser (WebGL)")


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>EventGraph — 3D country network</title>
<style>
  body { margin:0; background:#0b1020; color:#e2e8f0;
    font-family:system-ui,sans-serif; overflow:hidden; }
  #hud { position:fixed; top:0; left:0; right:0; z-index:10; padding:12px 18px;
    background:linear-gradient(#0b1020f2,#0b102000); }
  #hud h1 { margin:0; font-size:17px; }
  #hud p { margin:4px 0 6px; font-size:12.5px; color:#94a3b8; }
  .btn { background:#1e293b; border:1px solid #334155; color:#cbd5e1; font-size:13px;
    padding:6px 13px; border-radius:8px; cursor:pointer; margin-right:5px; }
  .btn.on { background:#2563eb; border-color:#2563eb; color:#fff; }
  select { background:#1e293b; color:#cbd5e1; border:1px solid #334155;
    border-radius:8px; padding:5px 8px; font-size:13px; margin-right:4px; }
  #pair { margin-top:8px; font-size:13px; color:#94a3b8; }
  #g { position:fixed; inset:0; z-index:1; }
  #report { position:fixed; top:0; right:0; width:380px; max-width:90vw; height:100%;
    z-index:20; background:#0f172af2; border-left:1px solid #334155; padding:20px 22px;
    overflow:auto; transform:translateX(100%); transition:transform .25s;
    backdrop-filter:blur(3px); }
  #report.open { transform:translateX(0); }
  #report h2 { margin:0 0 4px; font-size:16px; }
  #report .muted2 { color:#64748b; font-size:11.5px; margin:0 0 12px; }
  #report p { font-size:13.5px; line-height:1.55; color:#cbd5e1; }
  #report code { background:#1e293b; padding:1px 5px; border-radius:4px; }
  #report .ev { margin-top:5px; font-size:13px; }
  #report .why { color:#94a3b8; font-size:12px; margin:1px 0 0 16px; font-style:italic; }
  #rptclose { float:right; cursor:pointer; color:#94a3b8; font-size:18px; border:none;
    background:none; }
</style>
<!-- single shared three instance (importmap) so label sprites render correctly;
     three/ prefix covers subpaths like three/webgpu that 3d-force-graph imports -->
<script type="importmap">
{ "imports": {
  "three": "https://esm.sh/three@0.160.0",
  "three/": "https://esm.sh/three@0.160.0/"
} }
</script>
</head><body>
<div id="hud">
  <h1>EventGraph — 3D country network</h1>
  <p>Link colour = domain (buttons below) · moving dots on a link = conflict, plain =
     cooperation. Click a country to fly to it &amp; focus its links; empty space to reset.</p>
  <div id="btns"></div>
  <div id="pair">Focus a pair:
    <select id="pa"></select> <select id="pb"></select>
    <button class="btn" id="clr">show all</button>
    <button class="btn" id="rpt">📄 Situation report</button>
    <span id="pairinfo"></span>
  </div>
</div>
<div id="report">
  <button id="rptclose">&times;</button>
  <h2 id="rpttitle">Situation report</h2>
  <p class="muted2" id="rptsub">Written by a local LLM from the signed multi-layer
    signals · cached.</p>
  <div id="rptbody">__SITUATION__</div>
</div>
<div id="g"></div>
<script type="module">
// Primary: one shared three (ES modules) -> always-on hub labels, no black box.
// Fallback: UMD 3d-force-graph -> still navigable, names on hover.
let ForceGraph3D = null, SpriteText = null;
try {
  ForceGraph3D = (await import('https://esm.sh/3d-force-graph?external=three')).default;
  SpriteText = (await import('https://esm.sh/three-spritetext?external=three')).default;
} catch (e) {
  try {
    await new Promise((res, rej) => {
      const sc = document.createElement('script');
      sc.src = 'https://unpkg.com/3d-force-graph';
      sc.onload = res; sc.onerror = rej;
      document.head.appendChild(sc);
    });
    ForceGraph3D = window.ForceGraph3D;  // SpriteText stays null -> hover labels only
  } catch (e2) {
    document.getElementById('g').innerHTML =
      '<p style="color:#f87171;padding:140px 40px">Could not load the 3D libraries '
      + '(needs an internet connection).</p>';
    throw e2;
  }
}
const D = __DATA__;
const PAIRS = __PAIRS__;  // per-pair: {text (LLM summary), edges:[{domain,cameo,sign}]}
const LAYERS = D.layers;
const active = new Set(LAYERS);  // multi-select: all layers on by default
const HUBS = 16;                 // how many top countries get a permanent label
let pair = [null, null];         // when both set: show only the pair + direct neighbours
const LAYER_COLOR = {            // link colour = domain; conflict shown via moving particles
  military: '#ef4444', economic: '#f59e0b', diplomatic: '#3b82f6',
  energy: '#a855f7', health: '#10b981',
};

function graphFor(activeSet) {
  // one link per (dyad, layer) so link colour can show the domain (no aggregation)
  const links = [], nbr = {};
  for (const L of activeSet) for (const [a, b, s] of D.dyads[L]) {
    if (!s) continue;
    links.push({ source: a, target: b, net: s, layer: L });
    (nbr[a] = nbr[a] || new Set()).add(b);
    (nbr[b] = nbr[b] || new Set()).add(a);
  }
  const ids = new Set();
  links.forEach(l => { ids.add(l.source); ids.add(l.target); });
  const nodes = [...ids].map(c => ({ id: c, deg: nbr[c] ? nbr[c].size : 1 }));
  // label only the top-degree hubs ("les principaux") to avoid clutter
  const hubSet = new Set([...nodes].sort((x, y) => y.deg - x.deg).slice(0, HUBS).map(n => n.id));
  nodes.forEach(n => { n.labelOn = hubSet.has(n.id); });
  return { nodes, links };
}

let hlNodes = new Set(), hlLinks = new Set();
const Graph = ForceGraph3D()(document.getElementById('g'))
  .backgroundColor('#0b1020')
  .nodeRelSize(4)
  .nodeVal(n => 2 + n.deg)
  .nodeLabel('id')  // hover tooltip (and the only labels in UMD fallback mode)
  .nodeThreeObject(n => {
    if (!SpriteText) return undefined;  // fallback mode: no always-on labels
    const focused = hlNodes.size > 0 && hlNodes.has(n.id);
    if (!focused && !n.labelOn) return undefined;  // hubs + focused only
    const s = new SpriteText(n.id);
    s.backgroundColor = false;  // no black box
    s.padding = 0;
    s.borderWidth = 0;
    s.color = hlNodes.size > 0 && !focused ? 'rgba(200,210,225,0.25)' : '#f8fafc';
    s.textHeight = 7 + Math.min(6, n.deg);
    s.fontWeight = '600';
    s.position.y = 9;
    return s;
  })
  .nodeThreeObjectExtend(true)
  .linkColor(l => {
    const base = LAYER_COLOR[l.layer] || '#94a3b8';
    if (!hlLinks.size) return base;
    return hlLinks.has(l) ? base : 'rgba(100,116,139,0.10)';
  })
  .linkWidth(l => Math.min(5, 0.6 + Math.abs(l.net)))
  .linkCurvature(l => (LAYERS.indexOf(l.layer) - 2) * 0.12)  // fan parallel layer edges
  .linkOpacity(0.78)
  .linkDirectionalParticles(l => (l.net < 0 ? 4 : 0))  // moving dots = conflict
  .linkDirectionalParticleWidth(2)
  .linkDirectionalParticleSpeed(0.01)
  .linkDirectionalParticleColor(() => '#fecaca')
  .onNodeClick(node => {
    hlNodes = new Set([node.id]); hlLinks = new Set();
    Graph.graphData().links.forEach(l => {
      const s = l.source.id || l.source, t = l.target.id || l.target;
      if (s === node.id || t === node.id) {
        hlLinks.add(l); hlNodes.add(s); hlNodes.add(t);
      }
    });
    Graph.nodeThreeObject(Graph.nodeThreeObject());  // refresh labels
    Graph.linkColor(Graph.linkColor());
    const d = 140, r = 1 + d / Math.hypot(node.x, node.y, node.z || 1);
    Graph.cameraPosition({ x: node.x * r, y: node.y * r, z: node.z * r }, node, 1200);
  })
  .onBackgroundClick(() => {
    hlNodes = new Set(); hlLinks = new Set();
    Graph.nodeThreeObject(Graph.nodeThreeObject());
    Graph.linkColor(Graph.linkColor());
  });

const lid = l => l.source.id || l.source;       // link endpoints can be id or node obj
const tid = l => l.target.id || l.target;

function currentData() {
  const g = graphFor(active);
  const [a, b] = pair;
  if (!a || !b) return g;
  // keep the pair + every node directly connected to A or B, and edges among them
  const keep = new Set([a, b]);
  for (const l of g.links) {
    const s = lid(l), t = tid(l);
    if (s === a || t === a || s === b || t === b) { keep.add(s); keep.add(t); }
  }
  return {
    nodes: g.nodes.filter(n => keep.has(n.id)).map(n => ({ ...n, labelOn: true })),
    links: g.links.filter(l => keep.has(lid(l)) && keep.has(tid(l))),
  };
}

function redraw() {
  hlNodes = new Set(); hlLinks = new Set();
  Graph.graphData(currentData());
  const [a, b] = pair;
  document.getElementById('pairinfo').textContent =
    a && b ? `— showing ${a} & ${b} and their direct links` : '';
  renderPanel();
}

const btns = document.getElementById('btns');
LAYERS.forEach(lay => {  // multi-select: each button toggles a layer on/off
  const b = document.createElement('button');
  b.className = 'btn'; b.textContent = lay;
  const col = LAYER_COLOR[lay];
  const paint = () => {  // colour the button by its layer so it maps to link colour
    const on = active.has(lay);
    b.style.background = on ? col : '#1e293b';
    b.style.color = on ? '#0b1020' : col;
    b.style.borderColor = col;
  };
  paint();
  b.onclick = () => {
    if (active.has(lay)) active.delete(lay); else active.add(lay);
    if (active.size === 0) active.add(lay);  // keep ≥1
    paint(); redraw();
  };
  btns.appendChild(b);
});

const pa = document.getElementById('pa'), pb = document.getElementById('pb');
function fill(sel) {
  sel.appendChild(new Option('—', ''));
  D.countries.forEach(c => sel.appendChild(new Option(c, c)));
}
fill(pa); fill(pb);
pa.onchange = pb.onchange = () => {
  pair = [pa.value || null, pb.value || null];
  redraw();
  if (pair[0] && pair[1]) report.classList.add('open');  // surface the pair summary
};
document.getElementById('clr').onclick = () => {
  pa.value = ''; pb.value = ''; pair = [null, null]; redraw();
};

const report = document.getElementById('report');
const GLOBAL_HTML = document.getElementById('rptbody').innerHTML;
const esc = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
function renderPanel() {
  const [a, b] = pair;
  const title = document.getElementById('rpttitle');
  const sub = document.getElementById('rptsub');
  const body = document.getElementById('rptbody');
  if (!a || !b) {
    title.textContent = 'Situation report';
    sub.textContent = 'Written by a local LLM from the signed multi-layer signals · cached.';
    body.innerHTML = GLOBAL_HTML;
    return;
  }
  const p = PAIRS[[a, b].sort().join('|')];
  title.textContent = a + ' & ' + b;
  if (!p || (!p.text && !(p.edges && p.edges.length))) {
    sub.textContent = '';
    body.innerHTML = '<p class="muted">No direct interactions recorded between these two.</p>';
    return;
  }
  sub.textContent = 'Pair summary (LLM + interactions, cached) · media-derived.';
  let h = p.text ? '<p>' + esc(p.text) + '</p>' : '';
  if (p.edges && p.edges.length) {
    h += '<p class="muted2">Interactions &amp; reasons</p>';
    h += p.edges.map(e => {
      const why = e.why ? `<div class="why">${esc(e.why)}</div>` : '';
      return `<div class="ev"><span style="color:${LAYER_COLOR[e.domain] || '#888'}">●</span> `
        + `${esc(e.domain)}: ${esc(e.cameo)} (${e.sign > 0 ? '+' : ''}${e.sign})</div>${why}`;
    }).join('');
  }
  body.innerHTML = h;
}
document.getElementById('rpt').onclick = () => report.classList.toggle('open');
document.getElementById('rptclose').onclick = () => report.classList.remove('open');
redraw();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
