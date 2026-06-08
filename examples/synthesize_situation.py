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
from multilayer import CAMEO, LAYERS, MARITIME, NARR, _actor, net_dyads, signed_analysis

OUT = Path(__file__).parent / "data" / "world_observer_situation.json"
MIN_LLM = 2  # pairs with >= this many interactions get an LLM summary; others show facts only


def _word(s: int) -> str:
    return "cooperation" if s > 0 else "conflict" if s < 0 else "contact"


_BULLETS = (
    "Answer ONLY as bullet points, one per line, each starting with '- '. "
    "No intro, no headers, no numeric scores. "
)

_PAIR_PROMPT = (
    "In 3-4 bullet points, explain the relationship between {a} and {b}, focused on the "
    "REASONS and concrete events driving it, drawing on the news excerpts below. "
    + _BULLETS
    + "Media-derived. Be specific.\nDOMAINS & EVENTS:\n{lines}"
)

_COUNTRY_PROMPT = (
    "In 3-4 bullet points, summarise {c}'s geopolitical situation over ~12 days, focused "
    "on the REASONS and key events, drawing on its interactions below (with whom, domain, "
    "cooperation or conflict). " + _BULLETS + "Media-derived. Be specific.\n"
    "INTERACTIONS:\n{lines}"
)

_PROMPT = (
    "You are a geopolitical analyst. Write a SITUATION REPORT as 6-9 bullet points "
    "from the signals below (from ~12 days of news coverage). Cover the main fault lines, "
    "notable cooperation, cross-domain divergences (e.g. economic rivals that are "
    "diplomatic partners), the bloc structure and any maritime/chokepoint risk — and "
    "EXPLAIN THE REASONS using the concrete events in KEY EVENTS. "
    + _BULLETS
    + "Begin with one bullet noting these are media-derived stances, not ground truth. "
    "Be specific with country names; do not invent beyond the signals.\n\nSIGNALS:\n{facts}"
)


def _summaries() -> dict[str, dict[str, str]]:
    if not hasattr(_summaries, "_cache"):
        data = json.loads(NARR.read_text(encoding="utf-8")) if NARR.exists() else []
        _summaries._cache = {e["key"]: e["by_day"] for e in data}  # type: ignore[attr-defined]
    return _summaries._cache  # type: ignore[attr-defined]


def _ground(source: str, day: str, ra: str, rb: str) -> str:
    """The source sentence behind an interaction — the 'reason' (no scores)."""
    import re

    text = _summaries().get(source, {}).get(day, "")
    chunks = [" ".join(c.split()) for c in re.split(r"(?:\n|- |\. )", text) if c.strip()]
    both = [c for c in chunks if ra in c and rb in c]
    one = [c for c in chunks if ra in c or rb in c]
    return (both or one or [""])[0][:220]


def build_pairs() -> dict[str, list[dict]]:
    """Per canonical country pair: its CAMEO interactions, each with its source 'reason'."""
    cam = json.loads(CAMEO.read_text(encoding="utf-8"))
    pairs: dict[str, list[dict]] = {}
    for e in cam:
        a, b = _actor(e["a"]), _actor(e["b"])
        if not a or not b or a == b:
            continue
        key = "|".join(sorted((a, b)))
        pairs.setdefault(key, []).append(
            {
                "domain": e["domain"],
                "cameo": e["cameo"],
                "sign": e["sign"],
                "source": e["source"],
                "why": _ground(e["source"], e.get("day", ""), e["a"], e["b"]),
            }
        )
    return pairs


def build_facts(pairs: dict[str, list[dict]]) -> dict:
    net = net_dyads(json.loads(CAMEO.read_text(encoding="utf-8")))
    facts: dict = {"layers": {}}
    for lay in LAYERS:
        items = net[lay].items()
        conf = [f"{a}-{b}" for (a, b), s in sorted(items, key=lambda kv: kv[1]) if s < 0]
        coop = [f"{a}-{b}" for (a, b), s in sorted(items, key=lambda kv: -kv[1]) if s > 0]
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
                f"{pair[0]}-{pair[1]}: "
                + ", ".join(f"{ly} {_word(s)}" for ly, s in ls.items() if s)
            )
    facts["cross_layer_divergence"] = div[:10]

    # KEY EVENTS: the concrete reasons behind the strongest dyads (no scores)
    strength = {k: sum(abs(e["sign"]) for e in v) for k, v in pairs.items()}
    events = []
    for k in sorted(strength, key=lambda k: -strength[k])[:14]:
        a, b = k.split("|")
        why = next((e["why"] for e in pairs[k] if e["why"]), "")
        if why:
            events.append(f"{a}/{b}: {why}")
    facts["key_events"] = events

    sa = signed_analysis(net)
    facts["structural_balance_pct"] = round(sa["balance_pct"])
    facts["bloc_A"] = sa["factions"][0][:12]
    facts["bloc_B"] = sa["factions"][1][:12]
    facts["tension_triads"] = [" - ".join(t) for t in sa["unbalanced"][:5]]

    mar = json.loads(MARITIME.read_text(encoding="utf-8")) if MARITIME.exists() else []
    facts["maritime"] = [
        f"{c['name']} ({c['commodity']}): {c['disruption']['classification']}"
        for c in mar
        if c.get("disruption")
    ][:8]
    return facts


def _pair_reports(model: str, refresh: bool, cached: dict, pairs: dict) -> dict:
    """Per-pair entries {h, edges, text}; reason-based LLM summary for pairs >= MIN_LLM."""
    prev = cached.get("pairs", {}) if cached else {}
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
                lines = "\n".join(
                    f"- {x['domain']} ({_word(x['sign'])}): {x['why']}".rstrip(": ") for x in edges
                )
                txt = ollama(model, _PAIR_PROMPT.format(a=a, b=b, lines=lines), timeout=120)
                entry["text"] = (txt or "").strip()
                done += 1
                if done % 10 == 0:
                    print(f"  pair summaries: {done}/{todo}")
        out[key] = entry
    print(f"  pair summaries done ({todo} via LLM, {len(out)} total)")
    return out


def build_countries(pairs: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Per country: every interaction it takes part in (with whom, domain, reason)."""
    countries: dict[str, list[dict]] = {}
    for key, edges in pairs.items():
        a, b = key.split("|")
        for c, other in ((a, b), (b, a)):
            lst = countries.setdefault(c, [])
            for e in edges:
                lst.append(
                    {
                        "with": other,
                        "domain": e["domain"],
                        "cameo": e["cameo"],
                        "sign": e["sign"],
                        "why": e["why"],
                    }
                )
    return countries


def _country_reports(model: str, refresh: bool, cached: dict, countries: dict) -> dict:
    """Per-country entries {h, interactions, text}; LLM summary if >= MIN_LLM interactions."""
    prev = cached.get("countries", {}) if cached else {}
    todo = sum(1 for v in countries.values() if len(v) >= MIN_LLM)
    out: dict[str, dict] = {}
    done = 0
    for name, ints in countries.items():
        keep = ints[:14]  # cap embedded size
        ch = hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:12]
        entry: dict = {"h": ch, "interactions": keep, "text": ""}
        if len(ints) >= MIN_LLM:
            old = prev.get(name)
            if old and old.get("h") == ch and old.get("text") and not refresh:
                entry["text"] = old["text"]
            else:
                lines = "\n".join(
                    f"- {x['with']} · {x['domain']} ({_word(x['sign'])}): {x['why']}".rstrip(": ")
                    for x in keep
                )
                txt = ollama(model, _COUNTRY_PROMPT.format(c=name, lines=lines), timeout=120)
                entry["text"] = (txt or "").strip()
                done += 1
                if done % 10 == 0:
                    print(f"  country summaries: {done}/{todo}")
        out[name] = entry
    print(f"  country summaries done ({todo} via LLM, {len(out)} total)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--refresh", action="store_true", help="regenerate even if cached")
    args = parser.parse_args()

    pairs = build_pairs()
    facts = build_facts(pairs)
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
    pair_reports = _pair_reports(args.model, args.refresh, cached, pairs)
    print("generating per-country summaries…")
    country_reports = _country_reports(args.model, args.refresh, cached, build_countries(pairs))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "hash": digest,
                "text": text,
                "facts": facts,
                "pairs": pair_reports,
                "countries": country_reports,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({len(pair_reports)} pairs, {len(country_reports)} countries)")


if __name__ == "__main__":
    main()
