"""Surface *hidden* cross-narrative links between entities.

The narrative chains link signals that share a narrative. They miss links that
span theatres — e.g. China ↔ an Australian miner ↔ Africa — because the entities
never appear in the same daily summary. This finds those:

1. Build an entity co-mention graph over ALL of WO's summaries.
2. Weight pairs by **PMI** (pointwise mutual information), so a specific pairing
   (China-Zambia) beats a generic one (China-Iran, both ubiquitous).
3. Drop split artifacts (two halves of one name) and **ground** each link by the
   actual summary sentence where the two co-occur — proof it's real, not invented.
4. Optionally trace the strongest multi-hop path between two entities, and have a
   local Qwen phrase the relationship from the grounded snippet.

    python examples/hidden_links.py [--llm] [--between China Cobalt]
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import networkx as nx
from narrative_evolution import _TOKEN, DATA, GENERIC

REPORT = Path("reports") / "world_observer_hidden_links.md"


def _entities(text: str) -> set[str]:
    out = set()
    for cand in _TOKEN.findall(text):
        c = cand.strip()
        for art in ("The ", "A ", "An "):
            if c.startswith(art):
                c = c[len(art) :]
        if len(c) > 3 and c not in GENERIC:
            out.add(c)
    return out


def _is_split(a: str, b: str, texts: list[str]) -> bool:
    """True if a and b are really two halves of one name (appear adjacent)."""
    pats = [f"{a} {b}", f"{b} {a}", f"{a}-{b}", f"{b}-{a}", f"{a}, {b}"]
    joined = " ".join(texts)
    return any(p in joined for p in pats)


def _sentence(text: str, a: str, b: str) -> str | None:
    """Return a bullet/sentence from text that mentions both a and b."""
    for chunk in re.split(r"(?:\n|- |\. )", text):
        if a in chunk and b in chunk:
            return " ".join(chunk.split())[:200]
    return None


def build() -> tuple[list[tuple], dict, nx.Graph]:
    entities = json.loads(DATA.read_text(encoding="utf-8"))
    docs = [
        {"key": e["key"], "day": day, "text": txt, "ents": _entities(txt)}
        for e in entities
        for day, txt in e["by_day"].items()
    ]
    n = len(docs)
    freq: Counter[str] = Counter()
    co: Counter[tuple[str, str]] = Counter()
    examples: dict[tuple[str, str], dict] = {}
    for d in docs:
        for x in d["ents"]:
            freq[x] += 1
        for a, b in itertools.combinations(sorted(d["ents"]), 2):
            co[(a, b)] += 1
            examples.setdefault((a, b), d)

    graph = nx.Graph()
    links = []
    for (a, b), c in co.items():
        if c < 2:
            continue
        pmi = math.log((c / n) / ((freq[a] / n) * (freq[b] / n)))
        # full graph (co>=2) for path queries; distance favours specific (high-PMI) hops
        graph.add_edge(a, b, weight=pmi, dist=1.0 / max(pmi, 0.1), co=c)
        # the displayed "surprising links" use a stricter filter
        if c >= 4 and not (freq[a] >= n * 0.25 and freq[b] >= n * 0.25):
            links.append((pmi, c, a, b))
    links.sort(reverse=True)
    return links, examples, graph


def top_grounded_links(top: int = 14) -> list[dict]:
    """Top surprising links, de-noised and grounded in a source sentence (for reuse)."""
    links, examples, _ = build()
    entities = json.loads(DATA.read_text(encoding="utf-8"))
    texts_by_pair: dict[tuple[str, str], list[str]] = {}
    for e in entities:
        for txt in e["by_day"].values():
            ents = _entities(txt)
            for a, b in itertools.combinations(sorted(ents), 2):
                texts_by_pair.setdefault((a, b), []).append(txt)
    out: list[dict] = []
    for pmi, c, a, b in links:
        if len(out) >= top:
            break
        if _is_split(a, b, texts_by_pair.get((a, b), [])):
            continue
        snippet = _sentence(examples[(a, b)]["text"], a, b)
        if not snippet:
            continue
        out.append({"a": a, "b": b, "pmi": round(pmi, 1), "co": c, "snippet": snippet})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", action="store_true", help="phrase each link with a local Qwen")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument(
        "--between",
        nargs=2,
        metavar=("A", "B"),
        help="trace the strongest multi-hop path between two entities",
    )
    parser.add_argument("--top", type=int, default=18)
    args = parser.parse_args()

    links, examples, graph = build()
    entities = json.loads(DATA.read_text(encoding="utf-8"))
    texts_by_pair: dict[tuple[str, str], list[str]] = {}
    for e in entities:
        for txt in e["by_day"].values():
            ents = _entities(txt)
            for a, b in itertools.combinations(sorted(ents), 2):
                texts_by_pair.setdefault((a, b), []).append(txt)

    llm = None
    if args.llm:
        from narrative_llm_brief import ollama

        if ollama(args.model, "ping") is not None:
            llm = ollama

    if args.between:
        a, b = args.between
        if a not in graph or b not in graph:
            print(f"'{a}' or '{b}' not in the co-mention graph.")
            return
        path = nx.shortest_path(graph, a, b, weight="dist")
        print(f"Strongest link path  {a} → {b}:")
        print("  " + "  →  ".join(path))
        return

    print("HIDDEN LINKS — surprising cross-narrative co-mentions (PMI), grounded\n")
    lines = [
        "# World Observer — hidden cross-narrative links\n",
        "_Entity pairs that co-occur far more than chance (PMI) across WO's summaries — "
        "including cross-theatre links the narrative chains miss. Each is grounded in the "
        "actual summary sentence; split-name artifacts are removed._\n",
    ]
    shown = 0
    for pmi, c, a, b in links:
        if shown >= args.top:
            break
        if _is_split(a, b, texts_by_pair.get((a, b), [])):
            continue
        snippet = _sentence(examples[(a, b)]["text"], a, b)
        if not snippet:
            continue
        shown += 1
        line = f"{a} — {b}"
        print(f"  {line}   (PMI {pmi:.1f}, {c}x)")
        print(f"     “{snippet}”")
        lines.append(f"### {line}\n")
        lines.append(f"- PMI {pmi:.1f}, co-mentioned {c}x")
        lines.append(f"- > {snippet}")
        if llm is not None:
            out = llm(
                args.model,
                f"In ONE short phrase, state the relationship between '{a}' and '{b}'. "
                f"Use ONLY this text: {snippet}",
            )
            if out:
                rel = out.strip().splitlines()[0][:160]
                print(f"     → {rel}")
                lines.append(f"- **Relationship:** {rel}")
        lines.append("")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nMarkdown report written to {REPORT}")


if __name__ == "__main__":
    main()
