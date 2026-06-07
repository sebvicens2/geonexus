"""Tests for the causality engine."""

from __future__ import annotations

import pytest

from eventgraph import EventGraph
from eventgraph.causality.scoring import path_score


def test_path_score_single_edge_is_weight() -> None:
    assert path_score([0.8]) == pytest.approx(0.8)


def test_path_score_decays_with_length() -> None:
    # two equal edges score lower than one, thanks to decay
    one = path_score([0.9])
    two = path_score([0.9, 0.9])
    assert two < one
    assert two == pytest.approx(0.9 * 0.9 * 0.85)


def test_path_score_empty() -> None:
    assert path_score([]) == 0.0


def test_impact_finds_chain_to_gold(chain_graph: EventGraph) -> None:
    paths = chain_graph.impact("asset:XAU_USD")
    assert paths, "expected at least one causal chain"
    # every returned chain must terminate at the requested target
    assert all(p.target == "asset:XAU_USD" for p in paths)
    # results are sorted by descending score
    scores = [p.score for p in paths]
    assert scores == sorted(scores, reverse=True)


def test_impact_full_chain_from_iran(chain_graph: EventGraph) -> None:
    paths = chain_graph.impact("asset:XAU_USD", sources=["actor:iran"])
    assert len(paths) == 1
    full = paths[0]
    assert full.nodes == (
        "actor:iran",
        "event:hormuz",
        "event:supply",
        "asset:WTICO_USD",
        "event:inflation",
        "asset:XAU_USD",
    )
    assert full.length == 5
    expected = 0.9 * 0.8 * 0.85 * 0.7 * 0.75 * (0.85**4)
    assert full.score == pytest.approx(expected)


def test_impact_respects_max_depth(chain_graph: EventGraph) -> None:
    shallow = chain_graph.impact("asset:XAU_USD", sources=["actor:iran"], max_depth=2)
    assert shallow == []  # the only iran->gold path is 5 hops


def test_impact_unknown_target(chain_graph: EventGraph) -> None:
    assert chain_graph.impact("asset:DOES_NOT_EXIST") == []


def test_impact_top_k(chain_graph: EventGraph) -> None:
    assert len(chain_graph.impact("asset:XAU_USD", top_k=2)) <= 2
