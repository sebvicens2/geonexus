"""Tests for the domain model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from eventgraph import Actor, Asset, Event, Relation
from eventgraph.core.node import NodeKind


def test_node_ids_are_namespaced() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert Event(id="e1", title="t", timestamp=now).node_id == "event:e1"
    assert Actor(id="iran", name="Iran").node_id == "actor:iran"
    assert Asset(ticker="XAU_USD").node_id == "asset:XAU_USD"


def test_kind_classvar() -> None:
    assert Event.kind is NodeKind.EVENT
    assert Actor.kind is NodeKind.ACTOR
    assert Asset.kind is NodeKind.ASSET


def test_severity_bounds() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        Event(id="e", title="t", timestamp=now, severity=1.5)


def test_relation_weight_bounds() -> None:
    with pytest.raises(ValidationError):
        Relation(source="a", target="b", weight=2.0)


def test_defaults() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    e = Event(id="e", title="t", timestamp=now)
    assert e.severity == 0.5
    assert e.tags == []
    assert e.metadata == {}
