"""Canonical relation (edge) types.

Edges are directed. For causal types (``CAUSES``, ``DISRUPTS``, ``AFFECTS``,
``SUPPLIES``) the direction is *cause -> effect*, which is what the causality
engine walks when computing impact paths.
"""

from enum import Enum


class RelationType(str, Enum):
    """Type of directed relation between two nodes."""

    CAUSES = "causes"
    AFFECTS = "affects"
    DISRUPTS = "disrupts"
    SUPPLIES = "supplies"
    CORRELATES = "correlates"
    INVOLVES = "involves"
    LOCATED_IN = "located_in"
    OTHER = "other"
