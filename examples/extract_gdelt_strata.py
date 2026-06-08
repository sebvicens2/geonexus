"""Normalise the GDELT per-domain 20-year export (the inertia baseline).

Reads examples/data/gdelt_strata.json (BigQuery export: per country-pair x domain
{military|economic|diplomatic}, ~2005+, avg Goldstein tone) and writes it keyed by
our country names, for blending as long-run INERTIA into the recent news layers.

    python examples/extract_gdelt_strata.py
        → examples/data/world_observer_gdelt_strata.json
"""

from __future__ import annotations

import json
from pathlib import Path

from extract_gdelt_baseline import ISO3_NAME  # reuse the ISO3 -> name table

SRC = Path(__file__).parent / "data" / "gdelt_strata.json"
OUT = Path(__file__).parent / "data" / "world_observer_gdelt_strata.json"
MIN_EVENTS = 5000  # 20-year (pair, domain) cell must have >= this many events


def main() -> None:
    if not SRC.exists():
        print(f"{SRC} not found — export the per-domain GDELT query there first.")
        return
    out = []
    for r in json.loads(SRC.read_text(encoding="utf-8")):
        a, b = ISO3_NAME.get(r["a"]), ISO3_NAME.get(r["b"])
        if not a or not b or a == b or int(r["events"]) < MIN_EVENTS:
            continue
        out.append(
            {
                "a": a,
                "b": b,
                "domain": r["domain"],
                "net": round(float(r["avg_goldstein"]), 2),  # net tone over ~20y (-10..+10)
                "events": int(r["events"]),
            }
        )
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(out)} historical (pair, domain) cells (>= {MIN_EVENTS} ev) -> {OUT}")


if __name__ == "__main__":
    main()
