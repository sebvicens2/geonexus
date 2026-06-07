"""Tests for the visualisation helpers (matplotlib path + GraphML export)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend for CI

from eventgraph import EventGraph
from eventgraph.visualization import draw, export_graphml


def test_draw_returns_axes(chain_graph: EventGraph) -> None:
    ax = draw(chain_graph)
    assert ax is not None
    # one PathCollection of nodes should have been drawn
    assert len(ax.collections) >= 1


def test_export_graphml(chain_graph: EventGraph, tmp_path: Path) -> None:
    out = export_graphml(chain_graph, tmp_path / "graph.graphml")
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "graphml" in content
    assert "actor:iran" in content
