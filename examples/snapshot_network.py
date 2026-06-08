"""Save a dated snapshot of the multi-layer network for temporal analysis.

Captures the signed per-layer dyad stances, structural balance / blocs, maritime
disruption and the cached situation text into a dated file under
data/network_snapshots/. Deterministic (no LLM) — run it regularly (e.g. a daily
cron) to build a time series, then analyse it with network_evolution.py.

    python examples/snapshot_network.py [--cameo FILE] [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from multilayer import CAMEO, LAYERS, MARITIME, net_dyads, signed_analysis

SNAP_DIR = Path(__file__).parent / "data" / "network_snapshots"
SITUATION = Path(__file__).parent / "data" / "world_observer_situation.json"


def snapshot(cameo_path: Path, date: str | None = None, *, with_situation: bool = True) -> dict:
    cam = json.loads(cameo_path.read_text(encoding="utf-8"))
    if date is None:
        days = [e["day"] for e in cam if e.get("day")]
        date = max(days) if days else "unknown"
    net = net_dyads(cam)
    sa = signed_analysis(net)
    layers = {lay: {f"{a}|{b}": s for (a, b), s in net[lay].items()} for lay in LAYERS}
    mar = json.loads(MARITIME.read_text(encoding="utf-8")) if MARITIME.exists() else []
    maritime = {
        c["name"]: {"z": c["disruption"]["z_score"], "class": c["disruption"]["classification"]}
        for c in mar
        if c.get("disruption")
    }
    situation = ""
    if with_situation and SITUATION.exists():
        situation = json.loads(SITUATION.read_text(encoding="utf-8")).get("text", "")
    return {
        "date": date,
        "layers": layers,
        "balance_pct": round(sa["balance_pct"], 1),
        "bloc_A": sa["factions"][0],
        "bloc_B": sa["factions"][1],
        "tension_triads": [" - ".join(t) for t in sa["unbalanced"][:6]],
        "maritime": maritime,
        "situation": situation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cameo", default=str(CAMEO), help="CAMEO json to snapshot")
    parser.add_argument("--date", default=None, help="override snapshot date")
    args = parser.parse_args()

    snap = snapshot(Path(args.cameo), args.date, with_situation=args.date is None)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAP_DIR / f"{snap['date']}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    n_edges = sum(len(v) for v in snap["layers"].values())
    print(f"wrote snapshot {out.name} ({n_edges} signed edges, balance {snap['balance_pct']}%)")


if __name__ == "__main__":
    main()
