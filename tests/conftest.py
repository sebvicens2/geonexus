"""Shared fixtures."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from eventgraph import (
    Actor,
    ActorType,
    Asset,
    AssetType,
    Event,
    EventGraph,
    EventType,
    Relation,
    RelationType,
)


@pytest.fixture
def chain_graph() -> EventGraph:
    """Iran -> Hormuz -> Oil supply risk -> Oil -> Inflation -> Gold."""
    g = EventGraph()
    now = datetime(2026, 6, 7, tzinfo=timezone.utc)

    iran = g.add_actor(Actor(id="iran", name="Iran", category=ActorType.COUNTRY))
    hormuz = g.add_event(
        Event(
            id="hormuz", title="Hormuz disruption", timestamp=now, event_type=EventType.GEOPOLITICAL
        )
    )
    supply = g.add_event(
        Event(
            id="supply", title="Oil supply risk", timestamp=now, event_type=EventType.SUPPLY_SHOCK
        )
    )
    inflation = g.add_event(
        Event(id="inflation", title="Inflation", timestamp=now, event_type=EventType.MACRO)
    )
    oil = g.add_asset(Asset(ticker="WTICO_USD", asset_class=AssetType.COMMODITY))
    gold = g.add_asset(Asset(ticker="XAU_USD", asset_class=AssetType.COMMODITY))

    g.add_relation(
        Relation(source=iran, target=hormuz, relation_type=RelationType.INVOLVES, weight=0.9)
    )
    g.add_relation(
        Relation(source=hormuz, target=supply, relation_type=RelationType.CAUSES, weight=0.8)
    )
    g.add_relation(
        Relation(source=supply, target=oil, relation_type=RelationType.AFFECTS, weight=0.85)
    )
    g.add_relation(
        Relation(source=oil, target=inflation, relation_type=RelationType.CAUSES, weight=0.7)
    )
    g.add_relation(
        Relation(source=inflation, target=gold, relation_type=RelationType.AFFECTS, weight=0.75)
    )
    return g
