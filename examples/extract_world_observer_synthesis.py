"""Export World Observer's *aggregate synthesis* layer to a portable JSON file.

Unlike ``extract_world_observer_sample.py`` (which exports raw per-article events),
this pulls WO's already-computed, periodically-refreshed intelligence per
country / theatre — instability scores, attention shares, narratives, summaries —
plus a country co-occurrence graph derived from recent articles. Read-only.

    python examples/extract_world_observer_synthesis.py
        → examples/data/world_observer_synthesis.json

GeoNexus then *consumes WO's scores as node attributes* and adds the relational
layer (co-occurrence edges, clusters) on top, instead of recomputing attention.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

DEFAULT_DB = "/home/sebastien/Documents/world_observer/data/database/articles.db"
OUT_PATH = Path(__file__).parent / "data" / "world_observer_synthesis.json"

ALIASES = {
    "US": "United States",
    "U.S.": "United States",
    "USA": "United States",
    "UK": "United Kingdom",
    "DPRK": "North Korea",
    "PRC": "China",
}


def _canon(name: str) -> str:
    name = (name or "").strip()
    return ALIASES.get(name, name)


def _loads(blob: str | None) -> list:
    if not blob:
        return []
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return []


def _latest_by(rows: list[sqlite3.Row], key: str, ts: str) -> dict[str, sqlite3.Row]:
    """Keep the row with the most recent ``ts`` for each ``key``."""
    best: dict[str, sqlite3.Row] = {}
    for r in rows:
        k = r[key]
        if k not in best or str(r[ts]) > str(best[k][ts]):
            best[k] = r
    return best


def extract(db_path: str, days: int) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # --- per-country synthesis -------------------------------------------- #
    composite = {
        r["country"]: r
        for r in conn.execute(
            "SELECT country, score, classification, narrative FROM composite_snapshot"
        )
    }
    intel = _latest_by(
        conn.execute(
            "SELECT country, score, dominant_signal, computed_at FROM country_intelligence_index"
        ).fetchall(),
        "country",
        "computed_at",
    )

    # latest attention share per (dimension, key)
    att_rows = conn.execute("SELECT dimension, key, day, share FROM attention_snapshot").fetchall()
    latest_share: dict[tuple[str, str], float] = {}
    latest_day: dict[tuple[str, str], str] = {}
    for r in att_rows:
        dk = (r["dimension"], r["key"])
        if dk not in latest_day or r["day"] > latest_day[dk]:
            latest_day[dk] = r["day"]
            latest_share[dk] = r["share"]

    # english summaries per (dimension, key)
    summaries: dict[tuple[str, str], str] = {}
    for r in conn.execute(
        "SELECT dimension, key, text, generated_at FROM topic_summaries WHERE lang='en'"
    ):
        dk = (r["dimension"], r["key"])
        if dk not in summaries:  # rows are not ordered; keep first, good enough
            summaries[dk] = r["text"]

    countries = []
    for name, r in composite.items():
        nar = {}
        try:
            nar = json.loads(r["narrative"]) if r["narrative"] else {}
        except (json.JSONDecodeError, TypeError):
            nar = {}
        ci = intel.get(name)
        countries.append(
            {
                "name": name,
                "instability": float(r["score"]) if r["score"] is not None else None,
                "classification": r["classification"],
                "drivers": nar.get("drivers", [])[:3],
                "dominant_signal": nar.get("dominant_signal")
                or (ci["dominant_signal"] if ci else None),
                "intel_score": float(ci["score"]) if ci and ci["score"] is not None else None,
                "attention_share": latest_share.get(("country", name)),
                "summary": summaries.get(("country", name)),
            }
        )

    # --- per-theatre synthesis ------------------------------------------- #
    regional = _latest_by(
        conn.execute(
            "SELECT region, score, top_countries, computed_at FROM regional_intelligence_index"
        ).fetchall(),
        "region",
        "computed_at",
    )
    theatre_keys = {k for (dim, k) in latest_share if dim == "theatre"}
    theatres = []
    for key in sorted(theatre_keys):
        reg = regional.get(key)
        theatres.append(
            {
                "name": key,
                "attention_share": latest_share.get(("theatre", key)),
                "region_score": float(reg["score"]) if reg and reg["score"] is not None else None,
                "top_countries": [_canon(x) for x in _loads(reg["top_countries"])] if reg else [],
                "summary": summaries.get(("theatre", key)),
            }
        )

    # --- country co-occurrence from recent articles (the relational layer) - #
    country_names = {c["name"] for c in countries}
    rows = conn.execute(
        """
        SELECT m.countries FROM article_metadata m
        WHERE m.countries != '[]'
          AND m.created_at >= date('now', ?)
        """,
        (f"-{days} days",),
    ).fetchall()
    pair_w: dict[tuple[str, str], float] = defaultdict(float)
    for r in rows:
        names = sorted({_canon(x) for x in _loads(r["countries"]) if _canon(x) in country_names})
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                pair_w[(names[i], names[j])] += 1.0
    cooccurrence = [[a, b, w] for (a, b), w in pair_w.items() if w >= 2]
    cooccurrence.sort(key=lambda e: e[2], reverse=True)

    # --- attention time series (country + theatre) ----------------------- #
    series: dict[str, dict[str, dict[str, float]]] = {"country": {}, "theatre": {}}
    for r in att_rows:
        if r["dimension"] in series:
            series[r["dimension"]].setdefault(r["key"], {})[r["day"]] = r["share"]

    conn.close()
    return {
        "countries": countries,
        "theatres": theatres,
        "cooccurrence": cooccurrence,
        "attention_series": series,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--days", type=int, default=14, help="co-occurrence window")
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    data = extract(args.db, args.days)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"countries={len(data['countries'])} theatres={len(data['theatres'])} "
        f"cooccurrence_edges={len(data['cooccurrence'])} -> {out}"
    )


if __name__ == "__main__":
    main()
