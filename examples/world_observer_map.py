"""Render a map of the World Observer event graph, coloured by emerging cluster.

Produces:
    - world_observer_graph.png   (matplotlib, nodes coloured by cluster)
    - world_observer_graph.html  (interactive, if pyvis is installed)

To stay readable we render a backbone: the top clusters, each reduced to its most
influential entities plus its highest-severity events.

Run:
    python examples/world_observer_map.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
from world_observer_common import build_graph, load_events, subgraph

from geonexus import GeoNexus
from geonexus.visualization import export_html

PALETTE = ["#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#f39c12", "#1abc9c", "#e67e22"]
PNG_PATH = Path("world_observer_graph.png")
HTML_PATH = Path("world_observer_graph.html")


def select_backbone(
    g: GeoNexus,
    clusters: list[list[str]],
    *,
    n_clusters: int = 4,
    entities_per: int = 7,
    events_per: int = 4,
) -> tuple[set[str], dict[str, int]]:
    """Pick a readable subset of nodes and map each to its cluster index."""
    keep: set[str] = set()
    cluster_of: dict[str, int] = {}
    for idx, cluster in enumerate(clusters[:n_clusters]):
        entities = [n for n in cluster if not n.startswith("event:")]
        events = [n for n in cluster if n.startswith("event:")]
        entities.sort(key=lambda n: g.influence_score(n), reverse=True)
        events.sort(key=lambda n: g.get(n).severity, reverse=True)  # type: ignore[union-attr]
        chosen = entities[:entities_per] + events[:events_per]
        for n in chosen:
            keep.add(n)
            cluster_of[n] = idx
    return keep, cluster_of


def render_png(g: GeoNexus, cluster_of: dict[str, int]) -> None:
    h = g.raw.to_undirected()
    pos = nx.spring_layout(h, seed=11, k=0.6)
    colors = [PALETTE[cluster_of.get(n, 0) % len(PALETTE)] for n in h.nodes]
    sizes = [900 if not n.startswith("event:") else 250 for n in h.nodes]
    labels = {n: g.label(n)[:22] for n in h.nodes if not n.startswith("event:")}

    fig, ax = plt.subplots(figsize=(15, 10))
    nx.draw_networkx_edges(h, pos, ax=ax, edge_color="#cccccc", width=0.8)
    nx.draw_networkx_nodes(h, pos, node_color=colors, node_size=sizes, alpha=0.9, ax=ax)
    nx.draw_networkx_labels(h, pos, labels=labels, font_size=8, font_weight="bold", ax=ax)
    ax.set_title("World Observer — event graph by emerging cluster", fontsize=15, fontweight="bold")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(PNG_PATH, dpi=130, bbox_inches="tight")
    print(f"wrote {PNG_PATH}")


def main() -> None:
    g = build_graph(load_events())
    clusters = g.emerging_clusters(min_size=5)
    keep, cluster_of = select_backbone(g, clusters)
    sub = subgraph(g, keep)
    print(f"backbone: {len(sub)} nodes from top {min(4, len(clusters))} clusters")

    render_png(sub, cluster_of)

    try:
        export_html(sub, HTML_PATH)
        print(f"wrote {HTML_PATH}")
    except ModuleNotFoundError:
        print("pyvis not installed — skipping interactive HTML (pip install geonexus[viz])")


if __name__ == "__main__":
    main()
