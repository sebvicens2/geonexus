"""The Actor node."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from eventgraph.core.node import NodeKind
from eventgraph.ontology.actor_types import ActorType


class Actor(BaseModel):
    """An entity that participates in events (country, org, company, person...).

    Attributes:
        id: Stable, human-readable identifier (unique among actors).
        name: Display name.
        category: Kind of actor from the controlled vocabulary.
        aliases: Alternative names used to refer to the same actor.
        metadata: Arbitrary extra payload.
    """

    kind: ClassVar[NodeKind] = NodeKind.ACTOR

    id: str
    name: str
    category: ActorType = ActorType.OTHER
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def node_id(self) -> str:
        """Namespaced identifier used as the graph node key."""
        return f"{self.kind.value}:{self.id}"
