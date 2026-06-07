# EventGraph

[![CI](https://github.com/sebvicens2/eventgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/sebvicens2/eventgraph/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/badge/ruff-lint%20%2B%20format-orange)](https://docs.astral.sh/ruff/)

> **A causal graph engine for geopolitical, economic and financial events.**

EventGraph represents **events**, **actors** and **assets** as a typed, directed
graph, links them with weighted causal relations, and then *reasons* over that
graph — tracing which assets an event can reach, ranking the most influential
players, and surfacing the most probable causal chains.

It is a small, standalone, well-typed library with no ties to any data pipeline.
Install it and use it from any Python project.

```python
from eventgraph import EventGraph, Actor, Asset, RelationType

g = EventGraph()
iran = g.add_actor(Actor(id="iran", name="Iran"))
gold = g.add_asset(Asset(ticker="XAU_USD"))
g.connect(iran, gold, RelationType.AFFECTS, weight=0.4)

g.impact("asset:XAU_USD")   # → ranked causal chains leading to gold
```

---

## Why EventGraph?

Most "event graphs" stop at *storing* relations. EventGraph is built as a small
**causal reasoning layer** — the graph is the substrate, the answers are the point.
It is designed to answer questions like:

- **Which assets** could be impacted by this event?
- **What are the plausible causal paths** from a cause to an asset?
- **Which actors** are the most connected / influential?
- **How far** does a node's influence radiate through the network?

Design principles:

- **Deterministic by default** — the MVP needs *no LLM*. Scores are reproducible
  and explainable (a path's score is just its discounted edge-weight product).
- **Typed and validated** — Pydantic v2 models, `mypy --strict`, `py.typed`.
- **Layered & extensible** — `core → ontology → graph → causality → storage/viz`.
  Each layer depends only on the ones below it, so narrative analysis, geopolitical
  scoring, temporal graphs or an LLM layer can be added *on top* without a rewrite.
- **Light dependencies** — `pydantic`, `networkx`, `matplotlib`. Interactive
  visualisation (`pyvis`) is an optional extra.

---

## Installation

```bash
pip install eventgraph            # core: pydantic, networkx, matplotlib
pip install eventgraph[viz]       # + interactive HTML export via pyvis
```

---

## Quickstart

```python
from datetime import datetime, timezone
from eventgraph import (
    EventGraph, Actor, Asset, Event, Relation,
    ActorType, AssetType, EventType, RelationType,
)

g = EventGraph()

# add nodes (each returns its namespaced node_id, e.g. "actor:iran")
iran = g.add_actor(Actor(id="iran", name="Iran", category=ActorType.COUNTRY))
gold = g.add_asset(Asset(ticker="XAU_USD", asset_class=AssetType.COMMODITY))
infl = g.add_event(Event(id="inflation", title="Inflation",
                         timestamp=datetime.now(timezone.utc),
                         event_type=EventType.MACRO))

# relate them (cause → effect, weighted 0..1)
g.add_relation(Relation(source=infl, target=gold,
                        relation_type=RelationType.AFFECTS, weight=0.75))

# explore
g.neighbors(gold, direction="in")        # ['event:inflation']
g.shortest_path(infl, gold)              # ['event:inflation', 'asset:XAU_USD']
g.centrality("betweenness")              # {node_id: score, ...}
g.influence_score(iran)                  # causal reach of a node

# reason
for path in g.impact("asset:XAU_USD"):
    print(path)                          # ranked causal chains → gold

# persist
g.save_json("graph.json")
g2 = EventGraph.load_json("graph.json")
```

---

## Example: Iran → Hormuz → Oil → Inflation → Gold

```python
g.impact("asset:XAU_USD", sources=["actor:iran"])
```

```text
Iran → Strait of Hormuz disruption → Oil supply risk → WTICO_USD → Inflation → XAU_USD  (score=0.168)
```

```text
Causal chains impacting XAU_USD (gold):
  inflation → XAU_USD                                              (score=0.750)
  WTICO_USD → inflation → XAU_USD                                  (score=0.446)
  oil_supply_risk → WTICO_USD → inflation → XAU_USD                (score=0.322)
  hormuz → oil_supply_risk → WTICO_USD → inflation → XAU_USD       (score=0.219)
  iran → hormuz → oil_supply_risk → WTICO_USD → inflation → XAU_USD (score=0.168)

Most influential nodes (causal reach):
  Iran                         2.385
  Strait of Hormuz disruption  1.941
  Oil supply risk              1.678
```

Run the full demo:

```bash
python examples/iran_oil_gold.py
```

### How the score works

A chain's score is the **product of its edge weights**, discounted by a per-hop
`decay` factor (default `0.85`) so shorter, stronger chains rank above long,
speculative ones:

```
score = (w₁ · w₂ · … · wₙ) · decay^(n-1)
```

`impact(target)` enumerates every chain that ends at `target` and returns them
ranked by score. `influence_score(node)` sums the best forward-path scores from a
node to all of its descendants.

---

## Visualisation

`draw()` renders the graph with matplotlib (a core dependency) — enough for any
demo or notebook. Nodes are coloured by kind: **event** (red), **actor** (blue),
**asset** (green).

![EventGraph causal chain: Iran → Hormuz → Oil → Inflation → Gold](assets/example_graph.png)

```python
from eventgraph.visualization import draw, export_html, export_graphml

draw(g)                          # → matplotlib Axes
export_html(g, "graph.html")     # interactive (requires eventgraph[viz])
export_graphml(g, "graph.graphml")  # → Gephi / yEd
```

---

## Features

| Area | What you get |
| --- | --- |
| **Domain model** | `Event`, `Actor`, `Asset`, `Relation` — Pydantic v2, validated, JSON-ready |
| **Ontology** | Controlled vocabularies: `EventType`, `ActorType`, `AssetType`, `RelationType` |
| **Graph** | `EventGraph` over a `networkx.MultiDiGraph`: `add_*`, `get`, `neighbors`, `shortest_path` |
| **Metrics** | `centrality` (degree / betweenness / closeness) + `influence_score` (causal reach) |
| **Causality** | `impact(target)` — deterministic, ranked, explainable causal chains |
| **Storage** | In-memory + JSON backends behind a `Storage` protocol; canonical (deterministic) serialisation |
| **Visualisation** | matplotlib (core) · pyvis interactive HTML (extra) · GraphML export |
| **Quality** | `mypy --strict`, `ruff`, `py.typed`, ~96% test coverage, CI on 3.11 & 3.12 |

---

## Roadmap — Phase 2

The core is deliberately minimal. Planned work builds *on top* of it without
touching the existing layers:

- **Event similarity** — embed/compare events to answer *"what looks like this?"*
- **Temporal graphs** — time-sliced views to watch a crisis evolve and detect
  emerging weak signals in a region.
- **Geopolitical scoring** — actor/region risk metrics derived from graph structure.
- **Market-impact modelling** — turn causal chains into directional asset signals.
- **Narrative analysis** — cluster and contrast competing narratives over events.
- **Optional LLM layer** — assisted relation extraction and chain explanation,
  strictly additive to the deterministic core.

---

## Development

This project uses [uv](https://docs.astral.sh/uv/), `ruff`, `mypy` and `pytest`.

```bash
# set up an isolated environment with all extras
uv sync --extra dev --extra viz

# lint, format-check, type-check, test
uv run ruff check .
uv run ruff format .          # use --check in CI
uv run mypy
uv run pytest                 # coverage is on by default

# build distributables
uv build
```

CI runs the same checks on Python **3.11** and **3.12** (see
[`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

### Project layout

```
src/eventgraph/
├── core/          # Event, Actor, Asset, Relation (pydantic models)
├── ontology/      # controlled vocabularies (event/actor/asset/relation types)
├── graph/         # EventGraph — the public API over networkx
├── causality/     # propagation + scoring (the reasoning engine)
├── storage/       # in-memory & JSON backends (Storage protocol)
└── visualization/ # matplotlib (default) + pyvis (optional) + GraphML
```

---

## License

[MIT](LICENSE) © Sebastien Vicens
