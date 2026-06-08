"""Storage protocol shared by all backends."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from geonexus.graph.knowledge_graph import GeoNexus


@runtime_checkable
class Storage(Protocol):
    """A minimal save/load contract for graphs.

    Implementations are intentionally tiny: serialisation lives on
    :class:`GeoNexus` itself (:meth:`to_dict` / :meth:`from_dict`), so a
    backend only needs to decide *where* the bytes go.
    """

    def save(self, graph: GeoNexus) -> None:
        """Persist ``graph``."""
        ...

    def load(self) -> GeoNexus | None:
        """Return the persisted graph, or ``None`` if nothing is stored."""
        ...
