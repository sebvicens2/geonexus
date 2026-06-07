"""Canonical event categories.

These are intentionally broad. The ontology is meant to grow; downstream
projects can subclass or extend it without touching the graph layer.
"""

from enum import Enum


class EventType(str, Enum):
    """High-level classification of an event."""

    GEOPOLITICAL = "geopolitical"
    CONFLICT = "conflict"
    SUPPLY_SHOCK = "supply_shock"
    MACRO = "macro"
    ECONOMIC = "economic"
    FINANCIAL = "financial"
    REGULATORY = "regulatory"
    NEWS = "news"
    OTHER = "other"
