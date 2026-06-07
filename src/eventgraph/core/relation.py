"""The Relation (directed edge) between two nodes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from eventgraph.ontology.relation_types import RelationType


class Relation(BaseModel):
    """A directed, weighted link between two nodes.

    ``source`` and ``target`` are graph ``node_id`` strings (the namespaced
    ``"<kind>:<id>"`` form). The :class:`~eventgraph.graph.knowledge_graph.EventGraph`
    helpers accept node objects directly and resolve them for you.

    Attributes:
        source: ``node_id`` of the origin node.
        target: ``node_id`` of the destination node.
        relation_type: Type from the controlled vocabulary.
        weight: Strength/confidence of the link in ``[0, 1]``.
        metadata: Arbitrary extra payload.
    """

    source: str
    target: str
    relation_type: RelationType = RelationType.AFFECTS
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
