"""Causal propagation: enumerate and score chains through the graph.

Functions here operate directly on a ``networkx.MultiDiGraph`` so the causality
engine stays decoupled from the :class:`~eventgraph.graph.knowledge_graph.EventGraph`
wrapper (and is therefore easy to unit-test in isolation).
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise

import networkx as nx

from eventgraph.causality.scoring import DEFAULT_DECAY, CausalPath, path_score


def _best_edge(graph: nx.MultiDiGraph, u: str, v: str) -> tuple[float, str]:
    """Return the strongest parallel edge ``(weight, relation_type)`` from u to v."""
    data = graph.get_edge_data(u, v)
    best = max(data.values(), key=lambda d: d.get("weight", 0.0))
    return float(best.get("weight", 0.0)), str(best.get("relation_type", ""))


def _build_path(graph: nx.MultiDiGraph, nodes: list[str], decay: float) -> CausalPath:
    """Materialise a node sequence into a scored :class:`CausalPath`."""
    weights: list[float] = []
    relations: list[str] = []
    for u, v in pairwise(nodes):
        w, rel = _best_edge(graph, u, v)
        weights.append(w)
        relations.append(rel)
    return CausalPath(
        nodes=tuple(nodes),
        relations=tuple(relations),
        weights=tuple(weights),
        score=path_score(weights, decay),
    )


def impact_paths(
    graph: nx.MultiDiGraph,
    target: str,
    *,
    sources: Iterable[str] | None = None,
    max_depth: int = 5,
    top_k: int = 10,
    decay: float = DEFAULT_DECAY,
) -> list[CausalPath]:
    """Find the most probable causal chains leading *to* ``target``.

    Args:
        graph: The directed multigraph (cause -> effect edges).
        target: Destination ``node_id``.
        sources: Restrict chains to these origin node ids. ``None`` uses every
            ancestor of ``target``.
        max_depth: Maximum number of hops per chain.
        top_k: Maximum number of chains to return.
        decay: Per-hop discount passed to the scorer.

    Returns:
        Chains sorted by descending score (highest probability first).
    """
    if target not in graph:
        return []

    ancestors = nx.ancestors(graph, target)
    origins = ancestors if sources is None else (set(sources) & ancestors)

    paths: list[CausalPath] = []
    for src in origins:
        for node_seq in nx.all_simple_paths(graph, src, target, cutoff=max_depth):
            paths.append(_build_path(graph, node_seq, decay))

    paths.sort(key=lambda p: p.score, reverse=True)
    return paths[:top_k]


def reachable_scores(
    graph: nx.MultiDiGraph,
    source: str,
    *,
    max_depth: int = 5,
    decay: float = DEFAULT_DECAY,
) -> dict[str, float]:
    """Best forward-propagation score from ``source`` to every descendant.

    Used to express how far and how strongly a node's influence radiates.

    Args:
        graph: The directed multigraph.
        source: Origin ``node_id``.
        max_depth: Maximum number of hops to follow.
        decay: Per-hop discount passed to the scorer.

    Returns:
        Mapping ``descendant_node_id -> best_path_score``.
    """
    if source not in graph:
        return {}

    best: dict[str, float] = {}
    for target in nx.descendants(graph, source):
        top = 0.0
        for node_seq in nx.all_simple_paths(graph, source, target, cutoff=max_depth):
            score = _build_path(graph, node_seq, decay).score
            if score > top:
                top = score
        best[target] = top
    return best
