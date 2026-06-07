"""World Observer over time: EventMemory snapshots, cluster & hotspot diffs.

Builds one graph snapshot per day from a 14-day World Observer sample, stores them
in an EventMemory, then:

    - diffs the hotspots between the first and last day
      (what appeared / intensified / faded),
    - diffs the communities (which crises emerged / dissolved / persisted),
    - renders the risk-hotspot evolution as a line chart
      (world_observer_timeline.png).

Run:
    python examples/world_observer_timeline_demo.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from world_observer_common import build_graph

from eventgraph import EventMemory
from eventgraph.visualization import plot_hotspot_evolution

TIMELINE = Path(__file__).parent / "data" / "world_observer_timeline.json"
PNG_PATH = Path("world_observer_timeline.png")


def build_memory() -> EventMemory:
    import json

    events: list[dict[str, Any]] = json.loads(TIMELINE.read_text(encoding="utf-8"))
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        by_day[e["date"]].append(e)

    memory = EventMemory()
    for day in sorted(by_day):
        if len(by_day[day]) < 20:  # skip sparse days that would distort the series
            continue
        memory.snapshot(day, build_graph(by_day[day]))
    return memory


def _rule(title: str) -> None:
    print(f"\n{title}")
    print("─" * len(title))


def main() -> None:
    memory = build_memory()
    dates = memory.dates()
    first, last = dates[0], dates[-1]
    print(f"Stored {len(memory)} daily snapshots ({first} → {last}).")

    _rule(f"Hotspot changes  {first} → {last}")
    changes = memory.compare_hotspots(first, last, top_k=25, threshold=0.05)
    movers = [c for c in changes if c.status != "stable"]
    for c in movers[:6]:
        print(f"  ▲ {memory.label(c.node_id):<24} {c.status:<12} {c.before:.2f} → {c.after:.2f}")
    for c in reversed(movers[-6:]):
        if c.delta < 0:
            print(
                f"  ▼ {memory.label(c.node_id):<24} {c.status:<12} {c.before:.2f} → {c.after:.2f}"
            )

    _rule(f"Cluster changes  {first} → {last}")
    diff = memory.compare_clusters(first, last, min_size=4)
    for c in diff.emerged[:4]:
        print(f"  + EMERGED   {c.label}  ({c.size} nodes)")
    for c in diff.dissolved[:4]:
        print(f"  - DISSOLVED {c.label}  ({c.size} nodes)")
    for c in diff.persisted[:4]:
        grew = len(c.added) - len(c.removed)
        trend = "growing" if grew > 0 else "shrinking" if grew < 0 else "steady"
        print(f"  = PERSISTED {c.label}  ({trend}: +{len(c.added)}/-{len(c.removed)})")

    _rule("Rendering risk-hotspot evolution")
    fig, ax = plt.subplots(figsize=(12, 6))
    plot_hotspot_evolution(memory, top_k=6, ax=ax)
    fig.tight_layout()
    fig.savefig(PNG_PATH, dpi=130, bbox_inches="tight")
    print(f"  wrote {PNG_PATH}")


if __name__ == "__main__":
    main()
