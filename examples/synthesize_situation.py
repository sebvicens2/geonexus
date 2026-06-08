"""LLM situation report for the multi-layer network — grounded and cached.

Builds the structured signals (per-layer conflicts/cooperation, cross-layer
divergence, signed-network blocs/balance, maritime disruption), asks a local Qwen
to write a short situation report, and caches it keyed by a content hash so it is
only regenerated when the underlying data changes (or with --refresh).

    python examples/synthesize_situation.py [--model qwen2.5:7b] [--refresh]
        → examples/data/world_observer_situation.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extract_cameo import ollama
from multilayer import CAMEO, LAYERS, MARITIME, net_dyads, signed_analysis

OUT = Path(__file__).parent / "data" / "world_observer_situation.json"

_PROMPT = (
    "You are a geopolitical analyst. Using ONLY the structured signals below "
    "(stances extracted from ~12 days of news coverage; + = cooperation, "
    "- = conflict, by domain), write a concise SITUATION REPORT in 4-6 short "
    "paragraphs. Cover: the main fault lines, notable cooperation, cross-domain "
    "divergences (e.g. economic rivals that are diplomatic partners), the bloc "
    "structure, and any maritime/chokepoint risk. Be specific with country names. "
    "Do NOT invent anything beyond the signals. Begin by noting these are "
    "media-derived stances, not ground truth. Plain prose, no markdown headers.\n\n"
    "SIGNALS:\n{facts}"
)


def build_facts() -> dict:
    net = net_dyads(json.loads(CAMEO.read_text(encoding="utf-8")))
    facts: dict = {"layers": {}}
    for lay in LAYERS:
        items = net[lay].items()
        conf = [f"{a}-{b} ({s})" for (a, b), s in sorted(items, key=lambda kv: kv[1]) if s < 0]
        coop = [f"{a}-{b} (+{s})" for (a, b), s in sorted(items, key=lambda kv: -kv[1]) if s > 0]
        facts["layers"][lay] = {"conflict": conf[:6], "cooperation": coop[:6]}

    by_pair: dict = {}
    for lay in LAYERS:
        for pair, s in net[lay].items():
            by_pair.setdefault(pair, {})[lay] = s
    div = []
    for pair, ls in by_pair.items():
        signs = [s for s in ls.values() if s]
        if any(s > 0 for s in signs) and any(s < 0 for s in signs):
            div.append(
                f"{pair[0]}-{pair[1]}: " + ", ".join(f"{ly} {s:+d}" for ly, s in ls.items() if s)
            )
    facts["cross_layer_divergence"] = div[:10]

    sa = signed_analysis(net)
    facts["structural_balance_pct"] = round(sa["balance_pct"])
    facts["bloc_A"] = sa["factions"][0][:12]
    facts["bloc_B"] = sa["factions"][1][:12]
    facts["tension_triads"] = [" - ".join(t) for t in sa["unbalanced"][:5]]

    mar = json.loads(MARITIME.read_text(encoding="utf-8")) if MARITIME.exists() else []
    facts["maritime"] = [
        f"{c['name']} ({c['commodity']}): {c['disruption']['classification']}, "
        f"z={c['disruption']['z_score']}"
        for c in mar
        if c.get("disruption")
    ][:8]
    return facts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--refresh", action="store_true", help="regenerate even if cached")
    args = parser.parse_args()

    facts = build_facts()
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()[:16]

    if OUT.exists() and not args.refresh:
        cached = json.loads(OUT.read_text(encoding="utf-8"))
        if cached.get("hash") == digest:
            print(f"situation report already up to date (hash {digest}) — use --refresh to force")
            return

    print(f"generating situation report with {args.model}…")
    text = ollama(args.model, _PROMPT.format(facts=json.dumps(facts, indent=2)), timeout=240)
    if not text:
        print("Ollama not reachable — keeping any existing cache.")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"hash": digest, "text": text, "facts": facts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({len(text)} chars)")


if __name__ == "__main__":
    main()
