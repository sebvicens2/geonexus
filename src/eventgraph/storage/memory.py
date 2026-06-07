"""In-memory and JSON-file storage backends."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eventgraph.graph.knowledge_graph import EventGraph


class InMemoryStorage:
    """Keeps a single serialised snapshot in process memory.

    Useful for tests and for cheap save/restore checkpoints. The snapshot is a
    plain dict, so :meth:`load` always returns an independent copy.
    """

    def __init__(self) -> None:
        self._snapshot: dict[str, list[dict[str, Any]]] | None = None

    def save(self, graph: EventGraph) -> None:
        self._snapshot = graph.to_dict()

    def load(self) -> EventGraph | None:
        if self._snapshot is None:
            return None
        from eventgraph.graph.knowledge_graph import EventGraph

        return EventGraph.from_dict(self._snapshot)


class JsonStorage:
    """Persists a graph to a JSON file on disk."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, graph: EventGraph) -> None:
        graph.save_json(self.path)

    def load(self) -> EventGraph | None:
        if not self.path.exists():
            return None
        from eventgraph.graph.knowledge_graph import EventGraph

        return EventGraph.load_json(self.path)
