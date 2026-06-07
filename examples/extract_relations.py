"""Extract a typed relation graph from WO's summaries with a local LLM.

Co-occurrence/PMI mining of these summaries is mostly noise (it counts what
appears together, not what is *related*). This instead asks a local Qwen to pull
explicit ``SUBJECT | RELATION | OBJECT`` triples from each entity's latest
summary — real, stated relations — and writes them to JSON. A separate consumer
builds an EventGraph from them and traces multi-hop links.

LLM-heavy and non-deterministic (that's the trade for real relations). Requires
Ollama. Read-only on the committed narrative history (no WO DB access).

    python examples/extract_relations.py [--model qwen2.5:7b] [--top-entities 200]
        → examples/data/world_observer_relations.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from narrative_evolution import DATA

OLLAMA_URL = "http://localhost:11434/api/generate"
OUT_PATH = Path(__file__).parent / "data" / "world_observer_relations.json"

_PROMPT = (
    "Extract factual relations from this news summary as lines "
    "'SUBJECT | RELATION | OBJECT'. Only relations explicitly stated. Keep each "
    "entity short (a name, country, org, company, place — not a sentence). "
    "RELATION is a short verb phrase. Max 8 lines. No preamble.\nTEXT:\n{text}"
)


def ollama(model: str, prompt: str, timeout: int = 120) -> str | None:
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


def parse_triples(text: str) -> list[tuple[str, str, str]]:
    triples = []
    for line in (text or "").splitlines():
        parts = [p.strip(" -*\t") for p in line.split("|")]
        if len(parts) == 3 and all(parts) and all(len(p) < 60 for p in parts):
            triples.append((parts[0], parts[1], parts[2]))
    return triples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--top-entities", type=int, default=200)
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    entities = json.loads(DATA.read_text(encoding="utf-8"))[: args.top_entities]
    if ollama(args.model, "ping") is None:
        print(f"Ollama not reachable ({args.model}). Start it or pass --model.")
        return

    relations: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for i, e in enumerate(entities, 1):
        days = sorted(e["by_day"])
        if not days:
            continue
        day = days[-1]
        out = ollama(args.model, _PROMPT.format(text=e["by_day"][day][:1500]))
        for subj, rel, obj in parse_triples(out or ""):
            key = (subj.lower(), rel.lower(), obj.lower())
            if key in seen:
                continue
            seen.add(key)
            relations.append(
                {"subject": subj, "relation": rel, "object": obj, "source": e["key"], "day": day}
            )
        if i % 25 == 0:
            print(f"  {i}/{len(entities)} entities, {len(relations)} relations")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(relations, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(relations)} relations from {len(entities)} entities -> {out_path}")


if __name__ == "__main__":
    main()
