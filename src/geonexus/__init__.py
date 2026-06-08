"""GeoNexus — a causal graph engine for geopolitical, economic and financial events.

Public API::

    from geonexus import (
        GeoNexus,
        Event, Actor, Asset, Relation,
        EventType, ActorType, AssetType, RelationType,
    )
"""

from geonexus.causality.scoring import CausalPath
from geonexus.core.actor import Actor
from geonexus.core.asset import Asset
from geonexus.core.event import Event
from geonexus.core.node import NodeKind
from geonexus.core.relation import Relation
from geonexus.graph.analytics import RiskHotspot
from geonexus.graph.knowledge_graph import GeoNexus
from geonexus.memory.event_memory import (
    ClusterChange,
    ClusterDiff,
    EventMemory,
    HotspotChange,
)
from geonexus.ontology.actor_types import ActorType
from geonexus.ontology.asset_types import AssetType
from geonexus.ontology.event_types import EventType
from geonexus.ontology.relation_types import RelationType

__version__ = "0.1.0"

__all__ = [
    "Actor",
    "ActorType",
    "Asset",
    "AssetType",
    "CausalPath",
    "ClusterChange",
    "ClusterDiff",
    "Event",
    "EventMemory",
    "EventType",
    "GeoNexus",
    "HotspotChange",
    "NodeKind",
    "Relation",
    "RelationType",
    "RiskHotspot",
    "__version__",
]
