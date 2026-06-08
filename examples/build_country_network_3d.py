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
    data = {"layers": LAYERS, "dyads": dyads, "degree": degree}
    page = _TEMPLATE.replace("__DATA__", json.dumps(data))
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
  #g { position:fixed; inset:0; z-index:1; }
</style>
<!-- order matters: 3d-force-graph first (uses its bundled three), then three +
     spritetext for the labels (sprites render cross-instance via three's duck-typing) -->
<script src="https://unpkg.com/3d-force-graph"></script>
<script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
<script src="https://unpkg.com/three-spritetext/dist/three-spritetext.min.js"></script>
</head><body>
<div id="hud">
  <h1>EventGraph — 3D country network</h1>
  <p>Green = cooperation, red = conflict. Click a country to fly to it &amp; focus its
     links; click empty space to reset. Drag = rotate · scroll = zoom · right-drag = pan.</p>
  <div id="btns"></div>
</div>
<div id="g"></div>
<script>
const D = __DATA__;
if (typeof ForceGraph3D === 'undefined' || typeof SpriteText === 'undefined') {
  document.getElementById('g').innerHTML =
    '<p style="color:#f87171;padding:140px 40px">Could not load the 3D libraries '
    + '(needs an internet connection).</p>';
  throw new Error('libs not loaded');
}
const LAYERS = D.layers;
const active = new Set(LAYERS);  // multi-select: all layers on by default
const HUBS = 16;                 // how many top countries get a permanent label
const COOP = '#22c55e', CONF = '#ef4444';

function graphFor(activeSet) {
  const agg = {}, deg = {};
  for (const L of activeSet) for (const [a, b, s] of D.dyads[L]) {
    const k = a < b ? a + '|' + b : b + '|' + a;
    agg[k] = (agg[k] || 0) + s;
  }
  const ids = new Set(), links = [];
  for (const k in agg) {
    if (!agg[k]) continue;
    const [a, b] = k.split('|');
    ids.add(a); ids.add(b);
    deg[a] = (deg[a] || 0) + 1; deg[b] = (deg[b] || 0) + 1;
    links.push({ source: a, target: b, net: agg[k] });
  }
  const nodes = [...ids].map(c => ({ id: c, deg: deg[c] || 1 }));
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
  .nodeThreeObject(n => {
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
    const base = l.net > 0 ? COOP : CONF;
    if (!hlLinks.size) return base;
    return hlLinks.has(l) ? base : 'rgba(100,116,139,0.12)';
  })
  .linkWidth(l => Math.min(5, 0.6 + Math.abs(l.net)))
  .linkOpacity(0.7)
  .linkDirectionalParticles(0)
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

function redraw() {
  hlNodes = new Set(); hlLinks = new Set();
  Graph.graphData(graphFor(active));
}

const btns = document.getElementById('btns');
LAYERS.forEach(lay => {  // multi-select: each button toggles a layer on/off
  const b = document.createElement('button');
  b.className = 'btn on'; b.textContent = lay;
  b.onclick = () => {
    if (active.has(lay)) { active.delete(lay); b.classList.remove('on'); }
    else { active.add(lay); b.classList.add('on'); }
    if (active.size === 0) { active.add(lay); b.classList.add('on'); }  // keep ≥1
    redraw();
  };
  btns.appendChild(b);
});
redraw();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
