"""Optional LLM brief over the (deterministic) emerging-signals board.

The deterministic detector (narrative_evolution.emerging_signals) decides *which*
topics surged and *when* — reproducibly, no LLM. This script adds the last mile:
for the top signals, a local Qwen (Ollama) writes a grounded one-line "what
changed & why it matters" and cleans up the topic names, using the actual
before/after WO summaries as context (temperature 0, told to use only facts in
the text). Bounded to the top-N signals (~N LLM calls).

Requires Ollama running locally with a qwen model. EventGraph itself stays
LLM-free; this lives in examples/ as an optional enrichment.

    python examples/narrative_llm_brief.py [--model qwen2.5:14b] [--top 8]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from narrative_evolution import (
    DATA,
    build_memory,
    emerging_signals,
    world_series,
)

OLLAMA_URL = "http://localhost:11434/api/generate"
REPORT = Path("reports") / "world_observer_llm_brief.md"


def ollama(model: str, prompt: str, timeout: int = 180) -> str | None:
    """Call Ollama's /api/generate; return the text, or None if unreachable."""
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.0}}
    ).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return str(json.load(resp).get("response", "")).strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _prompt(key: str, topic: str, d0: str, t0: str, d1: str, t1: str) -> str:
    return (
        f"Two daily summaries of the same news theatre ({key}). Use ONLY facts present "
        f"in the LATER text; do not add anything.\n"
        f"EARLIER ({d0}):\n{t0[:1100]}\n\n"
        f"LATER ({d1}):\n{t1[:1100]}\n\n"
        f"The topic '{topic}' newly rose in this narrative. Reply in exactly two lines:\n"
        f"CHANGE: <one factual sentence: what changed around '{topic}', why it matters>\n"
        f"TOPICS: <up to 4 clean named topics present in LATER but not EARLIER, comma-separated>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:14b")
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()

    entities = json.loads(DATA.read_text(encoding="utf-8"))
    by_key = {e["key"]: e for e in entities}
    memory = build_memory(entities)
    days = memory.dates()
    series = world_series(memory, entities)
    signals = emerging_signals(memory, entities, series, days)[: args.top]

    if ollama(args.model, "ping") is None:
        print(
            f"Ollama not reachable at {OLLAMA_URL} (model {args.model}). "
            "Start Ollama or pass --model. The deterministic board still works without it."
        )
        return

    print(
        f"LLM brief over {len(signals)} emerging signals (model {args.model}, grounded, temp 0)\n"
    )
    lines = [
        "# World Observer — emerging-signals LLM brief\n",
        f"_Top {len(signals)} deterministically-detected breakouts, each explained by "
        f"`{args.model}` from the actual before/after WO summaries (grounded, no new facts). "
        "Detection is reproducible; this interpretation layer is not._\n",
    ]

    for s in signals:
        topic = s["topic"]
        key = s["where"][0] if s["where"] else None
        if key is None or key not in by_key:
            continue
        bd = by_key[key]["by_day"]
        edays = sorted(bd)
        out = ollama(
            args.model, _prompt(key, topic, edays[0], bd[edays[0]], edays[-1], bd[edays[-1]])
        )
        change, topics = topic, ""
        for ln in (out or "").splitlines():
            if ln.upper().startswith("CHANGE:"):
                change = ln.split(":", 1)[1].strip()
            elif ln.upper().startswith("TOPICS:"):
                topics = ln.split(":", 1)[1].strip()

        print(
            f"▲ {topic}  (broke out {s['breakout_day']}, ~{s['recent']:.0f} narratives, via {key})"
        )
        print(f"    {change}")
        if topics:
            print(f"    topics: {topics}")
        lines.append(f"### {topic}\n")
        lines.append(
            f"- **Broke out:** {s['breakout_day']} · now in ~{s['recent']:.0f} narratives "
            f"· seen via `{key}`"
        )
        lines.append(f"- **What changed:** {change}")
        if topics:
            lines.append(f"- **Clean topics:** {topics}")
        lines.append("")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nMarkdown brief written to {REPORT}")


if __name__ == "__main__":
    main()
