"""Export the *history* of World Observer's LLM syntheses (read-only).

WO snapshots its per-country / per-theatre narrative summary very frequently. This
exports one summary per day per entity from ``topic_summary_history`` so we can
track how the narrative *content* drifts over time — which topics/entities enter,
fade or persist. That drift is where the genuinely new, interpretable signal is.

    python examples/extract_world_observer_narrative_history.py
        → examples/data/world_observer_narrative_history.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = "/home/sebastien/Documents/world_observer/data/database/articles.db"
OUT_PATH = Path(__file__).parent / "data" / "world_observer_narrative_history.json"


def extract(db_path: str, window_hours: int, top_entities: int) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # actively-tracked entities (countries + theatres) with the most history
    keys = conn.execute(
        """
        SELECT dimension, key, COUNT(*) n
        FROM topic_summary_history
        WHERE lang='en' AND window_hours=?
          AND dimension IN ('country','theatre','category','global')
        GROUP BY dimension, key ORDER BY n DESC LIMIT ?
        """,
        (window_hours, top_entities),
    ).fetchall()

    out: list[dict] = []
    for k in keys:
        rows = conn.execute(
            """
            SELECT generated_at, text FROM topic_summary_history
            WHERE dimension=? AND key=? AND lang='en' AND window_hours=?
            ORDER BY generated_at
            """,
            (k["dimension"], k["key"], window_hours),
        ).fetchall()
        by_day: dict[str, str] = {}
        for r in rows:
            by_day[r["generated_at"][:10]] = r["text"]  # keep last summary of each day
        if len(by_day) >= 3:  # need at least a few days to see drift
            out.append({"dimension": k["dimension"], "key": k["key"], "by_day": by_day})

    conn.close()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--window-hours", type=int, default=72)
    parser.add_argument("--top-entities", type=int, default=200)
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    data = extract(args.db, args.window_hours, args.top_entities)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    days = sorted({d for e in data for d in e["by_day"]})
    span = f"{days[0]}..{days[-1]}" if days else "n/a"
    print(f"entities={len(data)} days={len(days)} ({span}) -> {out}")


if __name__ == "__main__":
    main()
