"""Build and query a typed relation graph from LLM-extracted triples.

Consumes ``world_observer_relations.json`` (subject → relation → object triples
extracted by examples/extract_relations.py) into an EventGraph, where each edge
carries the actual stated relation. Unlike the PMI co-occurrence approach, paths
here are real relation chains, e.g. China —adjusts→ Belt and Road —... → Africa.

    python examples/relation_graph.py                      # most-connected hubs + sample chains
    python examples/relation_graph.py --between China Africa
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eventgraph import Actor, EventGraph, Relation, RelationType

DATA = Path(__file__).parent / "data" / "world_observer_relations.json"
REPORT = Path("reports") / "world_observer_relations.md"


def _norm(name: str) -> str:
    n = name.strip().strip(".").replace("U.S.", "US").replace("the ", "")
    return n[:1].upper() + n[1:] if n else n


def build(triples: list[dict]) -> tuple[EventGraph, dict]:
    """EventGraph of entities; each edge stores the stated relation verb."""
    g = EventGraph()
    rel_of: dict[tuple[str, str], str] = {}
    for t in triples:
        a, b = _norm(t["subject"]), _norm(t["object"])
        if not a or not b or a == b:
            continue
        for name in (a, b):
            if f"actor:{name}" not in g:
                g.add_actor(Actor(id=name, name=name))
        g.add_relation(
            Relation(
                source=f"actor:{a}",
                target=f"actor:{b}",
                relation_type=RelationType.OTHER,
                weight=1.0,
                metadata={"rel": t["relation"], "source": t["source"]},
            )
        )
        rel_of[(a, b)] = t["relation"]
    return g, rel_of


def _edge_label(g: EventGraph, a: str, b: str) -> str:
    """Relation verb on the edge between node-ids a and b (either direction)."""
    data = g.raw.get_edge_data(a, b) or g.raw.get_edge_data(b, a) or {}
    for d in data.values():
        obj = d.get("obj")
        if obj is not None:
            return str(obj.metadata.get("rel", "->"))
    return "->"


def _resolve(g: EventGraph, query: str) -> str | None:
    """Find a node id matching ``query`` by label (exact, then substring)."""
    ql = query.strip().lower()
    nodes = list(g.nodes())
    for o in nodes:
        if g.label(o.node_id).lower() == ql:
            return o.node_id
    matches = [o.node_id for o in nodes if ql in g.label(o.node_id).lower()]
    return matches[0] if matches else None


def load_triples() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else []


def top_hubs(g: EventGraph, n: int = 12) -> list[tuple[str, int]]:
    """Most-connected entities (label, relation count)."""
    ranked = sorted(g.nodes(), key=lambda o: len(g.neighbors(o.node_id)), reverse=True)
    return [(g.label(o.node_id), len(g.neighbors(o.node_id))) for o in ranked[:n]]


def chain(g: EventGraph, a: str, b: str) -> list[tuple[str, str, str]] | None:
    """Shortest relation chain between two entities as (from, relation, to) steps."""
    import networkx as nx

    sa, sb = _resolve(g, a), _resolve(g, b)
    if not sa or not sb:
        return None
    try:
        path = nx.shortest_path(g.raw.to_undirected(), sa, sb)
    except nx.NetworkXNoPath:
        return None
    return [(g.label(x), _edge_label(g, x, y), g.label(y)) for x, y in pairwise(path)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--between", nargs=2, metavar=("A", "B"))
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    if not DATA.exists():
        print(f"{DATA} not found — run examples/extract_relations.py first.")
        return
    triples = json.loads(DATA.read_text(encoding="utf-8"))
    g, _ = build(triples)
    print(f"Relation graph: {len(g)} entities, {g.raw.number_of_edges()} relations.")

    if args.between:
        import networkx as nx

        sa, sb = _resolve(g, args.between[0]), _resolve(g, args.between[1])
        if not sa or not sb:
            missing = args.between[0] if not sa else args.between[1]
            print(f"No entity matching '{missing}' in the graph.")
            return
        und = g.raw.to_undirected()
        try:
            path = nx.shortest_path(und, sa, sb)
        except nx.NetworkXNoPath:
            print(f"No relation chain links {g.label(sa)} and {g.label(sb)}.")
            return
        print(f"\nRelation chain  {g.label(sa)} -> {g.label(sb)}:")
        for x, y in pairwise(path):
            print(f"  {g.label(x)}  --[{_edge_label(g, x, y)}]->  {g.label(y)}")
        return

    hubs = top_hubs(g, args.top)
    print("\nMost-connected entities (relation degree):")
    for label, c in hubs:
        print(f"  {label}  ({c} relations)")

    print("\nSample stated relations:")
    for t in triples[: args.top]:
        print(f"  {t['subject']}  --[{t['relation']}]->  {t['object']}")

    lines = [
        "# World Observer — relation graph (LLM-extracted)\n",
        f"_{len(triples)} stated relations from {g.raw.number_of_edges()} edges over "
        f"{len(g)} entities, extracted as subject→relation→object triples by a local LLM "
        "(not co-occurrence). Non-deterministic; grounded in WO's summaries._\n",
        "## Most-connected entities\n",
    ]
    lines += [f"- **{label}** — {c} relations" for label, c in hubs]
    lines.append("\n## Example relation chains\n")
    for a, b in [("China", "Ukraine"), ("Iran", "Israel"), ("China", "Africa"), ("US", "Ebola")]:
        steps = chain(g, a, b)
        if steps:
            txt = "  →  ".join([steps[0][0]] + [f"[{r}] {y}" for _, r, y in steps])
            lines.append(f"- **{a} → {b}:** {txt}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nMarkdown report written to {REPORT}")


if __name__ == "__main__":
    main()
