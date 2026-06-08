"""Render the LLM-extracted relation graph as an interactive network.

Each edge is a single grounded relation (subject —verb→ object); the network just
*maps* them — no multi-hop composition, no invented links. We drop degree-1 leaves
(dust) and render the connected core, edges labelled with the relation verb.

    python examples/relation_network.py        → reports/geonexus_relation_network.html

Self-contained (pyvis inlined); open in any browser. Requires the relations file
(examples/extract_relations.py) and the [viz] extra (pyvis).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from relation_graph import _edge_label, build, load_triples

OUT_PATH = Path("reports") / "geonexus_relation_network.html"
PALETTE = ["#94a3b8", "#60a5fa", "#3b82f6", "#1d4ed8", "#dc2626"]  # by degree tier


def _color(deg: int) -> str:
    return PALETTE[min(deg // 3, len(PALETTE) - 1)]


def build_network(min_degree: int = 2):  # returns (pyvis Network, n_core, n_total)
    from pyvis.network import Network

    triples = load_triples()
    g, _ = build(triples)
    raw = g.raw
    und = raw.to_undirected()
    deg = dict(und.degree())
    core = {n for n, d in deg.items() if d >= min_degree}

    net = Network(
        height="780px",
        width="100%",
        bgcolor="#0f172a",
        font_color="#e2e8f0",
        cdn_resources="in_line",
        directed=True,
    )
    net.barnes_hut(gravity=-9000, spring_length=130, spring_strength=0.02)
    for n in core:
        d = deg[n]
        net.add_node(
            n,
            label=g.label(n),
            title=f"{g.label(n)} — {d} relations",
            color=_color(d),
            size=8 + min(d, 18) * 2,
        )
    for u, v in raw.edges():
        if u in core and v in core:
            net.add_edge(u, v, title=_edge_label(g, u, v), color="#475569", arrowStrength=0.5)
    return net, len(core), und.number_of_nodes()


def main() -> None:
    try:
        net, n_core, n_total = build_network()
    except ModuleNotFoundError:
        print("pyvis required: pip install geonexus[viz]")
        return
    if n_total == 0:
        print("No relations — run examples/extract_relations.py first.")
        return
    inner = net.generate_html()
    # wrap with a small header explaining what it is (honest framing)
    header = (
        '<div style="font-family:system-ui;background:#0f172a;color:#e2e8f0;'
        'padding:14px 20px;border-bottom:1px solid #1e293b">'
        "<b>GeoNexus — relation network</b> · each edge is one grounded "
        "subject→relation→object fact (hover for the verb). "
        f"Showing the connected core ({n_core} entities, degree ≥ 2; "
        "degree-1 leaves hidden). No multi-hop inference.</div>"
    )
    page = inner.replace("<body>", f"<body>{header}", 1) if "<body>" in inner else header + inner
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB) — open it in a browser")


if __name__ == "__main__":
    main()
