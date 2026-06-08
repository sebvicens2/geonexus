"""Multi-layer geopolitical network: signed news layers + hard maritime layer.

Combines two sources into one GeoNexus:
  - CAMEO signed layers (military / economic / diplomatic / energy / health):
    country↔country edges signed by stance (extract_cameo.py).
  - Hard maritime layer: chokepoint nodes with real PortWatch disruption, linked
    to the countries of their theatre (extract_maritime.py).

Reports per-layer net stance per dyad, cross-layer divergence (partners in one
layer, rivals in another), and chokepoint disruption + convergence with news.

    python examples/multilayer.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from geonexus import Actor, GeoNexus, Relation, RelationType

_DATA = Path(__file__).parent / "data"
# prefer the audited/gated extraction (fully-valid links) when available
CAMEO = (
    _DATA / "world_observer_cameo_verified.json"
    if (_DATA / "world_observer_cameo_verified.json").exists()
    else _DATA / "world_observer_cameo.json"
)
MARITIME = Path(__file__).parent / "data" / "world_observer_maritime.json"
SAMPLE = Path(__file__).parent / "data" / "world_observer_sample.json"
REPORT = Path("reports") / "world_observer_multilayer.md"

ALIASES = {
    "U.S.": "United States",
    "US": "United States",
    "USA": "United States",
    "U.S": "United States",
    "UK": "United Kingdom",
    "EU": "European Union",
    "DPRK": "North Korea",
    "PRC": "China",
    "Republic of Korea": "South Korea",
}
LAYERS = ["military", "economic", "diplomatic", "energy", "health"]
NARR = Path(__file__).parent / "data" / "world_observer_narrative_history.json"
BLOCS = {
    "NATO",
    "European Union",
    "OPEC",
    "OPEC+",
    "United Nations",
    "ASEAN",
    "BRICS",
    "African Union",
    "Quad",
    "G7",
    "G20",
    "Hamas",
    "Hezbollah",
    "Taliban",
    "IAEA",
    "WHO",
}


def _canon(name: str) -> str:
    return ALIASES.get(name.strip(), name.strip())


def _valid_actors() -> set[str]:
    """Real geopolitical actors: WO's country list + a bloc/org whitelist."""
    countries: set[str] = set()
    if NARR.exists():
        for e in json.loads(NARR.read_text(encoding="utf-8")):
            if e["dimension"] == "country":
                countries.add(_canon(e["key"]))
    return countries | BLOCS


VALID = _valid_actors()


def _actor(name: str) -> str | None:
    """Canonical actor name if it's a country/bloc, else None (drops junk nodes)."""
    c = _canon(name)
    return c if c in VALID else None


def countries_per_theatre(top: int = 6) -> dict[str, list[str]]:
    events = json.loads(SAMPLE.read_text(encoding="utf-8")) if SAMPLE.exists() else []
    counts: dict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in events:
        th = e.get("theatre")
        if th:
            for c in e.get("countries", []):
                counts[th][_canon(c)] += 1
    return {
        th: [c for c, _ in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:top]]
        for th, d in counts.items()
    }


def net_dyads(cameo: list[dict]) -> dict[str, dict[tuple[str, str], int]]:
    """Per layer: {(A,B) sorted: net sign}."""
    net: dict[str, dict[tuple[str, str], int]] = {lay: defaultdict(int) for lay in LAYERS}
    for e in cameo:
        a, b = _actor(e["a"]), _actor(e["b"])
        if not a or not b or a == b or e["domain"] not in net:
            continue
        net[e["domain"]][tuple(sorted((a, b)))] += e["sign"]
    return net


def alignment(net: dict[str, dict[tuple[str, str], int]]) -> dict[tuple[str, str], int]:
    """Geopolitical alignment per dyad = military + diplomatic net stance (signed)."""
    align: dict[tuple[str, str], int] = defaultdict(int)
    for lay in ("military", "diplomatic"):
        for pair, s in net[lay].items():
            align[pair] += s
    return {p: s for p, s in align.items() if s != 0}


def signed_analysis(net: dict) -> dict:
    """Structural balance % + a 2-bloc faction split on the signed alignment graph."""
    import networkx as nx

    align = alignment(net)
    g = nx.Graph()
    for (a, b), s in align.items():
        g.add_edge(a, b, sign=1 if s > 0 else -1)

    # structural balance: a triangle is balanced if the product of its edge signs is +
    balanced = unbalanced = 0
    unbalanced_examples = []
    for a, b, c in (tri for tri in _triangles(g)):
        prod = g[a][b]["sign"] * g[b][c]["sign"] * g[a][c]["sign"]
        if prod > 0:
            balanced += 1
        else:
            unbalanced += 1
            if len(unbalanced_examples) < 6:
                unbalanced_examples.append((a, b, c))
    total = balanced + unbalanced
    balance_pct = 100 * balanced / total if total else 0.0

    # factions: largest component, seed two camps from the strongest rivalry, then assign
    factions: tuple[list[str], list[str]] = ([], [])
    if g.number_of_edges():
        comp = max(nx.connected_components(g), key=len)
        sub = g.subgraph(comp)
        seed = min(sub.edges(data=True), key=lambda e: e[2]["sign"])
        seed_a, seed_b = seed[0], seed[1]
        rest = [n for n in sub.nodes if n not in (seed_a, seed_b)]
        campA, campB = {seed_a}, {seed_b}
        for _ in range(4):  # reassign every node fresh each pass (no double membership)
            newA, newB = {seed_a}, {seed_b}
            for n in rest:
                aff = sum(sub[n][m]["sign"] for m in campA if sub.has_edge(n, m)) - sum(
                    sub[n][m]["sign"] for m in campB if sub.has_edge(n, m)
                )
                (newA if aff >= 0 else newB).add(n)
            campA, campB = newA, newB
        factions = (sorted(campA), sorted(campB))
    return {
        "balance_pct": balance_pct,
        "n_triads": total,
        "factions": factions,
        "unbalanced": unbalanced_examples,
    }


def _triangles(g: object):
    seen = set()
    for a in g:
        nbrs = list(g[a])
        for i in range(len(nbrs)):
            for j in range(i + 1, len(nbrs)):
                b, c = nbrs[i], nbrs[j]
                if g.has_edge(b, c):
                    tri = frozenset((a, b, c))
                    if tri not in seen:
                        seen.add(tri)
                        yield (a, b, c)


def build(cameo: list[dict], maritime: list[dict]) -> GeoNexus:
    """GeoNexus: country nodes + chokepoint nodes; signed layer edges + maritime links."""
    g = GeoNexus()
    theatre_countries = countries_per_theatre()
    for lay, dyads in net_dyads(cameo).items():
        for (a, b), net in dyads.items():
            for name in (a, b):
                if f"actor:{name}" not in g:
                    g.add_actor(Actor(id=name, name=name, metadata={"kind": "country"}))
            g.add_relation(
                Relation(
                    source=f"actor:{a}",
                    target=f"actor:{b}",
                    relation_type=RelationType.OTHER,
                    weight=min(1.0, abs(net) / 6 + 0.1),
                    metadata={
                        "layer": lay,
                        "net": net,
                        "stance": "coop" if net > 0 else "conflict" if net < 0 else "neutral",
                    },
                )
            )
    for cp in maritime:
        cid = f"actor:CP:{cp['name']}"
        if cid not in g:
            g.add_actor(
                Actor(
                    id=f"CP:{cp['name']}",
                    name=cp["name"],
                    metadata={
                        "kind": "chokepoint",
                        "commodity": cp["commodity"],
                        "disruption": cp["disruption"],
                        "importance": cp["importance"],
                    },
                )
            )
        for th in cp["theatres"]:
            for country in theatre_countries.get(th, []):
                if f"actor:{country}" in g:
                    g.add_relation(
                        Relation(
                            source=cid,
                            target=f"actor:{country}",
                            relation_type=RelationType.LOCATED_IN,
                            weight=0.5,
                            metadata={"layer": "maritime"},
                        )
                    )
    return g


def main() -> None:
    if not CAMEO.exists():
        print(f"{CAMEO} not found — run examples/extract_cameo.py first.")
        return
    cameo = json.loads(CAMEO.read_text(encoding="utf-8"))
    maritime = json.loads(MARITIME.read_text(encoding="utf-8")) if MARITIME.exists() else []
    g = build(cameo, maritime)
    net = net_dyads(cameo)

    def head(t: str) -> None:
        print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")

    n_cp = sum(1 for o in g.nodes() if o.metadata.get("kind") == "chokepoint")
    print(
        f"Multi-layer graph: {len(g) - n_cp} countries, {n_cp} chokepoints, "
        f"{g.raw.number_of_edges()} edges across {len(LAYERS)} signed layers + maritime."
    )

    for lay in LAYERS:
        dy = sorted(net[lay].items(), key=lambda kv: kv[1])
        if not dy:
            continue
        head(f"{lay.upper()} layer — net stance per dyad (- conflict / + cooperation)")
        for (a, b), s in dy[:5]:
            if s < 0:
                print(f"  ▼ {a} - {b}: {s}")
        for (a, b), s in sorted(net[lay].items(), key=lambda kv: kv[1], reverse=True)[:4]:
            if s > 0:
                print(f"  ▲ {a} - {b}: +{s}")

    head("CROSS-LAYER DIVERGENCE  (partners in one layer, rivals in another)")
    by_pair: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for lay in LAYERS:
        for pair, s in net[lay].items():
            by_pair[pair][lay] = s
    for pair, layers in by_pair.items():
        signs = [s for s in layers.values() if s != 0]
        if any(s > 0 for s in signs) and any(s < 0 for s in signs):
            desc = ", ".join(f"{lay} {s:+d}" for lay, s in layers.items() if s)
            print(f"  {pair[0]} - {pair[1]}:  {desc}")

    sa = signed_analysis(net)
    head("SIGNED-NETWORK ANALYSIS  (alignment = military + diplomatic)")
    print(
        f"  Structural balance: {sa['balance_pct']:.0f}% of {sa['n_triads']} triads balanced "
        "(balanced = allies-of-allies / enemy-of-enemy)."
    )
    fa, fb = sa["factions"]
    if fa or fb:
        print(f"  Bloc A: {', '.join(fa[:12])}")
        print(f"  Bloc B: {', '.join(fb[:12])}")
    if sa["unbalanced"]:
        print(
            "  Tension triads (unbalanced): "
            + "; ".join(" - ".join(t) for t in sa["unbalanced"][:4])
        )

    head("HARD MARITIME LAYER — chokepoints by PortWatch disruption")
    cps = sorted(
        (o for o in g.nodes() if o.metadata.get("kind") == "chokepoint"),
        key=lambda o: abs((o.metadata.get("disruption") or {}).get("z_score", 0) or 0),
        reverse=True,
    )
    for o in cps[:8]:
        d = o.metadata.get("disruption") or {}
        deps = ", ".join(g.label(n) for n in g.neighbors(o.node_id, direction="out")[:5])
        print(
            f"  {o.name:16} {o.metadata['commodity']:6} "
            f"z={d.get('z_score', '?')} {d.get('classification', '?'):9} → {deps}"
        )

    _write_md(g, net, by_pair, cps, sa)
    print(f"\nMarkdown report written to {REPORT}")


def _write_md(g, net, by_pair, cps, sa) -> None:
    L = [
        "# World Observer — multi-layer geopolitical network\n",
        "_Signed news layers (CAMEO: military/economic/diplomatic/energy/health) + a "
        "hard maritime layer (chokepoints with real PortWatch disruption). News stance "
        "is media-derived; PortWatch is hard data._\n",
    ]
    for lay in LAYERS:
        dy = sorted(net[lay].items(), key=lambda kv: kv[1])
        if not dy:
            continue
        L.append(f"## {lay.capitalize()} layer\n")
        for (a, b), s in dy[:6]:
            if s != 0:
                L.append(f"- {a} - {b}: **{s:+d}** ({'conflict' if s < 0 else 'cooperation'})")
        L.append("")
    fa, fb = sa["factions"]
    L.append("## Signed-network analysis (alignment = military + diplomatic)\n")
    L.append(
        f"- **Structural balance:** {sa['balance_pct']:.0f}% of {sa['n_triads']} triads balanced"
    )
    L.append(f"- **Bloc A:** {', '.join(fa[:14])}")
    L.append(f"- **Bloc B:** {', '.join(fb[:14])}\n")

    L.append("## Cross-layer divergence\n")
    for pair, layers in by_pair.items():
        signs = [s for s in layers.values() if s != 0]
        if any(s > 0 for s in signs) and any(s < 0 for s in signs):
            L.append(
                f"- **{pair[0]} - {pair[1]}**: "
                + ", ".join(f"{lay} {s:+d}" for lay, s in layers.items() if s)
            )
    L.append("\n## Maritime chokepoints (hard PortWatch disruption)\n")
    L.append("| Chokepoint | Commodity | z-score | class | dependent countries |")
    L.append("| --- | --- | --: | --- | --- |")
    for o in cps:
        d = o.metadata.get("disruption") or {}
        deps = ", ".join(g.label(n) for n in g.neighbors(o.node_id, direction="out")[:5])
        L.append(
            f"| {o.name} | {o.metadata['commodity']} | {d.get('z_score', '?')} | "
            f"{d.get('classification', '?')} | {deps} |"
        )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
