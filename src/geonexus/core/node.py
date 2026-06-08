"""Shared building blocks for graph nodes.

Every node object (Event, Actor, Asset) exposes a stable ``node_id`` of the
form ``"<kind>:<identifier>"``. Namespacing by kind guarantees that, say, an
asset ticker can never collide with an actor id inside a single graph.
"""

from enum import Enum


class NodeKind(str, Enum):
    """Discriminator for the three node types stored in the graph."""

    EVENT = "event"
    ACTOR = "actor"
    ASSET = "asset"
