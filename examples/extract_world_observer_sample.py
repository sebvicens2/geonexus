"""Extract a real sample of World Observer events into a portable JSON file.

This is the ONLY piece that touches World Observer, and it only *reads* its
SQLite database (never modifies it). Run it once on a machine that has the WO
database; it writes ``examples/data/world_observer_sample.json``, which the demo
and map scripts then consume. EventGraph itself stays fully independent of WO.

Usage:
    python examples/extract_world_observer_sample.py \
        --db /home/sebastien/Documents/world_observer/data/database/articles.db \
        --min-importance 4 --limit 350
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = "/home/sebastien/Documents/world_observer/data/database/articles.db"
OUT_PATH = Path(__file__).parent / "data" / "world_observer_sample.json"


def _loads(blob: str | None) -> list[str]:
    """Parse a JSON-array text column into a clean list of non-empty strings."""
    if not blob:
        return []
    try:
        items = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(x).strip() for x in items if isinstance(x, str) and x.strip()]


def extract(
    db_path: str,
    min_importance: float,
    limit: int,
    per_day: int | None = None,
    days: int | None = None,
) -> list[dict[str, object]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # one category label per article (the most frequent non-empty one)
    cat_rows = conn.execute(
        """
        SELECT article_id, category, COUNT(*) AS n
        FROM article_analysis
        WHERE category IS NOT NULL AND category NOT IN ('', 'uncategorized')
        GROUP BY article_id, category
        """
    ).fetchall()
    categories: dict[str, str] = {}
    best: dict[str, int] = {}
    for r in cat_rows:
        aid, cat, n = r["article_id"], r["category"], r["n"]
        if n > best.get(aid, 0):
            best[aid] = n
            categories[aid] = cat

    # NB: articles.published_at holds raw RSS date strings of mixed formats, so we
    # use article_metadata.created_at (always ISO-8601) as the authoritative date.
    rows = conn.execute(
        """
        SELECT m.article_id, a.title, a.published_at, m.created_at, m.importance_score,
               m.theatre_override, m.countries, m.actors, m.organizations, m.commodities
        FROM article_metadata m
        JOIN articles a ON a.id = m.article_id
        WHERE m.countries != '[]' AND m.actors != '[]'
          AND m.importance_score >= ?
          AND a.title IS NOT NULL
        ORDER BY m.created_at DESC, m.importance_score DESC
        """,
        (min_importance,),
    ).fetchall()
    conn.close()

    def record(r: sqlite3.Row) -> dict[str, object]:
        return {
            "id": r["article_id"],
            "title": r["title"].strip(),
            "date": r["created_at"][:10],
            "published_at": r["published_at"],
            "importance": float(r["importance_score"] or 0.0),
            "category": categories.get(r["article_id"]) or r["theatre_override"] or "general",
            "theatre": r["theatre_override"],
            "countries": _loads(r["countries"]),
            "actors": _loads(r["actors"]),
            "organizations": _loads(r["organizations"]),
            "commodities": _loads(r["commodities"]),
        }

    if per_day is None:
        return [record(r) for r in rows[:limit]]

    # timeline mode: keep up to `per_day` events for each of the most recent `days`
    events: list[dict[str, object]] = []
    seen_days: list[str] = []
    per_count: dict[str, int] = {}
    for r in rows:
        day = r["created_at"][:10]
        if day not in seen_days:
            if days is not None and len(seen_days) >= days:
                break
            seen_days.append(day)
        if per_count.get(day, 0) >= per_day:
            continue
        per_count[day] = per_count.get(day, 0) + 1
        events.append(record(r))
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--min-importance", type=float, default=4.0)
    parser.add_argument("--limit", type=int, default=350)
    parser.add_argument(
        "--per-day", type=int, default=None, help="timeline mode: keep this many events per day"
    )
    parser.add_argument(
        "--days", type=int, default=None, help="timeline mode: number of most recent days to cover"
    )
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    events = extract(args.db, args.min_importance, args.limit, args.per_day, args.days)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(events)} events -> {out}")


if __name__ == "__main__":
    main()
