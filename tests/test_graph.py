"""Tests for the GeoNexus wrapper."""

from __future__ import annotations

import pytest

from geonexus import Actor, Asset, GeoNexus, Relation, RelationType


def test_add_and_len(chain_graph: GeoNexus) -> None:
    assert len(chain_graph) == 6
    assert "actor:iran" in chain_graph
    assert "asset:XAU_USD" in chain_graph


def test_get_returns_object(chain_graph: GeoNexus) -> None:
    actor = chain_graph.get("actor:iran")
    assert isinstance(actor, Actor)
    assert actor.name == "Iran"


def test_get_unknown_raises(chain_graph: GeoNexus) -> None:
    with pytest.raises(KeyError):
        chain_graph.get("actor:nope")


def test_add_relation_requires_existing_nodes() -> None:
    g = GeoNexus()
    g.add_actor(Actor(id="iran", name="Iran"))
    with pytest.raises(KeyError):
        g.add_relation(Relation(source="actor:iran", target="asset:ghost"))


def test_connect_accepts_objects() -> None:
    g = GeoNexus()
    iran = Actor(id="iran", name="Iran")
    gold = Asset(ticker="XAU_USD")
    g.add_actor(iran)
    g.add_asset(gold)
    rel = g.connect(iran, gold, RelationType.AFFECTS, weight=0.4)
    assert rel.source == "actor:iran"
    assert rel.target == "asset:XAU_USD"
    assert g.neighbors(iran, direction="out") == ["asset:XAU_USD"]


def test_neighbors_directions(chain_graph: GeoNexus) -> None:
    assert chain_graph.neighbors("event:hormuz", direction="in") == ["actor:iran"]
    assert chain_graph.neighbors("event:hormuz", direction="out") == ["event:supply"]
    assert set(chain_graph.neighbors("event:hormuz", direction="both")) == {
        "actor:iran",
        "event:supply",
    }


def test_neighbors_bad_direction(chain_graph: GeoNexus) -> None:
    with pytest.raises(ValueError):
        chain_graph.neighbors("event:hormuz", direction="sideways")


def test_shortest_path(chain_graph: GeoNexus) -> None:
    path = chain_graph.shortest_path("actor:iran", "asset:XAU_USD")
    assert path[0] == "actor:iran"
    assert path[-1] == "asset:XAU_USD"
    assert len(path) == 6


def test_shortest_path_none(chain_graph: GeoNexus) -> None:
    # gold has no outgoing edge back to iran
    assert chain_graph.shortest_path("asset:XAU_USD", "actor:iran") == []


def test_centrality_methods(chain_graph: GeoNexus) -> None:
    for method in ("degree", "betweenness", "closeness"):
        scores = chain_graph.centrality(method)
        assert set(scores) == {n.node_id for n in chain_graph.nodes()}


def test_centrality_bad_method(chain_graph: GeoNexus) -> None:
    with pytest.raises(ValueError):
        chain_graph.centrality("nonsense")


def test_influence_score_orders_upstream_first(chain_graph: GeoNexus) -> None:
    # Iran sits at the head of the chain -> strictly more reach than gold (a sink).
    assert chain_graph.influence_score("actor:iran") > 0.0
    assert chain_graph.influence_score("asset:XAU_USD") == 0.0
    assert chain_graph.influence_score("actor:iran") > chain_graph.influence_score(
        "event:inflation"
    )


def test_nodes_filter_by_kind(chain_graph: GeoNexus) -> None:
    from geonexus.core.node import NodeKind

    assets = list(chain_graph.nodes(NodeKind.ASSET))
    assert {a.ticker for a in assets} == {"WTICO_USD", "XAU_USD"}
