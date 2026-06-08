"""End-to-end demo: Iran -> Hormuz -> Oil supply risk -> Oil -> Inflation -> Gold.

Run with::

    python examples/iran_oil_gold.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from geonexus import (
    Actor,
    ActorType,
    Asset,
    AssetType,
    Event,
    EventType,
    GeoNexus,
    Relation,
    RelationType,
)


def build_graph() -> GeoNexus:
    """Wire up the canonical Iran -> Gold causal chain."""
    g = GeoNexus()

    now = datetime(2026, 6, 7, tzinfo=timezone.utc)

    iran = g.add_actor(Actor(id="iran", name="Iran", category=ActorType.COUNTRY))
    hormuz = g.add_event(
        Event(
            id="hormuz_tension",
            title="Strait of Hormuz disruption",
            timestamp=now,
            event_type=EventType.GEOPOLITICAL,
            location="Strait of Hormuz",
            severity=0.8,
        )
    )
    supply = g.add_event(
        Event(
            id="oil_supply_risk",
            title="Oil supply risk",
            timestamp=now,
            event_type=EventType.SUPPLY_SHOCK,
            severity=0.7,
        )
    )
    inflation = g.add_event(
        Event(
            id="inflation",
            title="Inflationary pressure",
            timestamp=now,
            event_type=EventType.MACRO,
            severity=0.6,
        )
    )
    oil = g.add_asset(Asset(ticker="WTICO_USD", asset_class=AssetType.COMMODITY, name="WTI Crude"))
    gold = g.add_asset(Asset(ticker="XAU_USD", asset_class=AssetType.COMMODITY, name="Gold"))

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


def main() -> None:
    g = build_graph()

    print(f"Graph has {len(g)} nodes\n")

    print("Causal chains impacting XAU_USD (gold):")
    for path in g.impact("asset:XAU_USD"):
        print(f"  {path}")

    print("\nFull chain from Iran to Gold:")
    for path in g.impact("asset:XAU_USD", sources=["actor:iran"]):
        readable = " -> ".join(g.label(n) for n in path.nodes)
        print(f"  {readable}  (score={path.score:.3f})")

    print("\nMost influential nodes (causal reach):")
    ranked = sorted(
        ((g.label(o.node_id), g.influence_score(o.node_id)) for o in g.nodes()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    for name, score in ranked[:5]:
        print(f"  {name:<28} {score:.3f}")


if __name__ == "__main__":
    main()
