"""Tests for serialisation and storage backends."""

from __future__ import annotations

from pathlib import Path

from eventgraph import EventGraph
from eventgraph.storage import InMemoryStorage, JsonStorage, Storage


def _assert_equivalent(a: EventGraph, b: EventGraph) -> None:
    assert a.to_dict() == b.to_dict()


def test_roundtrip_dict(chain_graph: EventGraph) -> None:
    restored = EventGraph.from_dict(chain_graph.to_dict())
    _assert_equivalent(chain_graph, restored)
    assert len(restored) == 6


def test_roundtrip_json_file(chain_graph: EventGraph, tmp_path: Path) -> None:
    target = tmp_path / "graph.json"
    chain_graph.save_json(target)
    restored = EventGraph.load_json(target)
    _assert_equivalent(chain_graph, restored)


def test_in_memory_storage(chain_graph: EventGraph) -> None:
    store = InMemoryStorage()
    assert store.load() is None
    store.save(chain_graph)
    restored = store.load()
    assert restored is not None
    _assert_equivalent(chain_graph, restored)


def test_json_storage(chain_graph: EventGraph, tmp_path: Path) -> None:
    store = JsonStorage(tmp_path / "g.json")
    assert store.load() is None
    store.save(chain_graph)
    restored = store.load()
    assert restored is not None
    _assert_equivalent(chain_graph, restored)


def test_backends_satisfy_protocol(tmp_path: Path) -> None:
    assert isinstance(InMemoryStorage(), Storage)
    assert isinstance(JsonStorage(tmp_path / "g.json"), Storage)
