"""GeoNexus over World Observer's synthesis layer.

Instead of recomputing attention from raw articles, this consumes WO's already-
computed per-entity intelligence (instability, attention share, narrative,
summaries) as **node attributes**, and lets GeoNexus add the **relational
layer** WO does not have: a country co-occurrence graph, communities (blocs),
and connectivity ranking.

Run:
    python examples/world_observer_synthesis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from geonexus import Actor, ActorType, GeoNexus, Relation, RelationType

DATA = Path(__file__).parent / "data" / "world_observer_synthesis.json"
REPORT = Path("reports") / "world_observer_synthesis.md"

_COUNTRY_FIELDS = (
    "instability",
    "classification",
    "drivers",
    "dominant_signal",
    "intel_score",
    "attention_share",
    "summary",
)


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def build(data: dict) -> GeoNexus:
    """Country/theatre graph: WO scores as node metadata, co-occurrence as edges."""
    g = GeoNexus()
    for c in data["countries"]:
        g.add_actor(
            Actor(
                id=c["name"],
                name=c["name"],
                metadata={"wo_kind": "country", **{k: c.get(k) for k in _COUNTRY_FIELDS}},
            )
        )
    for t in data["theatres"]:
        g.add_actor(
            Actor(
                id=t["name"],
                name=t["name"],
                category=ActorType.OTHER,
                metadata={
                    "wo_kind": "theatre",
                    "attention_share": t.get("attention_share"),
                    "region_score": t.get("region_score"),
                    "summary": t.get("summary"),
                },
            )
        )

    max_w = max((w for _, _, w in data["cooccurrence"]), default=1.0)
    for a, b, w in data["cooccurrence"]:
        if f"actor:{a}" in g and f"actor:{b}" in g:
            g.add_relation(
                Relation(
                    source=f"actor:{a}",
                    target=f"actor:{b}",
                    relation_type=RelationType.CORRELATES,
                    weight=min(1.0, w / max_w),
                )
            )
    for t in data["theatres"]:
        for cn in t["top_countries"]:
            if f"actor:{cn}" in g:
                g.add_relation(
                    Relation(
                        source=f"actor:{t['name']}",
                        target=f"actor:{cn}",
                        relation_type=RelationType.LOCATED_IN,
                        weight=0.5,
                    )
                )
    return g


def kind(g: GeoNexus, nid: str) -> str:
    return str(g.get(nid).metadata.get("wo_kind", "node"))


def attention_momentum(
    series: dict[str, dict[str, float]],
) -> list[tuple[str, float, float, float]]:
    """(key, first, last, delta) for keys present on both the first and last day."""
    out = []
    for key, by_day in series.items():
        days = sorted(by_day)
        if len(days) >= 2:
            first, last = by_day[days[0]], by_day[days[-1]]
            out.append((key, first, last, last - first))
    out.sort(key=lambda r: r[3], reverse=True)
    return out


def main() -> None:
    data = load()
    g = build(data)
    by_name = {c["name"]: c for c in data["countries"]}

    countries = [o for o in g.nodes() if kind(g, o.node_id) == "country"]
    theatres = [o for o in g.nodes() if kind(g, o.node_id) == "theatre"]
    degree = g.centrality("degree")

    def head(t: str) -> None:
        print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")

    print(
        f"GeoNexus over WO synthesis: {len(countries)} countries, {len(theatres)} theatres, "
        f"{g.raw.number_of_edges()} relations."
    )
    print("Scores below are World Observer's own (instability, attention); GeoNexus")
    print("adds the relational layer (co-occurrence graph, blocs, connectivity).")

    head("1. MOST UNSTABLE COUNTRIES  (World Observer instability score)")
    top_inst = sorted(
        (c for c in data["countries"] if c["instability"] is not None),
        key=lambda c: c["instability"],
        reverse=True,
    )[:10]
    for c in top_inst:
        driver = c["drivers"][0] if c["drivers"] else (c["dominant_signal"] or "")
        print(
            f"  {c['name']:<18} {c['instability']:>5.0f}  "
            f"{c['classification'] or '':<8} {driver[:46]}"
        )

    head("2. HIGHEST-ATTENTION THEATRES  (WO coverage share, latest day)")
    top_att = sorted(
        (t for t in data["theatres"] if t["attention_share"] is not None),
        key=lambda t: t["attention_share"],
        reverse=True,
    )[:8]
    for t in top_att:
        print(f"  {t['name']:<26} share={t['attention_share']:.2f}")

    head("3. MOST CONNECTED COUNTRIES  (GeoNexus adds this — co-occurrence degree)")
    conn_rank = sorted(countries, key=lambda o: degree[o.node_id], reverse=True)[:10]
    for o in conn_rank:
        inst = by_name[o.node_id.split(":", 1)[1]]["instability"]
        inst_s = f"{inst:.0f}" if inst is not None else "—"
        print(
            f"  {g.label(o.node_id):<18} degree={degree[o.node_id]:.3f}  (WO instability {inst_s})"
        )

    head("4. BLOCS  (co-occurrence communities, ranked by mean WO instability)")
    blocs = []
    for cluster in g.emerging_clusters(min_size=3):
        members = [n for n in cluster if kind(g, n) == "country"]
        insts = [
            by_name[n.split(":", 1)[1]]["instability"]
            for n in members
            if by_name.get(n.split(":", 1)[1], {}).get("instability") is not None
        ]
        if not insts:
            continue
        mean_inst = sum(insts) / len(insts)
        members.sort(key=lambda n: by_name[n.split(":", 1)[1]]["instability"] or 0, reverse=True)
        blocs.append((mean_inst, [g.label(n) for n in members]))
    blocs.sort(reverse=True)
    for mean_inst, members in blocs[:6]:
        print(f"  mean instability {mean_inst:>4.0f}:  {', '.join(members[:6])}")

    head("5. NARRATIVE (WO LLM synthesis, verbatim) — top theatre")
    top_theatre = next((t for t in top_att if t["summary"]), None)
    if top_theatre:
        print(f"  [{top_theatre['name']}]")
        for line in (top_theatre["summary"] or "").splitlines()[:5]:
            if line.strip():
                print(f"    {line.strip()[:90]}")

    head("6. ATTENTION MOMENTUM  (WO daily share, 7-day change)")
    mom = attention_momentum(data["attention_series"]["theatre"])
    print("  Rising:")
    for key, f, last, d in [m for m in mom if m[3] > 0][:4]:
        print(f"    ▲ {key:<26} {f:.2f} → {last:.2f}  (+{d:.2f})")
    print("  Fading:")
    for key, f, last, d in [m for m in reversed(mom) if m[3] < 0][:4]:
        print(f"    ▼ {key:<26} {f:.2f} → {last:.2f}  ({d:.2f})")

    print(f"\n{'=' * 72}")
    print(
        f"GeoNexus layered a {g.raw.number_of_edges()}-edge relational graph over WO's "
        f"synthesis of {len(countries)} countries / {len(theatres)} theatres —"
    )
    print("ranking by WO's real instability & attention, not by recomputed proxies.")
    print("=" * 72)

    _write_markdown(data, g, by_name, top_inst, top_att, conn_rank, blocs, mom, degree)
    print(f"\nMarkdown report written to {REPORT}")


def _write_markdown(data, g, by_name, top_inst, top_att, conn_rank, blocs, mom, degree) -> None:
    L: list[str] = []
    L.append("# GeoNexus over World Observer synthesis\n")
    L.append(
        "_GeoNexus **consumes World Observer's own scores** (instability, attention, "
        "narrative) as node attributes and adds the relational layer (co-occurrence "
        "graph, blocs, connectivity). No recomputation of attention; no LLM here._\n"
    )

    L.append("## Most unstable countries (WO instability)\n")
    L.append("| Country | Instability | Class | Top driver |")
    L.append("| --- | --: | --- | --- |")
    for c in top_inst:
        driver = (c["drivers"][0] if c["drivers"] else (c["dominant_signal"] or "")).replace(
            "|", "/"
        )
        L.append(
            f"| {c['name']} | {c['instability']:.0f} | {c['classification'] or ''} | {driver} |"
        )

    L.append("\n## Highest-attention theatres (WO coverage share)\n")
    L.append("| Theatre | Share |")
    L.append("| --- | --: |")
    for t in top_att:
        L.append(f"| {t['name']} | {t['attention_share']:.2f} |")

    L.append("\n## Most connected countries (GeoNexus co-occurrence degree)\n")
    L.append("| Country | Degree | WO instability |")
    L.append("| --- | --: | --: |")
    for o in conn_rank:
        inst = by_name[o.node_id.split(":", 1)[1]]["instability"]
        L.append(
            f"| {g.label(o.node_id)} | {degree[o.node_id]:.3f} | {inst:.0f} |"
            if inst is not None
            else f"| {g.label(o.node_id)} | {degree[o.node_id]:.3f} | — |"
        )

    L.append("\n## Blocs (co-occurrence communities, by mean WO instability)\n")
    for mean_inst, members in blocs[:6]:
        L.append(f"- **mean instability {mean_inst:.0f}** — {', '.join(members[:6])}")

    L.append("\n## Attention momentum (WO 7-day share change)\n")
    L.append("| Theatre | First | Last | Δ |")
    L.append("| --- | --: | --: | --: |")
    for key, f, last, d in [m for m in mom if abs(m[3]) > 0.02][:8]:
        L.append(f"| {key} | {f:.2f} | {last:.2f} | {d:+.2f} |")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
