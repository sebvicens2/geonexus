"""Track how World Observer's LLM narratives evolve — what enters / fades / persists.

For each entity (country/theatre) and each day, we deterministically extract the
named topics from WO's synthesis bullets (no LLM), model entity→topic links in a
daily EventGraph, and store the days in an EventMemory. We then diff an entity's
topic set over time, and roll up which topics are *entering the world narrative*.

This is where the genuinely new, interpretable signal lives: not the static
instability scores, but the drift of the narrative content itself.

Run:
    python examples/narrative_evolution.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eventgraph import Actor, EventGraph, EventMemory, Relation, RelationType

DATA = Path(__file__).parent / "data" / "world_observer_narrative_history.json"
REPORT = Path("reports") / "world_observer_narrative_evolution.md"
MOMENTUM_PNG = Path("world_observer_narrative_momentum.png")

# generic capitalised tokens that are not informative entities/topics
GENERIC = {
    "The",
    "A",
    "An",
    "This",
    "That",
    "These",
    "Those",
    "It",
    "Its",
    "As",
    "On",
    "In",
    "Gulf",
    "Middle East",
    "President",
    "Secretary",
    "Minister",
    "Foreign Minister",
    "Prime Minister",
    "North",
    "South",
    "East",
    "West",
    "New",
    "State",
    "States",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
    "Strait",
    "Tensions",
    "Multiple",
    "General",
    "Civilian",
    "Both",
    "Several",
    "Many",
    # nationality / adjective forms (keep the place/person, drop the adjective)
    "Iranian",
    "Russian",
    "Ukrainian",
    "Chinese",
    "Israeli",
    "Palestinian",
    "American",
    "British",
    "Canadian",
    "Australian",
    "Korean",
    "Japanese",
    "Indian",
    "European",
    "African",
    "Arab",
    "Western",
    "Eastern",
    "Northern",
    "Southern",
    # abstract / common nouns that are noise as "topics"
    "Negative",
    "Positive",
    "Protests",
    "Violence",
    "Talks",
    "Concerns",
    "Warning",
    "Warnings",
    "Report",
    "Reports",
    "Statement",
    "Rising",
    "Major",
    "Significant",
    "Key",
    "Recent",
    "Ongoing",
    "Potential",
    "Global",
    "World",
    "Crisis",
    "Conflict",
    "Attack",
    "Attacks",
    "Strikes",
    "Deal",
    "Summit",
    "Dialogue",
    "Meeting",
    "Forces",
    "Officials",
    "Government",
    "Military",
    "Economy",
    "Markets",
    "Day",
}
_TOKEN = re.compile(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[A-Z]{2,})\b")
_LEADING = ("The ", "A ", "An ")


def extract_topics(text: str, own_name: str) -> set[str]:
    """Deterministically pull named topics from a summary (capitalised phrases)."""
    own = {w for w in re.split(r"[_\s]+", own_name) if w}
    topics = set()
    for cand in _TOKEN.findall(text):
        c = cand.strip()
        for art in _LEADING:  # drop leading articles ("The Trump" -> "Trump")
            if c.startswith(art):
                c = c[len(art) :]
        if len(c) <= 2 or c in GENERIC or c in own or c.title() in own:
            continue
        topics.add(c)
    return topics


def build_memory(entities: list[dict]) -> EventMemory:
    """One EventGraph per day: entity -> topic links, stored in an EventMemory."""
    days = sorted({d for e in entities for d in e["by_day"]})
    memory = EventMemory()
    for day in days:
        g = EventGraph()
        for ent in entities:
            text = ent["by_day"].get(day)
            if not text:
                continue
            eid = f"actor:{ent['key']}"
            if eid not in g:
                g.add_actor(
                    Actor(id=ent["key"], name=ent["key"], metadata={"wo_kind": ent["dimension"]})
                )
            for topic in extract_topics(text, ent["key"]):
                tid = f"actor:topic:{topic}"
                if tid not in g:
                    g.add_actor(
                        Actor(id=f"topic:{topic}", name=topic, metadata={"wo_kind": "topic"})
                    )
                g.add_relation(
                    Relation(
                        source=eid, target=tid, relation_type=RelationType.INVOLVES, weight=1.0
                    )
                )
        memory.snapshot(day, g)
    return memory


def topics_of(memory: EventMemory, day: str, entity_key: str) -> set[str]:
    g = memory.get(day)
    eid = f"actor:{entity_key}"
    if eid not in g:
        return set()
    return {g.label(n) for n in g.neighbors(eid, direction="out")}


def world_series(memory: EventMemory, entities: list[dict]) -> dict[str, dict[str, int]]:
    """For each topic: {day -> number of entities whose narrative mentions it}."""
    days = memory.dates()
    series: dict[str, dict[str, int]] = {}
    for day in days:
        for e in entities:
            for topic in topics_of(memory, day, e["key"]):
                series.setdefault(topic, dict.fromkeys(days, 0))[day] += 1
    return series


def first_seen(series_for_topic: dict[str, int], days: list[str]) -> str | None:
    """First day a topic's count is non-zero."""
    return next((d for d in days if series_for_topic[d] > 0), None)


def rising_topics(
    series: dict[str, dict[str, int]], days: list[str], *, min_end: int = 3
) -> list[tuple[str, int, int, str]]:
    """(topic, start_count, end_count, first_day) for topics that climb across entities."""
    out = []
    for topic, by_day in series.items():
        start, end = by_day[days[0]], by_day[days[-1]]
        if end >= min_end and end - start >= 2:
            out.append((topic, start, end, first_seen(by_day, days) or days[0]))
    out.sort(key=lambda r: (r[2] - r[1], r[2]), reverse=True)
    return out


def emerging_signals(
    memory: EventMemory,
    entities: list[dict],
    series: dict[str, dict[str, int]],
    days: list[str],
    *,
    min_recent: float = 4.0,
    max_baseline: float = 2.5,
    min_surprise: float = 3.0,
) -> list[dict]:
    """Denoised, surprise-ranked breakouts: topics ~absent early, prominent now.

    For each topic, compares an early baseline (mean of the first 3 days) to a
    recent level (mean of the last 2 days). Returns the ones that genuinely
    surged, with their breakout day, trajectory sparkline and the narratives
    carrying them now — the short, legible "what's newly rising" board.
    """
    last = days[-1]
    where: dict[str, list[str]] = {}
    for e in entities:
        for topic in topics_of(memory, last, e["key"]):
            where.setdefault(topic, []).append(e["key"])

    def _mean(values: list[int]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _breakout_day(by_day: dict[str, int]) -> str:
        best, day0 = 0, days[-1]
        for i in range(1, len(days)):
            jump = by_day[days[i]] - by_day[days[i - 1]]
            if jump > best:
                best, day0 = jump, days[i]
        return day0

    out: list[dict] = []
    for topic, by_day in series.items():
        baseline = _mean([by_day[d] for d in days[:3]])
        recent = _mean([by_day[d] for d in days[-2:]])
        if recent >= min_recent and baseline <= max_baseline and recent - baseline >= min_surprise:
            out.append(
                {
                    "topic": topic,
                    "breakout_day": _breakout_day(by_day),
                    "recent": recent,
                    "surprise": round(recent - baseline, 1),
                    "spark": "".join(_spark(by_day[d]) for d in days),
                    "where": sorted(where.get(topic, []))[:6],
                }
            )
    out.sort(key=lambda s: s["surprise"], reverse=True)
    return out


def relate_signals(signals: list[dict], *, min_overlap: float = 0.2) -> list[list[dict]]:
    """Group emerging signals into chains: signals sharing the narratives they appear in.

    Builds an EventGraph of signals (edge = Jaccard overlap of their ``where``
    narratives) and returns the connected components of size >= 2 — the
    storylines. Deterministic; reproducible.
    """
    import networkx as nx

    g = EventGraph()
    by_node: dict[str, dict] = {}
    for s in signals:
        nid = g.add_actor(Actor(id=s["topic"], name=s["topic"]))
        by_node[nid] = s
    for i in range(len(signals)):
        for j in range(i + 1, len(signals)):
            wa, wb = set(signals[i]["where"]), set(signals[j]["where"])
            if wa and wb:
                jac = len(wa & wb) / len(wa | wb)
                if jac >= min_overlap:
                    g.connect(
                        f"actor:{signals[i]['topic']}",
                        f"actor:{signals[j]['topic']}",
                        RelationType.CORRELATES,
                        weight=jac,
                    )
    chains = [
        sorted((by_node[n] for n in comp), key=lambda s: s["recent"], reverse=True)
        for comp in nx.connected_components(g.raw.to_undirected())
        if len(comp) >= 2
    ]
    chains.sort(key=len, reverse=True)
    return chains


def render_momentum_chart(
    series: dict[str, dict[str, int]], days: list[str], topics: list[str], path: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 6))
    for topic in topics:
        ax.plot(days, [series[topic][d] for d in days], marker="o", linewidth=1.8, label=topic)
    ax.set_xlabel("day")
    ax.set_ylabel("# entities whose narrative mentions the topic")
    ax.set_title("Narrative momentum — topics rising across the world's syntheses")
    ax.legend(loc="upper left", fontsize=8)
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    entities = json.loads(DATA.read_text(encoding="utf-8"))
    memory = build_memory(entities)
    days = memory.dates()
    first, last = days[0], days[-1]
    by_key = {e["key"]: e for e in entities}
    series = world_series(memory, entities)

    def head(t: str) -> None:
        print(f"\n{'=' * 74}\n{t}\n{'=' * 74}")

    print(
        f"Narrative evolution over {len(days)} days ({first} → {last}), "
        f"{len(entities)} entities — deterministic extraction, no LLM."
    )

    signals = emerging_signals(memory, entities, series, days)[:12]
    head("EMERGING SIGNALS  (denoised, ranked by surprise — read this first)")
    for s in signals:
        print(
            f"  {s['topic'][:22]:<22} ^{s['breakout_day']}  "
            f"~{s['recent']:.0f} narratives  {s['spark']}"
        )
        print(f"     -> {', '.join(s['where'])}")

    head("SIGNAL CHAINS  (signals sharing the same narratives = one storyline)")
    for chain in relate_signals(signals):
        print(f"  • {' + '.join(s['topic'] for s in chain)}")

    # spotlight a few high-signal theatres/countries
    spotlight = [
        k
        for k in (
            "gulf_iran",
            "ukraine_russia",
            "israel_gaza",
            "korean_peninsula",
            "taiwan_strait",
            "Iran",
            "Russia",
            "China",
            "United States",
        )
        if k in by_key
    ][:6]

    head(f"WHAT ENTERED / FADED IN EACH NARRATIVE  ({first} → {last})")
    for key in spotlight:
        a = topics_of(memory, first, key)
        b = topics_of(memory, last, key)
        if not a and not b:
            continue
        entered = sorted(b - a)
        faded = sorted(a - b)
        print(f"\n  [{key}]")
        print(f"    + entered: {', '.join(entered[:8]) or '—'}")
        print(f"    - faded:   {', '.join(faded[:6]) or '—'}")

    head("ENTERING THE WORLD NARRATIVE  (topics newly appearing across many entities)")
    entering: Counter[str] = Counter()
    for e in entities:
        ed = sorted(e["by_day"])
        if len(ed) < 2:
            continue
        a = topics_of(memory, ed[0], e["key"])
        b = topics_of(memory, ed[-1], e["key"])
        for topic in b - a:
            entering[topic] += 1
    for topic, n in entering.most_common(15):
        print(f"  {n:>2} entities  {topic}")

    # ---- day-by-day temporal analysis ---------------------------------- #
    rising = rising_topics(series, days)

    head("RISING TOPICS  (trajectory across the window, dated)")
    print(f"  {'topic':<26} {'first seen':<12} {'start→end (entities)':<20} sparkline")
    for topic, start, end, fday in rising[:12]:
        spark = "".join(_spark(series[topic][d]) for d in days)
        print(f"  {topic[:26]:<26} {fday:<12} {start:>2} → {end:<2}  {' ' * 9}{spark}")

    head("CHRONOLOGICAL FEED  (topics first crossing into 2+ narratives, by day)")
    seen: set[str] = set()
    for d in days:
        new_today = []
        for topic, by_day in series.items():
            if topic in seen:
                continue
            if by_day[d] >= 2:
                new_today.append((by_day[d], topic))
                seen.add(topic)
        if new_today:
            new_today.sort(reverse=True)
            tops = ", ".join(f"{t} ({n})" for n, t in new_today[:6])
            print(f"  {d}:  {tops}")

    head(f"ENTRY TIMELINE per entity  (when each topic entered, {spotlight[0]})")
    key = spotlight[0]
    entry_day: dict[str, str] = {}
    for d in days:
        for topic in topics_of(memory, d, key):
            entry_day.setdefault(topic, d)
    for topic, d in sorted(entry_day.items(), key=lambda kv: kv[1]):
        if d != days[0]:  # only show topics that entered after the start
            print(f"    {d}  + {topic}")

    chart_topics = [t for t, *_ in rising[:6]] or list(series)[:6]
    render_momentum_chart(series, days, chart_topics, MOMENTUM_PNG)
    print(f"\nNarrative momentum chart → {MOMENTUM_PNG}")

    _write_markdown(memory, entities, spotlight, entering, rising, series, days, first, last)
    print(f"Markdown report written to {REPORT}")


def _spark(n: int) -> str:
    bars = " ▁▂▃▄▅▆▇█"
    return bars[min(n, len(bars) - 1)]


def _write_markdown(
    memory, entities, spotlight, entering, rising, series, days, first, last
) -> None:
    L: list[str] = []
    L.append("# World Observer — narrative evolution\n")
    L.append(
        f"_How WO's LLM syntheses drifted between **{first}** and **{last}**: which "
        "topics entered, faded or persisted, and *when*. Topics are extracted "
        "deterministically from the summary bullets (no LLM). EventGraph stores one "
        "graph per day in an EventMemory and diffs the daily topic sets._\n"
    )

    L.append("## Rising topics (dated trajectory)\n")
    L.append("| Topic | First seen | Start → End (entities) |")
    L.append("| --- | --- | --- |")
    for topic, start, end, fday in rising[:15]:
        L.append(f"| {topic} | {fday} | {start} → {end} |")

    L.append("\n## Chronological feed (topics first reaching 2+ narratives, by day)\n")
    seen: set[str] = set()
    for d in days:
        new_today = sorted(
            ((by_day[d], t) for t, by_day in series.items() if t not in seen and by_day[d] >= 2),
            reverse=True,
        )
        for _, t in new_today:
            seen.add(t)
        if new_today:
            L.append(f"- **{d}** — {', '.join(t for _, t in new_today[:8])}")

    L.append("\n## What entered / faded per narrative\n")
    for key in spotlight:
        a = topics_of(memory, first, key)
        b = topics_of(memory, last, key)
        if not a and not b:
            continue
        L.append(f"### {key}\n")
        L.append(f"- **Entered:** {', '.join(sorted(b - a)[:10]) or '—'}")
        L.append(f"- **Faded:** {', '.join(sorted(a - b)[:8]) or '—'}")
        L.append(f"- **Core (persisted):** {', '.join(sorted(a & b)[:8]) or '—'}\n")

    L.append("## Entering the world narrative (across entities)\n")
    L.append("| Topic | # entities it newly entered |")
    L.append("| --- | --: |")
    for topic, n in entering.most_common(20):
        L.append(f"| {topic} | {n} |")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
