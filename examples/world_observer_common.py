"""Shared helpers for the World Observer → GeoNexus demos.

Loads the extracted real-data sample and builds an GeoNexus from it. Kept
separate so both ``world_observer_demo.py`` and ``world_observer_map.py`` use the
exact same graph construction.

Graph model (reusing GeoNexus's three node kinds, no new abstractions):
    - each article            -> Event   (severity = importance / 10)
    - countries/actors/orgs   -> Actor   (metadata wo_kind="actor")
    - theatre                 -> Actor   (metadata wo_kind="region")
    - category (if distinct)  -> Actor   (metadata wo_kind="category")
    - commodities             -> Asset   (metadata wo_kind="commodity")

Edges run *entity -> event* (the entity participates in / drives the event),
so a node's influence_score reflects how much significant activity it touches.
WO's LLM-flagged ``entities_to_watch`` add weaker, forward-looking CORRELATES
edges for entities not already involved (metadata source="watch"). Entities are
de-duplicated across case/underscore variants.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from geonexus import (
    Actor,
    ActorType,
    Asset,
    AssetType,
    Event,
    GeoNexus,
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


def _key(name: str) -> str:
    """Match key that collapses case and underscore variants (Iran/iran/united_states)."""
    return _canon(name).casefold().replace("_", " ").strip()


def _properness(name: str) -> int:
    """Display-form score: prefers 'United States' over 'united states'."""
    return sum(1 for c in name if c.isupper())


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


def build_graph(events: list[dict[str, Any]]) -> GeoNexus:
    """Build an GeoNexus from World Observer event records.

    Entities are de-duplicated across case/underscore variants, so ``Iran``,
    ``iran`` and a category ``iran`` all collapse onto one node.
    """
    g = GeoNexus()

    # pass 1: pick a canonical display name per entity key (merge variants)
    display: dict[str, str] = {}
    for e in events:
        watch = e.get("entities_to_watch", [])
        for raw in (*e["countries"], *e["actors"], *e["organizations"], *watch):
            name = _canon(raw)
            if not name:
                continue
            k = _key(name)
            if k not in display or _properness(name) > _properness(display[k]):
                display[k] = name

    def resolve(raw: str) -> str:
        return display.get(_key(raw), _canon(raw))

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
        names = {
            resolve(x) for x in (*e["countries"], *e["actors"], *e["organizations"]) if x.strip()
        }
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

        # entities_to_watch -> forward-looking "watch" links, but only for entities
        # not already involved (pure enrichment from WO's LLM, weaker weight)
        watch_names = {resolve(x) for x in e.get("entities_to_watch", []) if x.strip()} - names
        for name in watch_names:
            nid = f"actor:{name}"
            if nid not in g:
                g.add_actor(Actor(id=name, name=name, metadata={"wo_kind": "actor"}))
            g.add_relation(
                Relation(
                    source=nid,
                    target=event.node_id,
                    relation_type=RelationType.CORRELATES,
                    weight=weight * 0.7,
                    metadata={"source": "watch"},
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

        # category -> node only when it adds info beyond the theatre AND is not
        # just a duplicate of a country/actor (e.g. category "iran" == actor Iran)
        category = e.get("category")
        if category and category not in (theatre, "general") and _key(category) not in display:
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


def wo_kind(g: GeoNexus, node_id: str) -> str:
    """Return the World Observer role tag stored on a node ('actor', 'region', ...)."""
    obj = g.get(node_id)
    kind = obj.metadata.get("wo_kind")
    if kind:
        return str(kind)
    return "event" if node_id.startswith("event:") else "node"


def subgraph(g: GeoNexus, node_ids: set[str]) -> GeoNexus:
    """Build a new GeoNexus induced on ``node_ids`` (keeps edges among them)."""
    sub = GeoNexus()
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
