"""The Event node."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from eventgraph.core.node import NodeKind
from eventgraph.ontology.event_types import EventType


class Event(BaseModel):
    """A discrete real-world event with a time, place and severity.

    Attributes:
        id: Stable, human-readable identifier (unique among events).
        title: Short headline.
        timestamp: When the event occurred (or was first reported).
        event_type: Category from the controlled vocabulary.
        description: Free-form details.
        location: Optional place name (country, region, city...).
        severity: Normalised importance in ``[0, 1]``.
        tags: Free-form labels for filtering/search.
        metadata: Arbitrary extra payload (kept opaque by the library).
    """

    kind: ClassVar[NodeKind] = NodeKind.EVENT

    id: str
    title: str
    timestamp: datetime
    event_type: EventType = EventType.OTHER
    description: str = ""
    location: str | None = None
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def node_id(self) -> str:
        """Namespaced identifier used as the graph node key."""
        return f"{self.kind.value}:{self.id}"
