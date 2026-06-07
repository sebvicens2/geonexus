"""Pluggable persistence backends for an :class:`EventGraph`."""

from eventgraph.storage.base import Storage
from eventgraph.storage.memory import InMemoryStorage, JsonStorage

__all__ = ["InMemoryStorage", "JsonStorage", "Storage"]
