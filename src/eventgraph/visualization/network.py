"""Network visualisation.

``draw`` uses matplotlib (a core dependency) and is enough for the demo.
``to_pyvis`` / ``export_html`` produce an interactive HTML graph but require the
optional ``pyvis`` extra::

    pip install eventgraph[viz]

They import pyvis lazily, so the rest of the library works without it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx

from eventgraph.core.node import NodeKind

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from eventgraph.graph.knowledge_graph import EventGraph

#: Colour per node kind, shared across backends.
NODE_COLORS: dict[str, str] = {
    NodeKind.EVENT.value: "#e74c3c",  # red
    NodeKind.ACTOR.value: "#3498db",  # blue
    NodeKind.ASSET.value: "#2ecc71",  # green
}
_DEFAULT_COLOR = "#95a5a6"


def _kind(graph: EventGraph, node_id: str) -> str:
    kind: str = graph.raw.nodes[node_id]["kind"]
    return kind


def draw(
    graph: EventGraph,
    ax: Axes | None = None,
    *,
    with_labels: bool = True,
    seed: int = 42,
) -> Axes:
    """Render the graph with matplotlib and return the Axes.

    Nodes are coloured by kind (event/actor/asset) and labelled with their
    human-readable name. Edges are drawn with arrows in causal direction.
    """
    import matplotlib.pyplot as plt

    g = graph.raw
    pos = nx.spring_layout(g, seed=seed)
    colors = [NODE_COLORS.get(_kind(graph, n), _DEFAULT_COLOR) for n in g.nodes]
    labels = {n: graph.label(n) for n in g.nodes}

    if ax is None:
        _, ax = plt.subplots(figsize=(11, 7))

    nx.draw_networkx_nodes(g, pos, node_color=colors, node_size=1400, alpha=0.9, ax=ax)
    nx.draw_networkx_edges(
        g, pos, ax=ax, arrows=True, arrowsize=18, edge_color="#7f8c8d", width=1.4
    )
    if with_labels:
        nx.draw_networkx_labels(g, pos, labels=labels, font_size=8, ax=ax)
    ax.set_axis_off()
    return ax


def to_pyvis(graph: EventGraph, *, height: str = "750px", width: str = "100%") -> Any:
    """Build an interactive ``pyvis.network.Network`` from the graph.

    Raises:
        ModuleNotFoundError: If the ``viz`` extra (pyvis) is not installed.
    """
    try:
        from pyvis.network import Network
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional dep
        raise ModuleNotFoundError(
            "Interactive visualisation requires pyvis. Install it with: pip install eventgraph[viz]"
        ) from exc

    net = Network(height=height, width=width, directed=True)
    for node_id in graph.raw.nodes:
        net.add_node(
            node_id,
            label=graph.label(node_id),
            color=NODE_COLORS.get(_kind(graph, node_id), _DEFAULT_COLOR),
            title=node_id,
        )
    for u, v, data in graph.raw.edges(data=True):
        net.add_edge(u, v, title=data.get("relation_type", ""), value=data.get("weight", 1.0))
    return net


def export_html(graph: EventGraph, path: str | Path) -> Path:
    """Write an interactive HTML visualisation to ``path`` (requires pyvis)."""
    net = to_pyvis(graph)
    out = Path(path)
    net.write_html(str(out), notebook=False)
    return out


def export_graphml(graph: EventGraph, path: str | Path) -> Path:
    """Export to GraphML (Gephi/yEd) using only networkx — no extra deps.

    The opaque ``obj`` payload is stripped so the output stays GraphML-valid.
    """
    g = graph.raw.copy()
    for _, data in g.nodes(data=True):
        data.pop("obj", None)
    for *_, data in g.edges(data=True):
        data.pop("obj", None)
    out = Path(path)
    nx.write_graphml(g, str(out))
    return out
