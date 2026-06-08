"""Pluggable persistence backends for an :class:`GeoNexus`."""

from geonexus.storage.base import Storage
from geonexus.storage.memory import InMemoryStorage, JsonStorage

__all__ = ["InMemoryStorage", "JsonStorage", "Storage"]
