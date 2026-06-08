"""Tests for community detection and risk hotspots."""

from __future__ import annotations

from datetime import datetime, timezone

from geonexus import Actor, Event, GeoNexus, Relation, RelationType, RiskHotspot


def _two_community_graph() -> GeoNexus:
    """Two tight groups (A: x1-x3, B: y1-y3) with a single weak bridge."""
    g = GeoNexus()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def add_group(prefix: str, weight: float) -> None:
        actors = [f"actor:{prefix}{i}" for i in range(1, 4)]
        for i in range(1, 4):
            g.add_actor(Actor(id=f"{prefix}{i}", name=f"{prefix}{i}"))
        for e in range(1, 3):  # two shared events bind the group densely
            ev = Event(id=f"{prefix}_e{e}", title=f"{prefix} event {e}", timestamp=now)
            g.add_event(ev)
            for a in actors:
                g.add_relation(
                    Relation(
                        source=a,
                        target=ev.node_id,
                        relation_type=RelationType.INVOLVES,
                        weight=weight,
                    )
                )

    add_group("x", 1.0)
    add_group("y", 1.0)

    # one weak bridge event linking the two groups
    bridge = Event(id="bridge", title="bridge", timestamp=now)
    g.add_event(bridge)
    g.add_relation(
        Relation(
            source="actor:x1",
            target=bridge.node_id,
            relation_type=RelationType.INVOLVES,
            weight=0.1,
        )
    )
    g.add_relation(
        Relation(
            source="actor:y1",
            target=bridge.node_id,
            relation_type=RelationType.INVOLVES,
            weight=0.1,
        )
    )
    return g


def test_emerging_clusters_separates_groups() -> None:
    g = _two_community_graph()
    clusters = g.emerging_clusters(min_size=3)
    assert len(clusters) >= 2

    # x1, x2, x3 should land in the same cluster; likewise the y group
    def cluster_of(node_id: str) -> int:
        return next(i for i, c in enumerate(clusters) if node_id in c)

    assert cluster_of("actor:x1") == cluster_of("actor:x2") == cluster_of("actor:x3")
    assert cluster_of("actor:y1") == cluster_of("actor:y2") == cluster_of("actor:y3")
    assert cluster_of("actor:x1") != cluster_of("actor:y1")


def test_emerging_clusters_min_size_filter() -> None:
    g = _two_community_graph()
    big = g.emerging_clusters(min_size=100)
    assert big == []


def test_emerging_clusters_empty_graph() -> None:
    assert GeoNexus().emerging_clusters() == []


def test_emerging_clusters_deterministic() -> None:
    g = _two_community_graph()
    assert g.emerging_clusters(seed=1) == g.emerging_clusters(seed=1)


def test_risk_hotspots_shape_and_order() -> None:
    g = _two_community_graph()
    spots = g.risk_hotspots(top_k=5)
    assert len(spots) == 5
    assert all(isinstance(s, RiskHotspot) for s in spots)

    scores = [s.score for s in spots]
    assert scores == sorted(scores, reverse=True)

    for s in spots:
        assert 0.0 <= s.centrality <= 1.0
        assert 0.0 <= s.influence <= 1.0
        assert 0.0 <= s.density <= 1.0


def test_risk_hotspots_actors_outrank_events() -> None:
    # actors sit at the hub (high degree + influence); events are leaf sinks
    g = _two_community_graph()
    top = g.risk_hotspots(top_k=1)[0]
    assert top.node_id.startswith("actor:")


def test_risk_hotspots_empty_graph() -> None:
    assert GeoNexus().risk_hotspots() == []


def test_risk_hotspots_weights_change_ranking() -> None:
    g = _two_community_graph()
    pure_density = g.risk_hotspots(top_k=10, weights=(0.0, 0.0, 1.0))
    pure_centrality = g.risk_hotspots(top_k=10, weights=(1.0, 0.0, 0.0))
    # different blends should not produce identical scores everywhere
    assert [s.score for s in pure_density] != [s.score for s in pure_centrality]


def test_risk_hotspot_str() -> None:
    spot = RiskHotspot(node_id="actor:x1", score=0.5, centrality=0.4, influence=0.6, density=0.2)
    text = str(spot)
    assert "actor:x1" in text
    assert "risk=0.500" in text
