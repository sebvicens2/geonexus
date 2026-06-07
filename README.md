# EventGraph

> A causal graph engine for geopolitical, economic and financial events.

EventGraph lets you represent **events**, **actors** and **assets** as a typed,
directed graph, link them with weighted causal relations, and then *reason* over
that graph — find which assets an event can reach, trace the most probable causal
chains, rank the most influential players, and visualise the whole thing.

It is a standalone, dependency-light library with no ties to any particular data
pipeline. Install it and use it from any Python project.

```python
from eventgraph import EventGraph, Actor, Asset, Event, Relation, RelationType

g = EventGraph()
iran = g.add_actor(Actor(id="iran", name="Iran"))
gold = g.add_asset(Asset(ticker="XAU_USD"))
g.connect(iran, gold, RelationType.AFFECTS, weight=0.4)

g.impact("asset:XAU_USD")   # -> ranked causal chains leading to gold
```

## Why

Most "event graphs" stop at storing relations. EventGraph is built as a small
**causal reasoning layer**, designed to answer questions like:

- Which assets could be impacted by this event?
- What are the plausible causal paths?
- Which actors are the most connected / influential?
- How does a node's influence radiate through the network?

The MVP is fully deterministic — **no LLM required**. The architecture is laid
out so that narrative analysis, geopolitical scoring, temporal graphs and an
optional LLM layer can be added later without reworking the core.

## Installation

```bash
pip install eventgraph            # core (pydantic, networkx, matplotlib)
pip install eventgraph[viz]       # + interactive HTML export via pyvis
```

Local development (using [uv](https://docs.astral.sh/uv/)):

```bash
uv venv && uv pip install -e ".[dev,viz]"
pytest
```

## Concepts

| Object | Identified by | Key attributes |
| --- | --- | --- |
| `Event` | `id` | `title`, `timestamp`, `event_type`, `severity`, `location`, `tags`, `metadata` |
| `Actor` | `id` | `name`, `category`, `aliases` |
| `Asset` | `ticker` | `asset_class`, `region` |
| `Relation` | `source` → `target` | `relation_type`, `weight ∈ [0, 1]` |

Every node has a namespaced `node_id` of the form `"<kind>:<id>"`
(`"actor:iran"`, `"asset:XAU_USD"`), so identifiers never collide across kinds.

Edges are **directed** in causal order (*cause → effect*) and **weighted** by
strength/confidence. The graph is a `networkx.MultiDiGraph`, so two nodes can
hold several differently-typed relations.

## The causal model

A chain's score is the **product of its edge weights**, discounted by a per-hop
`decay` factor (default `0.85`) so shorter, stronger chains rank above long
speculative ones:

```
score = (w₁ · w₂ · … · wₙ) · decay^(n-1)
```

`impact(target)` enumerates every chain that ends at `target` and returns them
ranked by score. `influence_score(node)` sums the best forward-path scores from a
node to all of its descendants.

## Example: Iran → Gold

```python
g.impact("asset:XAU_USD", sources=["actor:iran"])
# Iran -> Hormuz disruption -> Oil supply risk -> WTI -> Inflation -> Gold  (score=...)
```

Run the full demo:

```bash
python examples/iran_oil_gold.py
```

## API at a glance

```python
g = EventGraph()

# build
g.add_event(event); g.add_actor(actor); g.add_asset(asset)
g.add_relation(Relation(...))               # or: g.connect(a, b, RelationType.CAUSES, 0.8)

# explore
g.neighbors(node, direction="both")         # "in" | "out" | "both"
g.shortest_path(source, target)
g.centrality("degree")                      # degree | betweenness | closeness | pagerank
g.influence_score(node)

# reason
g.impact(target, sources=None, max_depth=5, top_k=10)

# persist
g.save_json("graph.json"); EventGraph.load_json("graph.json")

# visualise
from eventgraph.visualization import draw, export_html, export_graphml
draw(g)                                      # matplotlib Axes
export_html(g, "graph.html")                 # interactive (needs eventgraph[viz])
export_graphml(g, "graph.graphml")           # Gephi / yEd
```

## Project layout

```
src/eventgraph/
├── core/          # Event, Actor, Asset, Relation (pydantic models)
├── ontology/      # controlled vocabularies (event/actor/asset/relation types)
├── graph/         # EventGraph — the public API over networkx
├── causality/     # propagation + scoring (the reasoning engine)
├── storage/       # in-memory & JSON backends (Storage protocol)
└── visualization/ # matplotlib (default) + pyvis (optional) + GraphML
```

## Roadmap

The core is deliberately small. Planned extensions build *on top* without
touching it: narrative analysis, geopolitical scoring, market-impact models,
temporal graphs, an optional LLM layer, and distributed/shared graphs.

## License

MIT
