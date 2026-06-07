"""Extract a SIGNED, multi-layer country interaction graph (CAMEO-style) via LLM.

For each summary, a local Qwen extracts interactions between two actors as
``A | B | DOMAIN | CLASS`` where DOMAIN is the layer (military / economic /
diplomatic / energy / health) and CLASS is a CAMEO quad-class:
material_cooperation, verbal_cooperation, neutral, verbal_conflict,
material_conflict — mapped to a Goldstein-style sign (+2..-2).

This gives a signed multiplex: one layer per domain, edges signed by stance.
Pure co-mentions (no interaction) are excluded by design.

    python examples/extract_cameo.py [--model qwen2.5:7b] [--top-entities 200]
        → examples/data/world_observer_cameo.json
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
OUT_PATH = Path(__file__).parent / "data" / "world_observer_cameo.json"

DOMAINS = {"military", "economic", "diplomatic", "energy", "health"}
SIGN = {
    "material_cooperation": 2,
    "verbal_cooperation": 1,
    "neutral": 0,
    "verbal_conflict": -1,
    "material_conflict": -2,
}
_PROMPT = (
    "From this news summary, extract interactions between TWO distinct named actors "
    "(countries, blocs, or major orgs). One per line, exactly:\n"
    "ACTOR_A | ACTOR_B | DOMAIN | CLASS\n"
    "DOMAIN ∈ military, economic, diplomatic, energy, health\n"
    "CLASS ∈ material_cooperation, verbal_cooperation, neutral, verbal_conflict, "
    "material_conflict\n"
    "Only real interactions between two actors (skip one-actor facts). Max 8 lines. "
    "No preamble.\nTEXT:\n{text}"
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


def parse(text: str) -> list[tuple[str, str, str, str]]:
    rows = []
    for line in (text or "").splitlines():
        parts = [p.strip(" -*\t").lower() if i >= 2 else p.strip(" -*\t")
                 for i, p in enumerate(line.split("|"))]
        if len(parts) == 4 and all(parts) and parts[2] in DOMAINS and parts[3] in SIGN:
            a, b = parts[0], parts[1]
            if a and b and a.lower() != b.lower() and len(a) < 50 and len(b) < 50:
                rows.append((a, b, parts[2], parts[3]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--top-entities", type=int, default=200)
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    entities = json.loads(DATA.read_text(encoding="utf-8"))[: args.top_entities]
    if ollama(args.model, "ping") is None:
        print(f"Ollama not reachable ({args.model}).")
        return

    edges: list[dict] = []
    seen: set[tuple] = set()
    for i, e in enumerate(entities, 1):
        days = sorted(e["by_day"])
        if not days:
            continue
        day = days[-1]
        out = ollama(args.model, _PROMPT.format(text=e["by_day"][day][:1500]))
        for a, b, domain, cameo in parse(out or ""):
            key = (a.lower(), b.lower(), domain, cameo)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"a": a, "b": b, "domain": domain, "cameo": cameo,
                          "sign": SIGN[cameo], "source": e["key"], "day": day})
        if i % 25 == 0:
            print(f"  {i}/{len(entities)} entities, {len(edges)} edges")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(edges, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(edges)} signed multi-layer edges -> {out_path}")


if __name__ == "__main__":
    main()
