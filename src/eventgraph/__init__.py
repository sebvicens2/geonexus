"""EventGraph — a causal graph engine for geopolitical, economic and financial events.

Public API::

    from eventgraph import (
        EventGraph,
        Event, Actor, Asset, Relation,
        EventType, ActorType, AssetType, RelationType,
    )
"""

from eventgraph.causality.scoring import CausalPath
from eventgraph.core.actor import Actor
from eventgraph.core.asset import Asset
from eventgraph.core.event import Event
from eventgraph.core.node import NodeKind
from eventgraph.core.relation import Relation
from eventgraph.graph.knowledge_graph import EventGraph
from eventgraph.ontology.actor_types import ActorType
from eventgraph.ontology.asset_types import AssetType
from eventgraph.ontology.event_types import EventType
from eventgraph.ontology.relation_types import RelationType

__version__ = "0.1.0"

__all__ = [
    "Actor",
    "ActorType",
    "Asset",
    "AssetType",
    "CausalPath",
    "Event",
    "EventGraph",
    "EventType",
    "NodeKind",
    "Relation",
    "RelationType",
    "__version__",
]
