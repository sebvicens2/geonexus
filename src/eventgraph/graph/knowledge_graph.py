"""EventGraph: a typed, causal knowledge graph.

This is the single public entry point of the library. It wraps a
``networkx.MultiDiGraph`` (directed, parallel edges allowed) behind a small,
stable API so the storage and reasoning layers never touch networkx directly.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import networkx as nx

from eventgraph.causality.propagation import impact_paths, reachable_scores
from eventgraph.causality.scoring import DEFAULT_DECAY, CausalPath
from eventgraph.core.actor import Actor
from eventgraph.core.asset import Asset
from eventgraph.core.event import Event
from eventgraph.core.node import NodeKind
from eventgraph.core.relation import Relation

#: Anything that can stand in for a node: an id string or a node object.
NodeRef = str | Event | Actor | Asset
NodeObj = Event | Actor | Asset

Direction = str  # "in" | "out" | "both"
CentralityMethod = str  # "degree" | "betweenness" | "closeness"


class EventGraph:
    """A causal graph of events, actors and assets.

    Example:
        >>> from eventgraph import EventGraph, Actor, Asset, Relation, RelationType
        >>> g = EventGraph()
        >>> iran = g.add_actor(Actor(id="iran", name="Iran"))
        >>> gold = g.add_asset(Asset(ticker="XAU_USD"))
        >>> g.add_relation(Relation(source=iran, target=gold,
        ...                         relation_type=RelationType.AFFECTS, weight=0.4))
        >>> g.neighbors(iran)
        ['asset:XAU_USD']
    """

    def __init__(self) -> None:
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()

    # ------------------------------------------------------------------ #
    # construction
    # ------------------------------------------------------------------ #
    def add_event(self, event: Event) -> str:
        """Add (or replace) an event node. Returns its ``node_id``."""
        self._g.add_node(event.node_id, kind=NodeKind.EVENT.value, obj=event)
        return event.node_id

    def add_actor(self, actor: Actor) -> str:
        """Add (or replace) an actor node. Returns its ``node_id``."""
        self._g.add_node(actor.node_id, kind=NodeKind.ACTOR.value, obj=actor)
        return actor.node_id

    def add_asset(self, asset: Asset) -> str:
        """Add (or replace) an asset node. Returns its ``node_id``."""
        self._g.add_node(asset.node_id, kind=NodeKind.ASSET.value, obj=asset)
        return asset.node_id

    def add_relation(self, relation: Relation) -> Relation:
        """Add a directed edge described by a :class:`Relation`.

        Both endpoints must already exist in the graph. Parallel edges of
        *different* types are kept; re-adding the same type overwrites it.

        Raises:
            KeyError: If ``source`` or ``target`` is not in the graph.
        """
        for ref in (relation.source, relation.target):
            if ref not in self._g:
                raise KeyError(f"unknown node {ref!r}; add it before relating it")
        self._g.add_edge(
            relation.source,
            relation.target,
            key=relation.relation_type.value,
            relation_type=relation.relation_type.value,
            weight=relation.weight,
            obj=relation,
        )
        return relation

    def connect(
        self,
        source: NodeRef,
        target: NodeRef,
        relation_type: Any = None,
        weight: float = 1.0,
    ) -> Relation:
        """Ergonomic helper to relate two nodes given as ids *or* objects.

        Builds a :class:`Relation` and delegates to :meth:`add_relation`.
        """
        from eventgraph.ontology.relation_types import RelationType

        rel = Relation(
            source=self._ref(source),
            target=self._ref(target),
            relation_type=relation_type or RelationType.AFFECTS,
            weight=weight,
        )
        return self.add_relation(rel)

    # ------------------------------------------------------------------ #
    # access
    # ------------------------------------------------------------------ #
    @property
    def raw(self) -> nx.MultiDiGraph:
        """The underlying networkx graph (for advanced/visualisation use)."""
        return self._g

    def get(self, node: NodeRef) -> NodeObj:
        """Return the domain object stored at ``node``.

        Raises:
            KeyError: If the node is unknown.
        """
        nid = self._ref(node)
        if nid not in self._g:
            raise KeyError(nid)
        obj: NodeObj = self._g.nodes[nid]["obj"]
        return obj

    def label(self, node: NodeRef) -> str:
        """Human-readable label for a node (title / name / ticker)."""
        obj = self.get(node)
        if isinstance(obj, Event):
            return obj.title
        if isinstance(obj, Actor):
            return obj.name
        return obj.ticker

    def nodes(self, kind: NodeKind | None = None) -> Iterator[NodeObj]:
        """Iterate over node objects, optionally filtered by kind."""
        for _, data in self._g.nodes(data=True):
            if kind is None or data["kind"] == kind.value:
                yield data["obj"]

    def __contains__(self, node: NodeRef) -> bool:
        return self._ref(node) in self._g

    def __len__(self) -> int:
        return int(self._g.number_of_nodes())

    # ------------------------------------------------------------------ #
    # traversal & metrics
    # ------------------------------------------------------------------ #
    def neighbors(self, node: NodeRef, direction: Direction = "both") -> list[str]:
        """Return adjacent node ids.

        Args:
            node: The node to inspect.
            direction: ``"out"`` (successors), ``"in"`` (predecessors) or
                ``"both"`` (default).
        """
        nid = self._ref(node)
        if direction == "out":
            return list(self._g.successors(nid))
        if direction == "in":
            return list(self._g.predecessors(nid))
        if direction == "both":
            return list(dict.fromkeys([*self._g.successors(nid), *self._g.predecessors(nid)]))
        raise ValueError(f"direction must be 'in', 'out' or 'both', got {direction!r}")

    def shortest_path(self, source: NodeRef, target: NodeRef) -> list[str]:
        """Shortest directed path (by hop count) as a list of node ids.

        Returns an empty list when no path exists.
        """
        try:
            path: list[str] = nx.shortest_path(self._g, self._ref(source), self._ref(target))
            return path
        except nx.NetworkXNoPath:
            return []

    def centrality(self, method: CentralityMethod = "degree") -> dict[str, float]:
        """Structural centrality of every node.

        Args:
            method: ``"degree"``, ``"betweenness"``, ``"closeness"`` or
                ``"pagerank"`` (weighted).
        """
        funcs = {
            "degree": nx.degree_centrality,
            "betweenness": nx.betweenness_centrality,
            "closeness": nx.closeness_centrality,
        }
        if method not in funcs:
            raise ValueError(f"unknown centrality method {method!r}")
        scores: dict[str, float] = funcs[method](self._g)
        return scores

    def influence_score(
        self, node: NodeRef, *, max_depth: int = 5, decay: float = DEFAULT_DECAY
    ) -> float:
        """How strongly a node's effects radiate through the graph.

        Defined as the sum of the best causal-path scores from ``node`` to each
        of its descendants. A node with no outgoing reach scores ``0.0``.
        """
        scores = reachable_scores(self._g, self._ref(node), max_depth=max_depth, decay=decay)
        return sum(scores.values())

    # ------------------------------------------------------------------ #
    # causality
    # ------------------------------------------------------------------ #
    def impact(
        self,
        target: NodeRef,
        *,
        sources: Iterable[NodeRef] | None = None,
        max_depth: int = 5,
        top_k: int = 10,
        decay: float = DEFAULT_DECAY,
    ) -> list[CausalPath]:
        """Most probable causal chains leading to ``target``.

        Args:
            target: The node (often an asset) you care about.
            sources: Optionally restrict chains to these origins.
            max_depth: Maximum chain length in hops.
            top_k: Maximum number of chains returned.
            decay: Per-hop discount.

        Returns:
            Chains ranked by descending score.
        """
        resolved = None if sources is None else [self._ref(s) for s in sources]
        return impact_paths(
            self._g,
            self._ref(target),
            sources=resolved,
            max_depth=max_depth,
            top_k=top_k,
            decay=decay,
        )

    # ------------------------------------------------------------------ #
    # serialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Serialise the whole graph to plain, JSON-ready dicts.

        Output is *canonical* — each list is sorted by a stable key — so the
        serialisation is deterministic (clean diffs) and the round-trip
        ``from_dict(to_dict())`` is order-independent.
        """
        events, actors, assets = [], [], []
        for _, data in self._g.nodes(data=True):
            obj = data["obj"]
            dumped = obj.model_dump(mode="json")
            if data["kind"] == NodeKind.EVENT.value:
                events.append(dumped)
            elif data["kind"] == NodeKind.ACTOR.value:
                actors.append(dumped)
            else:
                assets.append(dumped)
        relations = [data["obj"].model_dump(mode="json") for *_, data in self._g.edges(data=True)]

        events.sort(key=lambda d: d["id"])
        actors.sort(key=lambda d: d["id"])
        assets.sort(key=lambda d: d["ticker"])
        relations.sort(key=lambda d: (d["source"], d["target"], d["relation_type"]))
        return {"events": events, "actors": actors, "assets": assets, "relations": relations}

    @classmethod
    def from_dict(cls, data: dict[str, list[dict[str, Any]]]) -> EventGraph:
        """Rebuild a graph from :meth:`to_dict` output."""
        g = cls()
        for raw in data.get("events", []):
            g.add_event(Event(**raw))
        for raw in data.get("actors", []):
            g.add_actor(Actor(**raw))
        for raw in data.get("assets", []):
            g.add_asset(Asset(**raw))
        for raw in data.get("relations", []):
            g.add_relation(Relation(**raw))
        return g

    def save_json(self, path: str | Path) -> None:
        """Write the graph to ``path`` as indented JSON."""
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> EventGraph:
        """Load a graph previously written by :meth:`save_json`."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _ref(node: NodeRef) -> str:
        """Resolve a node id string or node object to its ``node_id``."""
        if isinstance(node, (Event, Actor, Asset)):
            return node.node_id
        return node
