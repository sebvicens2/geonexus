"""In-memory and JSON-file storage backends."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from geonexus.graph.knowledge_graph import GeoNexus


class InMemoryStorage:
    """Keeps a single serialised snapshot in process memory.

    Useful for tests and for cheap save/restore checkpoints. The snapshot is a
    plain dict, so :meth:`load` always returns an independent copy.
    """

    def __init__(self) -> None:
        self._snapshot: dict[str, list[dict[str, Any]]] | None = None

    def save(self, graph: GeoNexus) -> None:
        self._snapshot = graph.to_dict()

    def load(self) -> GeoNexus | None:
        if self._snapshot is None:
            return None
        from geonexus.graph.knowledge_graph import GeoNexus

        return GeoNexus.from_dict(self._snapshot)


class JsonStorage:
    """Persists a graph to a JSON file on disk."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, graph: GeoNexus) -> None:
        graph.save_json(self.path)

    def load(self) -> GeoNexus | None:
        if not self.path.exists():
            return None
        from geonexus.graph.knowledge_graph import GeoNexus

        return GeoNexus.load_json(self.path)
