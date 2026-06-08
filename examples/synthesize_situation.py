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
from multilayer import CAMEO, LAYERS, MARITIME, _actor, net_dyads, signed_analysis

OUT = Path(__file__).parent / "data" / "world_observer_situation.json"
MIN_LLM = 2  # pairs with >= this many interactions get an LLM summary; others show facts only

_PAIR_PROMPT = (
    "In 2-3 sentences, summarise the relationship between {a} and {b}, based ONLY on "
    "these interactions from ~12 days of news coverage (+ = cooperation, - = conflict). "
    "These are media-derived stances. Be specific, do not invent. Plain prose.\n"
    "INTERACTIONS:\n{lines}"
)

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


def build_pairs() -> dict[str, list[dict]]:
    """Per canonical country pair: the list of CAMEO interactions between them."""
    cam = json.loads(CAMEO.read_text(encoding="utf-8"))
    pairs: dict[str, list[dict]] = {}
    for e in cam:
        a, b = _actor(e["a"]), _actor(e["b"])
        if not a or not b or a == b:
            continue
        key = "|".join(sorted((a, b)))
        pairs.setdefault(key, []).append(
            {"domain": e["domain"], "cameo": e["cameo"], "sign": e["sign"], "source": e["source"]}
        )
    return pairs


def _pair_reports(model: str, refresh: bool, cached: dict) -> dict:
    """Per-pair entries {h, edges, text}; LLM summary for pairs with >= MIN_LLM edges."""
    prev = cached.get("pairs", {}) if cached else {}
    pairs = build_pairs()
    todo = sum(1 for v in pairs.values() if len(v) >= MIN_LLM)
    out: dict[str, dict] = {}
    done = 0
    for key, edges in pairs.items():
        eh = hashlib.sha256(json.dumps(edges, sort_keys=True).encode()).hexdigest()[:12]
        entry: dict = {"h": eh, "edges": edges, "text": ""}
        if len(edges) >= MIN_LLM:
            old = prev.get(key)
            if old and old.get("h") == eh and old.get("text") and not refresh:
                entry["text"] = old["text"]
            else:
                a, b = key.split("|")
                lines = "\n".join(f"- {x['domain']}: {x['cameo']} ({x['sign']:+d})" for x in edges)
                txt = ollama(model, _PAIR_PROMPT.format(a=a, b=b, lines=lines), timeout=120)
                entry["text"] = (txt or "").strip()
                done += 1
                if done % 10 == 0:
                    print(f"  pair summaries: {done}/{todo}")
        out[key] = entry
    print(f"  pair summaries done ({todo} via LLM, {len(out)} total)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--refresh", action="store_true", help="regenerate even if cached")
    args = parser.parse_args()

    facts = build_facts()
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()[:16]
    cached = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    # global report: reuse cache if unchanged, else regenerate
    text = cached.get("text", "")
    if cached.get("hash") != digest or args.refresh or not text:
        print(f"generating global situation report with {args.model}…")
        new = ollama(args.model, _PROMPT.format(facts=json.dumps(facts, indent=2)), timeout=240)
        if new:
            text = new
        elif not text:
            print("Ollama not reachable and no cache — aborting.")
            return

    print("generating per-pair summaries…")
    pairs = _pair_reports(args.model, args.refresh, cached)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"hash": digest, "text": text, "facts": facts, "pairs": pairs},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUT} (global {len(text)} chars, {len(pairs)} pairs)")


if __name__ == "__main__":
    main()
