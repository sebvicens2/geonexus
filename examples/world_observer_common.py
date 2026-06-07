"""Shared helpers for the World Observer → EventGraph demos.

Loads the extracted real-data sample and builds an EventGraph from it. Kept
separate so both ``world_observer_demo.py`` and ``world_observer_map.py`` use the
exact same graph construction.

Graph model (reusing EventGraph's three node kinds, no new abstractions):
    - each article            -> Event   (severity = importance / 10)
    - countries/actors/orgs   -> Actor   (metadata wo_kind="actor")
    - theatre                 -> Actor   (metadata wo_kind="region")
    - category (if distinct)  -> Actor   (metadata wo_kind="category")
    - commodities             -> Asset   (metadata wo_kind="commodity")

Edges run *entity -> event* (the entity participates in / drives the event),
so a node's influence_score reflects how much significant activity it touches.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eventgraph import (
    Actor,
    ActorType,
    Asset,
    AssetType,
    Event,
    EventGraph,
    Relation,
    RelationType,
)

DATA_PATH = Path(__file__).parent / "data" / "world_observer_sample.json"

# light normalisation so "US" / "U.S." / "USA" collapse onto one node
ALIASES = {
    "US": "United States",
    "U.S.": "United States",
    "USA": "United States",
    "UK": "United Kingdom",
    "DPRK": "North Korea",
    "ROK": "South Korea",
    "PRC": "China",
}

_FALLBACK_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _canon(name: str) -> str:
    name = name.strip()
    return ALIASES.get(name, name)


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return _FALLBACK_TS
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return _FALLBACK_TS


def load_events(path: Path = DATA_PATH) -> list[dict[str, Any]]:
    """Load the extracted World Observer sample."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_graph(events: list[dict[str, Any]]) -> EventGraph:
    """Build an EventGraph from World Observer event records."""
    g = EventGraph()

    for e in events:
        severity = max(0.0, min(1.0, float(e.get("importance", 0.0)) / 10.0))
        weight = max(0.1, severity)
        event = Event(
            id=str(e["id"]),
            title=e["title"],
            timestamp=_parse_ts(e.get("published_at")),
            severity=severity,
            metadata={"category": e.get("category"), "theatre": e.get("theatre")},
        )
        g.add_event(event)

        # countries + actors + organizations -> Actor (unified by canonical name)
        names = {_canon(x) for x in (*e["countries"], *e["actors"], *e["organizations"])}
        for name in names:
            nid = f"actor:{name}"
            if nid not in g:
                g.add_actor(Actor(id=name, name=name, metadata={"wo_kind": "actor"}))
            g.add_relation(
                Relation(
                    source=nid,
                    target=event.node_id,
                    relation_type=RelationType.INVOLVES,
                    weight=weight,
                )
            )

        # theatre -> region node
        theatre = e.get("theatre")
        if theatre:
            nid = f"actor:{theatre}"
            if nid not in g:
                g.add_actor(
                    Actor(
                        id=theatre,
                        name=theatre,
                        category=ActorType.OTHER,
                        metadata={"wo_kind": "region"},
                    )
                )
            g.add_relation(
                Relation(
                    source=nid,
                    target=event.node_id,
                    relation_type=RelationType.LOCATED_IN,
                    weight=weight,
                )
            )

        # category -> node only when it carries info beyond the theatre
        category = e.get("category")
        if category and category not in (theatre, "general"):
            nid = f"actor:{category}"
            if nid not in g:
                g.add_actor(
                    Actor(
                        id=category,
                        name=category,
                        category=ActorType.OTHER,
                        metadata={"wo_kind": "category"},
                    )
                )
            g.add_relation(
                Relation(
                    source=nid,
                    target=event.node_id,
                    relation_type=RelationType.OTHER,
                    weight=weight,
                )
            )

        # commodities -> Asset
        for commodity in {c.strip() for c in e["commodities"] if c.strip()}:
            nid = f"asset:{commodity}"
            if nid not in g:
                g.add_asset(
                    Asset(
                        ticker=commodity,
                        asset_class=AssetType.COMMODITY,
                        metadata={"wo_kind": "commodity"},
                    )
                )
            g.add_relation(
                Relation(
                    source=nid,
                    target=event.node_id,
                    relation_type=RelationType.AFFECTS,
                    weight=weight,
                )
            )

    return g


def wo_kind(g: EventGraph, node_id: str) -> str:
    """Return the World Observer role tag stored on a node ('actor', 'region', ...)."""
    obj = g.get(node_id)
    kind = obj.metadata.get("wo_kind")
    if kind:
        return str(kind)
    return "event" if node_id.startswith("event:") else "node"


def subgraph(g: EventGraph, node_ids: set[str]) -> EventGraph:
    """Build a new EventGraph induced on ``node_ids`` (keeps edges among them)."""
    sub = EventGraph()
    for nid in node_ids:
        obj = g.get(nid)
        if nid.startswith("event:"):
            sub.add_event(obj)  # type: ignore[arg-type]
        elif nid.startswith("asset:"):
            sub.add_asset(obj)  # type: ignore[arg-type]
        else:
            sub.add_actor(obj)  # type: ignore[arg-type]
    for u, v, data in g.raw.edges(data=True):
        if u in node_ids and v in node_ids:
            sub.add_relation(data["obj"])
    return sub
