"""Graph analytics: community detection and risk hotspots.

These are deterministic, dependency-light heuristics that operate on the
undirected projection of the graph. They power :meth:`EventGraph.emerging_clusters`
and :meth:`EventGraph.risk_hotspots`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from eventgraph.graph.knowledge_graph import EventGraph


def undirected_simple(graph: nx.MultiDiGraph) -> nx.Graph:
    """Collapse a MultiDiGraph into a weighted simple undirected graph.

    Parallel/opposite edges between the same pair of nodes have their weights
    summed. Used by every structural metric below.
    """
    h: nx.Graph = nx.Graph()
    h.add_nodes_from(graph.nodes())
    for u, v, data in graph.edges(data=True):
        w = float(data.get("weight", 1.0))
        if h.has_edge(u, v):
            h[u][v]["weight"] += w
        else:
            h.add_edge(u, v, weight=w)
    return h


def detect_communities(graph: EventGraph, *, min_size: int = 2, seed: int = 42) -> list[list[str]]:
    """Detect strongly-connected groups (themes / emerging crises).

    Uses Louvain community detection on the weighted undirected projection.

    Returns:
        Clusters (lists of ``node_id``) with at least ``min_size`` members,
        sorted from largest to smallest.
    """
    h = undirected_simple(graph.raw)
    if h.number_of_edges() == 0:
        return []
    communities: list[set[str]] = nx.community.louvain_communities(h, weight="weight", seed=seed)
    clusters = [sorted(c) for c in communities if len(c) >= min_size]
    clusters.sort(key=len, reverse=True)
    return clusters


@dataclass(frozen=True, slots=True)
class RiskHotspot:
    """A node flagged as a risk concentration point.

    Attributes:
        node_id: The node.
        score: Blended hotspot score in ``[0, 1]``.
        centrality: Normalised degree centrality component.
        influence: Normalised causal-reach (influence) component.
        density: Local clustering coefficient (how tight the neighbourhood is).
    """

    node_id: str
    score: float
    centrality: float
    influence: float
    density: float

    def __str__(self) -> str:
        return (
            f"{self.node_id}  risk={self.score:.3f} "
            f"(centrality={self.centrality:.2f}, influence={self.influence:.2f}, "
            f"density={self.density:.2f})"
        )


def risk_hotspots(
    graph: EventGraph,
    *,
    top_k: int = 10,
    weights: tuple[float, float, float] = (0.4, 0.4, 0.2),
) -> list[RiskHotspot]:
    """Rank nodes by a blended risk-concentration heuristic.

    The score combines three normalised signals:

    - **centrality** — degree centrality (how connected the node is),
    - **influence** — :meth:`EventGraph.influence_score` (causal reach),
    - **density** — square clustering (local neighbourhood redundancy; this works
      on bipartite-style co-occurrence graphs where triangle clustering is always
      zero).

    Args:
        graph: The graph to analyse.
        top_k: Number of hotspots to return.
        weights: ``(centrality, influence, density)`` blend weights.

    Returns:
        Hotspots sorted by descending score.
    """
    h = undirected_simple(graph.raw)
    if h.number_of_nodes() == 0:
        return []

    degree: dict[str, float] = nx.degree_centrality(h)
    clustering: dict[str, float] = nx.square_clustering(h)
    influence = {n: graph.influence_score(n) for n in h.nodes}

    def _normalise(values: dict[str, float]) -> dict[str, float]:
        top = max(values.values(), default=0.0)
        if top <= 0.0:
            return dict.fromkeys(values, 0.0)
        return {k: v / top for k, v in values.items()}

    deg_n = _normalise(degree)
    inf_n = _normalise(influence)
    w_cen, w_inf, w_den = weights

    spots = [
        RiskHotspot(
            node_id=n,
            score=w_cen * deg_n[n] + w_inf * inf_n[n] + w_den * clustering.get(n, 0.0),
            centrality=deg_n[n],
            influence=inf_n[n],
            density=clustering.get(n, 0.0),
        )
        for n in h.nodes
    ]
    spots.sort(key=lambda r: r.score, reverse=True)
    return spots[:top_k]
