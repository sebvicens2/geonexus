"""Anti-hallucination auditor for the CAMEO extractions (report-only).

For every extracted interaction (A | B | domain | class) it checks:
  1. deterministic guard — do both actors actually appear in the source summary?
  2. LLM judge (strict, Qwen 14b) — does the source SUPPORT / not support / CONTRADICT
     the claimed interaction? (default UNSUPPORTED unless explicit.)
Then it aggregates a trust score, the worst offenders, and per-domain / per-source
patterns into a report. It does NOT modify the network (report only); cached by item.

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
from multilayer import CAMEO, NARR, _canon

CACHE = Path(__file__).parent / "data" / "cameo_verification.json"
REPORT = Path("reports") / "hallucination_report.md"
STANCE = {2: "cooperation", 1: "cooperation", 0: "neutral", -1: "conflict", -2: "conflict"}

_JUDGE = (
    "You are a strict fact-checker. Given a NEWS SUMMARY and a CLAIM about an "
    "interaction between two actors, decide whether the summary SUPPORTS the claim.\n"
    "Reply on ONE line: VERDICT | short reason (<15 words).\n"
    "VERDICT is exactly one of:\n"
    "  SUPPORTED   - the text clearly states this interaction and its cooperative/"
    "conflictual nature.\n"
    "  UNSUPPORTED - not stated, or you cannot tell.\n"
    "  CONTRADICTED- the text states the opposite stance.\n"
    "Be strict: if it is not explicit, answer UNSUPPORTED.\n\n"
    "SUMMARY:\n{text}\n\nCLAIM: {claim}"
)
_VERDICTS = {"SUPPORTED", "UNSUPPORTED", "CONTRADICTED"}


def _summaries() -> dict[str, dict[str, str]]:
    data = json.loads(NARR.read_text(encoding="utf-8")) if NARR.exists() else []
    return {e["key"]: e["by_day"] for e in data}


def _present(name: str, text: str) -> bool:
    """Loose check that an actor appears in the source (raw form or canonical name)."""
    low = text.lower()
    return name.lower() in low or _canon(name).lower() in low


def _claim(e: dict) -> str:
    stance = STANCE.get(e["sign"], "neutral")
    return (
        f"In the {e['domain']} domain, {e['a']} acted toward {e['b']} "
        f"in a {stance} way ({e['cameo'].replace('_', ' ')})."
    )


def _judge(model: str, text: str, claim: str) -> tuple[str, str]:
    out = ollama(model, _JUDGE.format(text=text[:1600], claim=claim), timeout=180) or ""
    line = next((ln for ln in out.splitlines() if ln.strip()), "")
    head = line.split("|", 1)
    verdict = head[0].strip().upper().rstrip(".")
    verdict = next((v for v in _VERDICTS if verdict.startswith(v[:6])), "UNSUPPORTED")
    reason = head[1].strip() if len(head) > 1 else ""
    return verdict, reason[:120]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--limit", type=int, default=0, help="judge only the first N (testing)")
    args = ap.parse_args()

    edges = json.loads(CAMEO.read_text(encoding="utf-8"))
    if args.limit:
        edges = edges[: args.limit]
    summ = _summaries()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    results = []
    todo = len(edges)
    for i, e in enumerate(edges, 1):
        text = summ.get(e["source"], {}).get(e.get("day", ""), "")
        present = _present(e["a"], text) and _present(e["b"], text)
        key = hashlib.sha256(
            json.dumps(
                [e["a"], e["b"], e["domain"], e["cameo"], e["source"], e.get("day")], sort_keys=True
            ).encode()
        ).hexdigest()[:16]
        if key in cache:
            verdict, reason = cache[key]["verdict"], cache[key]["reason"]
        elif not text:
            verdict, reason = "UNSUPPORTED", "source summary missing"
            cache[key] = {"verdict": verdict, "reason": reason}
        else:
            verdict, reason = _judge(args.model, text, _claim(e))
            cache[key] = {"verdict": verdict, "reason": reason}
        results.append({**e, "present": present, "verdict": verdict, "reason": reason})
        if i % 20 == 0:
            print(f"  judged {i}/{todo}")

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    _report(results)
    n = len(results)
    counts = collections.Counter(r["verdict"] for r in results)
    print(
        f"\n{n} edges · SUPPORTED {counts['SUPPORTED']} · "
        f"UNSUPPORTED {counts['UNSUPPORTED']} · CONTRADICTED {counts['CONTRADICTED']} · "
        f"actor-absent {sum(1 for r in results if not r['present'])}"
    )
    print(f"report -> {REPORT}")


def _report(results: list[dict]) -> None:
    n = len(results) or 1
    counts = collections.Counter(r["verdict"] for r in results)
    absent = [r for r in results if not r["present"]]
    bad = [r for r in results if r["verdict"] != "SUPPORTED"]
    by_dom = collections.Counter(r["domain"] for r in bad)
    by_src = collections.Counter(r["source"] for r in bad)

    L = [
        "# GeoNexus — CAMEO hallucination audit\n",
        f"_Strict fact-check of {len(results)} extracted interactions against their source "
        "summaries (deterministic guard + LLM judge). Report only — nothing is removed._\n",
        "## Trust score\n",
        f"- **SUPPORTED: {counts['SUPPORTED']} ({100 * counts['SUPPORTED'] // n}%)**",
        f"- UNSUPPORTED: {counts['UNSUPPORTED']} ({100 * counts['UNSUPPORTED'] // n}%)",
        f"- CONTRADICTED: {counts['CONTRADICTED']} ({100 * counts['CONTRADICTED'] // n}%)",
        f"- actor absent from source (deterministic flag): {len(absent)}",
        "\n## Most-hallucinating sources (summaries)\n",
    ]
    L += [f"- {src}: {c} flagged" for src, c in by_src.most_common(10)]
    L.append("\n## Flagged by domain\n")
    L += [f"- {dom}: {c}" for dom, c in by_dom.most_common()]
    L.append("\n## Contradicted / unsupported interactions\n")
    for r in sorted(bad, key=lambda r: r["verdict"]):
        flag = "" if r["present"] else " ⚠actor-absent"
        L.append(
            f"- **{r['verdict']}** {r['a']} →[{r['domain']}]→ {r['b']} "
            f"({r['cameo']}){flag} — _{r['reason']}_"
        )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
