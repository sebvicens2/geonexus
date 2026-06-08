"""Anti-hallucination auditor for the CAMEO extractions (report-only).

For every extracted link (A | B | domain | class) it fact-checks three things against
the source summary:
  1. DIRECT   - do the two countries actually interact DIRECTLY in the text (not just
     co-mentioned, not via a third party)? (deterministic presence guard + judge)
  2. DOMAIN   - is the assigned domain (military/economic/diplomatic/energy/health) the
     right one for that interaction?
  3. STANCE   - does the text support the cooperative/conflictual nature?
A strict Qwen-14b judge answers all three in one call (default: no / wrong /
unsupported unless explicit). Aggregates trust scores, domain confusion, worst-
offending sources and the flagged links into a report. Report only; cached per item.

    python examples/verify_llm.py [--model qwen2.5:14b] [--limit N]
        → data/cameo_verification.json + reports/hallucination_report.md
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extract_cameo import ollama
from multilayer import NARR, _canon

RAW = Path(__file__).parent / "data" / "world_observer_cameo.json"  # audit the raw extraction
VERIFIED = Path(__file__).parent / "data" / "world_observer_cameo_verified.json"  # gated output
CACHE = Path(__file__).parent / "data" / "cameo_verification.json"
REPORT = Path("reports") / "hallucination_report.md"
STANCE = {2: "cooperation", 1: "cooperation", 0: "neutral", -1: "conflict", -2: "conflict"}
DOMAINS = {"military", "economic", "diplomatic", "energy", "health", "none"}
_STANCES = {"SUPPORTED", "UNSUPPORTED", "CONTRADICTED"}

_JUDGE = (
    "You are a strict fact-checker for an extracted country-to-country link.\n"
    "Given the SUMMARY and the extracted CLAIM, answer THREE questions on ONE line, "
    "pipe-separated, then a short reason:\n"
    "DIRECT | DOMAIN | STANCE | reason\n"
    "DIRECT = yes if the summary describes a DIRECT interaction BETWEEN the two countries "
    "(one acting on/with the other); no if they are merely co-mentioned, unrelated, or one "
    "is not really involved.\n"
    "DOMAIN = ok if the interaction's domain matches the claimed one; otherwise give the "
    "correct domain (military|economic|diplomatic|energy|health|none).\n"
    "STANCE = SUPPORTED|UNSUPPORTED|CONTRADICTED for the cooperative/conflictual nature.\n"
    "Be strict: default to no / the-true-domain / UNSUPPORTED when it is not explicit. "
    "Reason < 15 words.\n"
    "Output ONLY the answer line, no preamble, do not repeat the header. "
    "Example: yes | ok | SUPPORTED | A imposed sanctions on B\n\n"
    "SUMMARY:\n{text}\n\n"
    "CLAIM: {a} interacts with {b} | domain={domain} | stance={stance}"
)


def _summaries() -> dict[str, dict[str, str]]:
    data = json.loads(NARR.read_text(encoding="utf-8")) if NARR.exists() else []
    return {e["key"]: e["by_day"] for e in data}


def _present(name: str, text: str) -> bool:
    low = text.lower()
    return name.lower() in low or _canon(name).lower() in low


def _judge(model: str, e: dict, text: str) -> dict:
    stance_word = STANCE.get(e["sign"], "neutral")
    prompt = _JUDGE.format(
        text=text[:1600], a=e["a"], b=e["b"], domain=e["domain"], stance=stance_word
    )
    out = ollama(model, prompt, timeout=180) or ""
    # the answer line has >=2 pipes; ignore an echoed header line ("DIRECT | DOMAIN | ...")
    cands = [
        ln
        for ln in out.splitlines()
        if ln.count("|") >= 2 and "DIRECT" not in ln.upper().split("|")[0]
    ]
    line = cands[-1] if cands else ""
    parts = [p.strip() for p in line.split("|")]
    parts += [""] * (4 - len(parts))
    direct = parts[0].lower().startswith("y")
    dlow = parts[1].lower()
    if "ok" in dlow or e["domain"] in dlow:  # "ok" OR the judge restated the same domain
        domain_ok, domain_fix = True, ""
    else:
        domain_ok = False
        domain_fix = next((d for d in DOMAINS if d in dlow), "?")
    su = parts[2].upper()
    stance = next((v for v in _STANCES if su.startswith(v[:6])), "UNSUPPORTED")
    return {
        "direct": direct,
        "domain_ok": domain_ok,
        "domain_fix": domain_fix,
        "stance": stance,
        "reason": parts[3][:120],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    edges = json.loads(RAW.read_text(encoding="utf-8"))
    if args.limit:
        edges = edges[: args.limit]
    summ = _summaries()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    results = []
    for i, e in enumerate(edges, 1):
        text = summ.get(e["source"], {}).get(e.get("day", ""), "")
        present = _present(e["a"], text) and _present(e["b"], text)
        key = hashlib.sha256(
            json.dumps(
                [e["a"], e["b"], e["domain"], e["cameo"], e["source"], e.get("day")], sort_keys=True
            ).encode()
        ).hexdigest()[:16]
        if key in cache and "stance" in cache[key]:
            v = cache[key]
            if not v["domain_ok"] and v.get("domain_fix") == e["domain"]:
                v = {**v, "domain_ok": True, "domain_fix": ""}  # fix old-parse same-domain
        elif not text:
            v = {
                "direct": False,
                "domain_ok": False,
                "domain_fix": "?",
                "stance": "UNSUPPORTED",
                "reason": "source summary missing",
            }
            cache[key] = v
        else:
            v = _judge(args.model, e, text)
            cache[key] = v
        results.append({**e, "present": present, **v})
        if i % 20 == 0:
            print(f"  judged {i}/{len(edges)}")

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    _report(results)

    # gate: write the fully-valid links (the network prefers this file). Skip on --limit.
    keep = ("a", "b", "domain", "cameo", "sign", "source", "day")
    valid_edges = [
        {k: r[k] for k in keep if k in r}
        for r in results
        if r["direct"] and r["domain_ok"] and r["stance"] == "SUPPORTED"
    ]
    if not args.limit:
        VERIFIED.write_text(json.dumps(valid_edges, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"gated -> {VERIFIED.name} ({len(valid_edges)} fully-valid links kept)")

    n = len(results) or 1
    valid = len(valid_edges)
    print(
        f"\n{len(results)} links · fully-valid {valid} ({100 * valid // n}%) · "
        f"direct {sum(r['direct'] for r in results)} · "
        f"domain-ok {sum(r['domain_ok'] for r in results)} · "
        f"stance-supported {sum(1 for r in results if r['stance'] == 'SUPPORTED')}"
    )
    print(f"report -> {REPORT}")


def _report(results: list[dict]) -> None:
    n = len(results) or 1
    direct = sum(r["direct"] for r in results)
    dom_ok = sum(r["domain_ok"] for r in results)
    sup = sum(1 for r in results if r["stance"] == "SUPPORTED")
    valid = [r for r in results if r["direct"] and r["domain_ok"] and r["stance"] == "SUPPORTED"]
    bad = [r for r in results if r not in valid]
    confusion = collections.Counter(
        f"{r['domain']} -> {r['domain_fix']}" for r in results if not r["domain_ok"]
    )
    by_src = collections.Counter(r["source"] for r in bad)

    L = [
        "# GeoNexus — CAMEO link audit\n",
        f"_Strict fact-check of {len(results)} extracted links vs their source summaries: "
        "is the tie a DIRECT interaction between the two countries, is the DOMAIN right, is "
        "the STANCE supported? Report only — nothing is removed._\n",
        "## Trust scores\n",
        f"- **fully valid (direct + domain + stance): {len(valid)} ({100 * len(valid) // n}%)**",
        f"- direct interaction: {direct} ({100 * direct // n}%)",
        f"- domain correct: {dom_ok} ({100 * dom_ok // n}%)",
        f"- stance supported: {sup} ({100 * sup // n}%)",
        f"- both actors present in source (deterministic): {sum(r['present'] for r in results)}",
        "\n## Domain misclassification (claimed -> correct)\n",
    ]
    L += [f"- {k}: {c}" for k, c in confusion.most_common(12)] or ["- none"]
    L.append("\n## Most-flagged source summaries\n")
    L += [f"- {src}: {c}" for src, c in by_src.most_common(10)]
    L.append(f"\n## Flagged links ({len(bad)})\n")
    for r in bad:
        issues = []
        if not r["direct"]:
            issues.append("not-direct" + ("" if r["present"] else "/actor-absent"))
        if not r["domain_ok"]:
            issues.append(f"domain→{r['domain_fix']}")
        if r["stance"] != "SUPPORTED":
            issues.append(r["stance"].lower())
        L.append(
            f"- {r['a']} →[{r['domain']}]→ {r['b']} ({r['cameo']}): "
            f"**{', '.join(issues)}** — _{r['reason']}_"
        )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
