"""Export World Observer's HARD maritime layer (chokepoints + PortWatch disruption).

This is real, non-media data: structured chokepoint nodes (Hormuz, Bab el-Mandeb…)
with their traffic and theatres, joined to PortWatch disruption scores (baseline vs
recent activity, z-score, classification). Chokepoints carry a `theatres` field, so
they plug straight into the news CAMEO layers (same theatre vocabulary).

    python examples/extract_maritime.py  → examples/data/world_observer_maritime.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from difflib import get_close_matches
from pathlib import Path

DEFAULT_DB = "/home/sebastien/Documents/world_observer/data/database/articles.db"
OUT_PATH = Path(__file__).parent / "data" / "world_observer_maritime.json"


_FILLER = {"strait", "straits", "canal", "of", "the", "gulf", "passage", "channel", "sea"}


def _core(name: str) -> str:
    """Distinctive token(s) of a chokepoint name, minus generic words."""
    return " ".join(w for w in name.lower().replace("-", " ").split() if w not in _FILLER)


def _commodity(desc: str) -> str:
    d = (desc or "").lower()
    if "oil" in d or "crude" in d or "bbl" in d:
        return "oil"
    if "grain" in d or "wheat" in d:
        return "grain"
    if "gas" in d or "lng" in d:
        return "gas"
    return "trade"


def extract(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # latest disruption score per chokepoint, keyed by port_name
    disruption: dict[str, sqlite3.Row] = {}
    for r in conn.execute(
        "SELECT port_name, recent_mean, baseline_mean, delta_pct, z_score, classification, "
        "computed_at FROM portwatch_disruption_scores WHERE port_type='chokepoint' "
        "ORDER BY computed_at DESC"
    ):
        disruption.setdefault(r["port_name"], r)
    core_to_name = {_core(name): name for name in disruption}
    cores = list(core_to_name)

    chokepoints = []
    for r in conn.execute(
        "SELECT id, name, short_name, lat, lon, region, importance, chokepoint_type, "
        "description, theatres, traffic_volume FROM chokepoints"
    ):
        query = _core(r["short_name"] or r["name"])
        match = get_close_matches(query, cores, n=1, cutoff=0.6)
        d = disruption.get(core_to_name[match[0]]) if match else None
        chokepoints.append({
            "id": r["id"],
            "name": r["short_name"] or r["name"],
            "region": r["region"],
            "importance": r["importance"],
            "type": r["chokepoint_type"],
            "theatres": json.loads(r["theatres"]) if r["theatres"] else [],
            "traffic": r["traffic_volume"],
            "commodity": _commodity(r["description"]),
            "description": (r["description"] or "")[:160],
            "disruption": None if d is None else {
                "z_score": d["z_score"],
                "delta_pct": d["delta_pct"],
                "classification": d["classification"],
            },
        })
    conn.close()
    return chokepoints


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    data = extract(args.db)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    matched = sum(1 for c in data if c["disruption"])
    print(f"wrote {len(data)} chokepoints ({matched} with PortWatch disruption) -> {out}")


if __name__ == "__main__":
    main()
