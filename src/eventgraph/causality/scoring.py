"""Scoring primitives for causal paths.

The MVP uses a simple, fully deterministic model: a path's score is the product
of its edge weights, discounted by a per-hop ``decay`` factor so that shorter,
stronger chains rank above long, speculative ones. No LLM involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import prod

DEFAULT_DECAY = 0.85


def path_score(weights: list[float], decay: float = DEFAULT_DECAY) -> float:
    """Score a path from its consecutive edge weights.

    Args:
        weights: Edge weights along the path (``len == n_edges``).
        decay: Per-extra-hop discount in ``(0, 1]``. A single direct edge is
            scored at its raw weight; each additional hop multiplies by ``decay``.

    Returns:
        A score in ``[0, 1]``. Empty input scores ``0.0``.
    """
    if not weights:
        return 0.0
    return prod(weights) * (decay ** (len(weights) - 1))


@dataclass(frozen=True, slots=True)
class CausalPath:
    """An immutable, scored causal chain through the graph.

    Attributes:
        nodes: Ordered ``node_id`` sequence, cause first, effect last.
        relations: Relation-type names for each hop (``len == len(nodes) - 1``).
        weights: Edge weights for each hop.
        score: Result of :func:`path_score` over ``weights``.
    """

    nodes: tuple[str, ...]
    relations: tuple[str, ...]
    weights: tuple[float, ...]
    score: float

    @property
    def length(self) -> int:
        """Number of hops (edges) in the path."""
        return len(self.nodes) - 1

    @property
    def source(self) -> str:
        """The originating node id."""
        return self.nodes[0]

    @property
    def target(self) -> str:
        """The destination node id."""
        return self.nodes[-1]

    def __str__(self) -> str:
        return " -> ".join(self.nodes) + f"  (score={self.score:.3f})"
