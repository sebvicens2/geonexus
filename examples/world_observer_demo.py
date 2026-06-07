"""World Observer → EventGraph: turn a real event feed into actionable structure.

Loads a real sample of analysed World Observer articles, builds a causal/relational
graph, and surfaces:

    - the most influential actors and regions,
    - the most connected events,
    - emerging clusters (themes / crises),
    - risk hotspots.

Run:
    python examples/world_observer_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from world_observer_common import build_graph, load_events, wo_kind

from eventgraph import EventGraph


def _rule(title: str) -> None:
    print(f"\n{title}")
    print("─" * len(title))


def top_by_influence(g: EventGraph, kind: str, n: int = 8) -> list[tuple[str, float]]:
    scored = [
        (g.label(obj.node_id), g.influence_score(obj.node_id))
        for obj in g.nodes()
        if wo_kind(g, obj.node_id) == kind
    ]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored[:n]


def most_connected_events(g: EventGraph, n: int = 8) -> list[tuple[str, int]]:
    events = [
        (g.label(obj.node_id), len(g.neighbors(obj.node_id, direction="in")))
        for obj in g.nodes()
        if wo_kind(g, obj.node_id) == "event"
    ]
    events.sort(key=lambda kv: kv[1], reverse=True)
    return events[:n]


def describe_cluster(g: EventGraph, cluster: list[str], n_entities: int = 5) -> list[str]:
    entities = [nid for nid in cluster if not nid.startswith("event:")]
    entities.sort(key=lambda nid: g.influence_score(nid), reverse=True)
    return [g.label(nid) for nid in entities[:n_entities]]


def main() -> None:
    events = load_events()
    g = build_graph(events)

    n_events = sum(1 for o in g.nodes() if wo_kind(g, o.node_id) == "event")
    print(
        f"Loaded {n_events} real World Observer events → graph with {len(g)} nodes "
        f"and {g.raw.number_of_edges()} relations."
    )

    _rule("Top influential actors")
    for name, score in top_by_influence(g, "actor"):
        print(f"  {name:<26} {score:.2f}")

    _rule("Top influential regions")
    for name, score in top_by_influence(g, "region"):
        print(f"  {name:<26} {score:.2f}")

    _rule("Most connected events")
    for title, degree in most_connected_events(g):
        print(f"  [{degree:>2} links] {title[:72]}")

    _rule("Emerging clusters (themes / crises)")
    clusters = g.emerging_clusters(min_size=5)
    for i, cluster in enumerate(clusters[:6], start=1):
        members = describe_cluster(g, cluster)
        print(f"  Cluster {i} ({len(cluster)} nodes): {', '.join(members)}")

    _rule("Top risk hotspots")
    for spot in g.risk_hotspots(top_k=10):
        print(
            f"  {g.label(spot.node_id):<26} risk={spot.score:.3f} "
            f"(cen={spot.centrality:.2f} inf={spot.influence:.2f} den={spot.density:.2f})"
        )


if __name__ == "__main__":
    main()
