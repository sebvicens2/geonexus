"""Concrete EventGraph results from the real World Observer sample.

Builds the graph from ``examples/data/world_observer_sample.json`` and prints a
readable report (overview, influence, risk hotspots, emerging clusters, causal
paths to a few assets). Also writes ``reports/world_observer_results.md``.

No LLM. Every number below is computed by EventGraph from real events.

Run:
    python examples/results_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import networkx as nx
from world_observer_common import build_graph, load_events, wo_kind

from eventgraph import Asset, AssetType, EventGraph, Relation, RelationType

REPORT_PATH = Path("reports") / "world_observer_results.md"

# ----------------------------------------------------------------------------- #
# Heuristic asset overlay (transparent, no LLM).
# Maps World Observer theatres/categories to tradable assets so we can trace
# real actor -> real event -> asset causal chains. The chains themselves only
# ever traverse genuine WO entities and events; this map just adds the leaves.
# ----------------------------------------------------------------------------- #
ASSETS: dict[str, tuple[str, AssetType]] = {
    "WTICO_USD": ("WTI Crude Oil", AssetType.COMMODITY),
    "XAU_USD": ("Gold", AssetType.COMMODITY),
    "SPY": ("S&P 500", AssetType.EQUITY),
    "USD": ("US Dollar", AssetType.FX),
}
MAJOR_MIN_NODES = 20  # clusters smaller than this are single-story noise

OIL_THEATRES = {"gulf_iran", "strait_hormuz", "maritime_chokepoints", "iran_asia_oil_trade"}
CONFLICT_THEATRES = {
    "gulf_iran",
    "israel_gaza",
    "israel_hezbollah_lebanon",
    "ukraine_russia",
    "taiwan_strait",
    "korean_peninsula",
    "global_crisis",
    "strait_hormuz",
}


def add_asset_overlay(g: EventGraph) -> list[str]:
    """Wire heuristic asset leaves onto the graph. Returns the asset node ids."""
    for ticker, (name, cls) in ASSETS.items():
        g.add_asset(Asset(ticker=ticker, asset_class=cls, name=name))

    def link(event_id: str, ticker: str, weight: float) -> None:
        g.add_relation(
            Relation(
                source=event_id,
                target=f"asset:{ticker}",
                relation_type=RelationType.AFFECTS,
                weight=max(0.05, min(1.0, weight)),
            )
        )

    for ev in [o for o in g.nodes() if wo_kind(g, o.node_id) == "event"]:
        eid = ev.node_id
        tags = {str(ev.metadata.get("theatre")), str(ev.metadata.get("category"))}
        sev = ev.severity  # type: ignore[union-attr]
        us_linked = "actor:United States" in g.neighbors(eid, direction="in")

        if tags & OIL_THEATRES or any("oil" in t or "energy" in t for t in tags):
            link(eid, "WTICO_USD", sev * 0.9)
        if tags & CONFLICT_THEATRES:  # risk-off safe havens
            link(eid, "XAU_USD", sev * 0.6)
            link(eid, "USD", sev * 0.5)
        if us_linked or any("us_" in t for t in tags):
            link(eid, "SPY", sev * 0.5)
            link(eid, "USD", sev * 0.4)
    return [f"asset:{t}" for t in ASSETS]


# ----------------------------------------------------------------------------- #
# data collection
# ----------------------------------------------------------------------------- #
def node_type(g: EventGraph, node_id: str) -> str:
    return wo_kind(g, node_id)


def collect(g: EventGraph) -> dict[str, object]:
    counts = {"event": 0, "actor": 0, "region": 0, "category": 0, "commodity": 0}
    for o in g.nodes():
        counts[node_type(g, o.node_id)] = counts.get(node_type(g, o.node_id), 0) + 1

    overview = {
        "events": counts["event"],
        "actors": counts["actor"],
        "regions": counts["region"],
        "categories": counts["category"],
        "relations": g.raw.number_of_edges(),
        "nodes": len(g),
        "density": nx.density(g.raw),
    }

    influence = sorted(
        (
            (o.node_id, g.label(o.node_id), node_type(g, o.node_id), g.influence_score(o.node_id))
            for o in g.nodes()
        ),
        key=lambda r: r[3],
        reverse=True,
    )[:10]

    hotspots = [
        (s.node_id, g.label(s.node_id), node_type(g, s.node_id), s)
        for s in g.risk_hotspots(top_k=10)
    ]

    all_clusters = g.emerging_clusters(min_size=5)
    clusters = []
    for cluster in all_clusters:
        if len(cluster) < MAJOR_MIN_NODES:  # keep only the major theatres
            continue
        entities = [n for n in cluster if not n.startswith("event:")]
        events = [n for n in cluster if n.startswith("event:")]
        entities.sort(key=g.influence_score, reverse=True)
        events.sort(key=lambda n: g.get(n).severity, reverse=True)  # type: ignore[union-attr]
        regions = [g.label(n) for n in entities if node_type(g, n) == "region"]
        top_entities = [g.label(n) for n in entities[:5]]
        name = " / ".join(top_entities[:3])
        interpretation = _interpret(g, entities, events, regions)
        clusters.append(
            {
                "name": name,
                "size": len(cluster),
                "entities": top_entities,
                "events": [g.label(n)[:70] for n in events[:3]],
                "n_events": len(events),
                "interpretation": interpretation,
            }
        )

    return {
        "overview": overview,
        "influence": influence,
        "hotspots": hotspots,
        "clusters": clusters,
        "total_clusters": len(all_clusters),
    }


def _interpret(g: EventGraph, entities: list[str], events: list[str], regions: list[str]) -> str:
    countries = [g.label(n) for n in entities if node_type(g, n) == "actor"][:3]
    region_txt = f" in the {regions[0]} theatre" if regions else ""
    who = ", ".join(countries) if countries else "multiple actors"
    return f"{who}{region_txt}, spanning {len(events)} events."


def causal_paths(g: EventGraph) -> dict[str, list[list[str]]]:
    sources = [o.node_id for o in g.nodes() if o.node_id.startswith("actor:")]
    out: dict[str, list[list[str]]] = {}
    for ticker in ASSETS:
        target = f"asset:{ticker}"
        paths = g.impact(target, sources=sources, max_depth=3, top_k=40)
        rendered = []
        seen_events: set[str] = set()
        for p in paths:
            mid = p.nodes[1] if len(p.nodes) > 1 else p.nodes[0]
            if mid in seen_events:  # one chain per intermediate event, for variety
                continue
            seen_events.add(mid)
            chain = [g.label(n)[:46] for n in p.nodes]
            rendered.append([" → ".join(chain), f"{p.score:.3f}"])
            if len(rendered) >= 4:
                break
        out[ticker] = rendered
    return out


# ----------------------------------------------------------------------------- #
# rendering
# ----------------------------------------------------------------------------- #
def render_console(data: dict[str, object], paths: dict[str, list[list[str]]]) -> None:
    ov = data["overview"]

    def head(t: str) -> None:
        print(f"\n{'=' * 70}\n{t}\n{'=' * 70}")

    window, n_days = data["window"]  # type: ignore[misc]
    head("1. OVERVIEW")
    print(f"  Window            {window}  ({n_days} days)")
    print(f"  Events            {ov['events']}")
    print(f"  Actors            {ov['actors']}")
    print(f"  Regions/theatres  {ov['regions']}")
    print(f"  Categories        {ov['categories']}")
    print(f"  Total nodes       {ov['nodes']}")
    print(f"  Relations         {ov['relations']}")
    print(f"  Graph density     {ov['density']:.4f}")

    head("2. TOP 10 INFLUENCE  (≈ media coverage volume, not real-world influence)")
    print(f"  {'#':>2}  {'node':<26} {'type':<10} {'influence':>10}")
    for i, (_, label, typ, score) in enumerate(data["influence"], 1):
        print(f"  {i:>2}  {label[:26]:<26} {typ:<10} {score:>10.2f}")

    head("3. TOP 10 ATTENTION HOTSPOTS  (media attention / connectivity, NOT real-world risk)")
    print(f"  {'#':>2}  {'node':<24} {'type':<9} {'score':>6} {'cen':>5} {'inf':>5} {'den':>5}")
    for i, (_, label, typ, s) in enumerate(data["hotspots"], 1):
        print(
            f"  {i:>2}  {label[:24]:<24} {typ:<9} {s.score:>6.3f} "
            f"{s.centrality:>5.2f} {s.influence:>5.2f} {s.density:>5.2f}"
        )

    head("4. EMERGING CLUSTERS")
    for i, c in enumerate(data["clusters"], 1):
        print(f"\n  Cluster {i}: {c['name']}")
        print(f"    size           {c['size']} nodes ({c['n_events']} events)")
        print(f"    main nodes     {', '.join(c['entities'])}")
        print(f"    sample events  {c['events'][0] if c['events'] else '—'}")
        print(f"    interpretation {c['interpretation']}")

    head("5. CAUSAL PATHS TO ASSETS  (ILLUSTRATIVE / heuristic — NOT predictive)")
    print("  Chains = real actor co-mentioned in a real event → asset.")
    print("  The event→asset link is HAND-MAPPED (theatre→asset), not inferred;")
    print("  the score is event importance, not a market-impact estimate.")
    for ticker, (name, _) in ASSETS.items():
        print(f"\n  {ticker} ({name}):")
        if not paths[ticker]:
            print("    (no chains)")
        for chain, score in paths[ticker]:
            print(f"    [{score}] {chain}")

    n_clusters = len(data["clusters"])
    n_hot = len(data["hotspots"])
    n_events = data["overview"]["events"]  # type: ignore[index]
    total = data["total_clusters"]
    window, n_days = data["window"]  # type: ignore[misc]
    print(f"\n{'=' * 70}")
    print(
        f"EventGraph organised {n_events} real World Observer events ({n_days} days) "
        f"into {n_clusters} major media clusters (of {total} communities) "
        f"and ranked {n_hot} attention hotspots."
    )
    print("Note: these metrics describe MEDIA ATTENTION, not real-world risk or causality.")
    print("=" * 70)


def render_markdown(data: dict[str, object], paths: dict[str, list[list[str]]]) -> str:
    ov = data["overview"]
    lines: list[str] = []
    window, n_days = data["window"]  # type: ignore[misc]
    lines.append("# EventGraph — World Observer results\n")
    lines.append(
        "_Generated by `examples/results_report.py` from real World Observer "
        "events. No LLM; every figure is computed by EventGraph._\n"
    )
    lines.append(
        "> **What this measures (honest caveats).** This is a *descriptive* view of "
        "**media attention**, not a risk or forecasting model.\n"
        "> - *Influence* ≈ how much an entity is covered (it correlates ~0.93 with raw "
        "degree); it is **not** real-world influence.\n"
        "> - *Attention hotspots* blend connectivity + coverage + local density; "
        "they are **not** real-world risk.\n"
        "> - *Causal paths* are **illustrative**: the event→asset links are hand-mapped "
        "heuristics, not inferred or predictive.\n"
        f"> - Sample = {ov['events']} events over **{n_days} days** "
        f"({window}) of English-language coverage (selection/coverage bias).\n"
    )

    lines.append("## 1. Overview\n")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Window | {window} ({n_days} days) |")
    lines.append(f"| Events | {ov['events']} |")
    lines.append(f"| Actors | {ov['actors']} |")
    lines.append(f"| Regions / theatres | {ov['regions']} |")
    lines.append(f"| Categories | {ov['categories']} |")
    lines.append(f"| Total nodes | {ov['nodes']} |")
    lines.append(f"| Relations | {ov['relations']} |")
    lines.append(f"| Graph density | {ov['density']:.4f} |\n")

    lines.append("## 2. Top 10 by influence\n")
    lines.append(
        "_Influence ≈ media coverage volume (correlates ~0.93 with degree), "
        "not real-world influence._\n"
    )
    lines.append("| # | Node | Type | Influence |")
    lines.append("| --: | --- | --- | --: |")
    for i, (_, label, typ, score) in enumerate(data["influence"], 1):
        lines.append(f"| {i} | {label} | {typ} | {score:.2f} |")
    lines.append("")

    lines.append("## 3. Top 10 attention hotspots\n")
    lines.append("_Media attention / connectivity, **not** real-world risk._\n")
    lines.append("| # | Node | Type | Score | Centrality | Influence | Density |")
    lines.append("| --: | --- | --- | --: | --: | --: | --: |")
    for i, (_, label, typ, s) in enumerate(data["hotspots"], 1):
        lines.append(
            f"| {i} | {label} | {typ} | {s.score:.3f} | {s.centrality:.2f} "
            f"| {s.influence:.2f} | {s.density:.2f} |"
        )
    lines.append("")

    lines.append("## 4. Emerging clusters\n")
    for i, c in enumerate(data["clusters"], 1):
        lines.append(f"### Cluster {i}: {c['name']}\n")
        lines.append(f"- **Size:** {c['size']} nodes ({c['n_events']} events)")
        lines.append(f"- **Main nodes:** {', '.join(c['entities'])}")
        if c["events"]:
            lines.append(f"- **Sample events:** {'; '.join(c['events'])}")
        lines.append(f"- **Interpretation:** {c['interpretation']}\n")

    lines.append("## 5. Causal paths to assets\n")
    lines.append(
        "_**Illustrative, not predictive.** Each chain is a real actor co-mentioned in a "
        "real event; the event→asset link is a hand-mapped heuristic (theatre→asset), not "
        "inferred. The score is event importance, not a market-impact estimate._\n"
    )
    for ticker, (name, _) in ASSETS.items():
        lines.append(f"**{ticker} ({name})**\n")
        if not paths[ticker]:
            lines.append("- (no chains)\n")
        for chain, score in paths[ticker]:
            lines.append(f"- `[{score}]` {chain}")
        lines.append("")

    n_clusters = len(data["clusters"])
    n_hot = len(data["hotspots"])
    n_events = data["overview"]["events"]  # type: ignore[index]
    total = data["total_clusters"]
    _, n_days = data["window"]  # type: ignore[misc]
    lines.append("---\n")
    lines.append(
        f"> **EventGraph organised {n_events} real World Observer events ({n_days} days) "
        f"into {n_clusters} major media clusters (of {total} communities) and ranked "
        f"{n_hot} attention hotspots — a descriptive map of media attention, "
        f"not a risk or causal model.**"
    )
    return "\n".join(lines) + "\n"


def _window(events: list[dict[str, object]]) -> tuple[str, int]:
    days = sorted({str(e.get("date") or e.get("published_at") or "")[:10] for e in events})
    days = [d for d in days if d.startswith("20")]
    if not days:
        return ("unknown window", 0)
    return (f"{days[0]} → {days[-1]}", len(days))


def main() -> None:
    events = load_events()
    g = build_graph(events)
    data = collect(g)  # sections 1-4 on the raw WO graph
    data["window"] = _window(events)
    add_asset_overlay(g)  # then attach heuristic asset leaves
    paths = causal_paths(g)  # section 5

    render_console(data, paths)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_markdown(data, paths), encoding="utf-8")
    print(f"\nMarkdown report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
