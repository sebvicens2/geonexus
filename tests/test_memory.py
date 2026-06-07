"""Tests for EventMemory (temporal snapshots and diffs)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from eventgraph import Actor, Event, EventGraph, EventMemory, Relation, RelationType
from eventgraph.memory.event_memory import _norm_date

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _group(g: EventGraph, prefix: str, n_events: int = 2) -> None:
    """Add a dense community: entities prefix1..3 sharing n_events events."""
    actors = [f"actor:{prefix}{i}" for i in range(1, 4)]
    for i in range(1, 4):
        g.add_actor(Actor(id=f"{prefix}{i}", name=f"{prefix}{i}"))
    for e in range(n_events):
        ev = Event(id=f"{prefix}_e{e}", title=f"{prefix} {e}", timestamp=NOW)
        g.add_event(ev)
        for a in actors:
            g.add_relation(
                Relation(
                    source=a, target=ev.node_id, relation_type=RelationType.INVOLVES, weight=1.0
                )
            )


def _graph(*prefixes: str) -> EventGraph:
    g = EventGraph()
    for p in prefixes:
        _group(g, p)
    return g


# ------------------------------------------------------------------ #
# storage basics
# ------------------------------------------------------------------ #
def test_norm_date_variants() -> None:
    assert _norm_date("2026-06-07") == "2026-06-07"
    assert _norm_date("2026-06-07T15:00:00+00:00") == "2026-06-07"
    assert _norm_date(date(2026, 6, 7)) == "2026-06-07"
    assert _norm_date(datetime(2026, 6, 7, 15, 0, tzinfo=timezone.utc)) == "2026-06-07"


def test_snapshot_and_access() -> None:
    m = EventMemory()
    m.snapshot("2026-06-01", _graph("x"))
    m.snapshot("2026-06-02", _graph("x", "y"))
    assert len(m) == 2
    assert m.dates() == ["2026-06-01", "2026-06-02"]
    assert "2026-06-01" in m
    assert "2026-06-03" not in m
    assert len(m.get("2026-06-02")) > len(m.get("2026-06-01"))


def test_snapshot_is_frozen() -> None:
    m = EventMemory()
    g = _graph("x")
    m.snapshot("2026-06-01", g)
    g.add_actor(Actor(id="late", name="late"))  # mutate after snapshot
    assert "actor:late" not in m.get("2026-06-01")


def test_directory_persistence(tmp_path: Path) -> None:
    m = EventMemory(tmp_path)
    m.snapshot("2026-06-01", _graph("x", "y"))
    assert (tmp_path / "2026-06-01.json").exists()

    reloaded = EventMemory(tmp_path)
    assert reloaded.dates() == ["2026-06-01"]
    assert reloaded.get("2026-06-01").to_dict() == m.get("2026-06-01").to_dict()


# ------------------------------------------------------------------ #
# hotspot diffs
# ------------------------------------------------------------------ #
def test_compare_hotspots_appear_disappear() -> None:
    m = EventMemory()
    m.snapshot("2026-06-01", _graph("x"))  # only x entities
    m.snapshot("2026-06-02", _graph("y"))  # only y entities

    changes = m.compare_hotspots("2026-06-01", "2026-06-02", top_k=10)
    status = {c.node_id: c.status for c in changes}
    assert status["actor:x1"] == "disappeared"
    assert status["actor:y1"] == "appeared"
    # sorted by descending delta (risers first)
    deltas = [c.delta for c in changes]
    assert deltas == sorted(deltas, reverse=True)


def test_compare_hotspots_persisting_node_not_appeared() -> None:
    m = EventMemory()
    m.snapshot("2026-06-01", _graph("x", "y"))
    m.snapshot("2026-06-02", _graph("x", "z"))
    status = {c.node_id: c.status for c in m.compare_hotspots("2026-06-01", "2026-06-02")}
    assert status["actor:x1"] in {"stable", "intensified", "faded"}
    assert status["actor:z1"] == "appeared"
    assert status["actor:y1"] == "disappeared"


def test_hotspot_series_shape() -> None:
    m = EventMemory()
    m.snapshot("2026-06-01", _graph("x"))
    m.snapshot("2026-06-02", _graph("x", "y"))
    series = m.hotspot_series(top_k=10)
    assert set(series) == {"2026-06-01", "2026-06-02"}
    assert "actor:x1" in series["2026-06-01"]


# ------------------------------------------------------------------ #
# cluster diffs
# ------------------------------------------------------------------ #
def test_compare_clusters_emerge_dissolve_persist() -> None:
    m = EventMemory()
    m.snapshot("2026-06-01", _graph("p", "q"))  # communities P, Q
    m.snapshot("2026-06-02", _graph("p", "r"))  # communities P, R

    diff = m.compare_clusters("2026-06-01", "2026-06-02", min_size=3)

    persisted_labels = " ".join(c.label for c in diff.persisted)
    emerged_labels = " ".join(c.label for c in diff.emerged)
    dissolved_labels = " ".join(c.label for c in diff.dissolved)

    assert "p1" in persisted_labels  # P recurs
    assert "r1" in emerged_labels  # R is new
    assert "q1" in dissolved_labels  # Q is gone


def test_compare_clusters_str() -> None:
    m = EventMemory()
    m.snapshot("d1", _graph("p"))
    m.snapshot("d2", _graph("p"))
    diff = m.compare_clusters("d1", "d2", min_size=3)
    assert all(isinstance(str(c), str) and c.status in str(c) for c in diff.changes)
