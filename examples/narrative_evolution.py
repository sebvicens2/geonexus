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


def main() -> None:
    entities = json.loads(DATA.read_text(encoding="utf-8"))
    memory = build_memory(entities)
    days = memory.dates()
    first, last = days[0], days[-1]
    by_key = {e["key"]: e for e in entities}

    def head(t: str) -> None:
        print(f"\n{'=' * 74}\n{t}\n{'=' * 74}")

    print(
        f"Narrative evolution over {len(days)} days ({first} → {last}), "
        f"{len(entities)} entities — deterministic extraction, no LLM."
    )

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

    _write_markdown(memory, entities, by_key, spotlight, entering, first, last)
    print(f"\nMarkdown report written to {REPORT}")


def _write_markdown(memory, entities, by_key, spotlight, entering, first, last) -> None:
    L: list[str] = []
    L.append("# World Observer — narrative evolution\n")
    L.append(
        f"_How WO's LLM syntheses drifted between **{first}** and **{last}**: which "
        "topics entered, faded or persisted. Topics are extracted deterministically "
        "from the summary bullets (no LLM). EventGraph stores one graph per day in an "
        "EventMemory and diffs each entity's topic set._\n"
    )

    L.append("## What entered / faded per narrative\n")
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
