"""Interactive 3D multiplex of the geopolitical network — fly through the layers.

Each signed layer (military / economic / diplomatic / energy / health) is a
horizontal plane at its own height. A country sits at the SAME (x, y) on every
plane it appears in; intra-layer edges are green (cooperation) / red (conflict);
thin vertical links couple the same country across layers. Rendered with WebGL
(3d-force-graph) — drag to rotate, scroll to zoom.

    python examples/build_multilayer_3d.py  → reports/eventgraph_multilayer_3d.html

Opens in any browser (loads 3d-force-graph from a CDN, so needs internet + WebGL).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from multilayer import CAMEO, LAYERS, net_dyads

LAYER_COLOR = {
    "military": "#ef4444",
    "economic": "#f59e0b",
    "diplomatic": "#3b82f6",
    "energy": "#a855f7",
    "health": "#10b981",
}
Z_SPACING = 160
XY_SCALE = 420


def build_graph_data(net: dict) -> dict:
    import networkx as nx

    # shared 2D layout over the union of all layers, so a country is at the same (x,y)
    union = nx.Graph()
    for lay in LAYERS:
        union.add_edges_from(net[lay].keys())
    if union.number_of_nodes() == 0:
        return {"nodes": [], "links": []}
    pos = nx.spring_layout(union, seed=2, k=0.5)

    nodes, links = [], []
    present: dict[str, list[int]] = {}  # country -> layer indices it appears in
    for li, lay in enumerate(LAYERS):
        countries = {c for pair in net[lay] for c in pair}
        deg: dict[str, int] = {}
        for a, b in net[lay]:
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1
        for c in countries:
            present.setdefault(c, []).append(li)
            x, y = pos[c]
            nodes.append(
                {
                    "id": f"{c}@@{lay}",
                    "name": f"{c} · {lay}",
                    "country": c,
                    "layer": lay,
                    "color": LAYER_COLOR[lay],
                    "val": 1 + deg.get(c, 0),
                    "x": x * XY_SCALE, "fx": x * XY_SCALE,
                    "y": y * XY_SCALE, "fy": y * XY_SCALE,
                    "z": li * Z_SPACING, "fz": li * Z_SPACING,
                }
            )
        for (a, b), s in net[lay].items():
            links.append(
                {
                    "source": f"{a}@@{lay}",
                    "target": f"{b}@@{lay}",
                    "color": "#22c55e" if s > 0 else "#ef4444",
                    "w": min(4, 0.5 + abs(s) / 2),
                }
            )
    # vertical coupling: same country across consecutive layers it appears in
    for c, lis in present.items():
        for i in range(len(lis) - 1):
            links.append(
                {
                    "source": f"{c}@@{LAYERS[lis[i]]}",
                    "target": f"{c}@@{LAYERS[lis[i + 1]]}",
                    "color": "rgba(148,163,184,0.35)",
                    "w": 0.4,
                }
            )
    return {"nodes": nodes, "links": links}


def main() -> None:
    if not CAMEO.exists():
        print(f"{CAMEO} not found — run extract_cameo.py first.")
        return
    cameo = json.loads(CAMEO.read_text(encoding="utf-8"))
    data = build_graph_data(net_dyads(cameo))
    legend = " ".join(f'<span style="color:{LAYER_COLOR[lay]}">●</span> {lay}' for lay in LAYERS)
    page = (
        _TEMPLATE.replace("__DATA__", json.dumps(data))
        .replace("__LEGEND__", legend)
        .replace("__N__", str(len(data["nodes"])))
    )
    out = Path("reports") / "eventgraph_multilayer_3d.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB) — open in a browser (needs WebGL)")


_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>EventGraph — 3D multiplex</title>
<style>
  body { margin:0; background:#0b1020; color:#e2e8f0;
    font-family:system-ui,sans-serif; overflow:hidden; }
  #hud { position:fixed; top:0; left:0; right:0; z-index:10; padding:12px 18px;
    background:linear-gradient(#0b1020ee,#0b102000); pointer-events:none; }
  #hud h1 { margin:0; font-size:17px; }
  #hud p { margin:4px 0 0; font-size:12.5px; color:#94a3b8; }
  #legend { margin-top:6px; font-size:13px; }
  #legend span { font-size:15px; }
</style>
<script src="//unpkg.com/three@0.149.0/build/three.min.js"></script>
<script src="//unpkg.com/3d-force-graph"></script>
</head><body>
<div id="hud">
  <h1>EventGraph — 3D multiplex (__N__ nodes)</h1>
  <p>Stacked layers; a country sits at the same x,y on each plane. Green = cooperation,
     red = conflict; faint vertical links couple a country across layers.
     Drag to rotate · scroll to zoom.</p>
  <div id="legend">__LEGEND__</div>
</div>
<div id="g"></div>
<script>
  const DATA = __DATA__;
  const Graph = ForceGraph3D()(document.getElementById('g'))
    .graphData(DATA)
    .backgroundColor('#0b1020')
    .nodeLabel('name')
    .nodeColor('color')
    .nodeVal('val')
    .nodeOpacity(0.92)
    .linkColor('color')
    .linkWidth('w')
    .linkOpacity(0.55)
    .enableNodeDrag(false);
  // nodes carry fixed x/y/z (fx/fy/fz) -> the layers stay as stacked planes
  Graph.d3Force('charge', null); Graph.d3Force('link', null); Graph.d3Force('center', null);
  setTimeout(function() { Graph.zoomToFit(600, 80); }, 400);
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
