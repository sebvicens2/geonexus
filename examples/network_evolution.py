"""Analyse how the multi-layer network evolves across dated snapshots.

Reads every snapshot in data/network_snapshots/ and reports, between the first and
last (and the per-date balance trend): which dyads escalated (moved toward conflict)
or de-escalated, which relations appeared or vanished, the structural-balance trend,
and maritime status changes.

    python examples/snapshot_network.py        # take snapshots over time, then:
    python examples/network_evolution.py       # → reports/world_observer_evolution.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SNAP_DIR = Path(__file__).parent / "data" / "network_snapshots"
REPORT = Path("reports") / "world_observer_evolution.md"


def _load() -> list[dict]:
    snaps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SNAP_DIR.glob("*.json"))]
    return sorted(snaps, key=lambda s: s["date"])


def _aggregate(snap: dict) -> dict[str, int]:
    """Net stance per dyad, summed across all layers."""
    agg: dict[str, int] = {}
    for layer in snap["layers"].values():
        for dyad, s in layer.items():
            agg[dyad] = agg.get(dyad, 0) + s
    return agg


def main() -> None:
    snaps = _load()
    if len(snaps) < 2:
        print(
            f"Only {len(snaps)} snapshot(s) in {SNAP_DIR}. Need >= 2 to compare.\n"
            "Take snapshots over time:  python examples/snapshot_network.py"
        )
        return

    first, last = snaps[0], snaps[-1]
    a0, a1 = _aggregate(first), _aggregate(last)
    dyads = set(a0) | set(a1)

    changes = []
    appeared, vanished = [], []
    for d in dyads:
        v0, v1 = a0.get(d), a1.get(d)
        if v0 is None:
            appeared.append((d, v1))
        elif v1 is None:
            vanished.append((d, v0))
        elif v1 != v0:
            changes.append((d, v0, v1, v1 - v0))

    escalations = sorted([c for c in changes if c[3] < 0], key=lambda c: c[3])
    deescalations = sorted([c for c in changes if c[3] > 0], key=lambda c: -c[3])

    def fmt(d: str) -> str:
        return d.replace("|", " — ")

    print(f"Evolution {first['date']} -> {last['date']}  ({len(snaps)} snapshots)\n")
    print(f"Structural balance: {first['balance_pct']}% -> {last['balance_pct']}%")
    print("Balance trend: " + " · ".join(f"{s['date']}:{s['balance_pct']}%" for s in snaps))

    print("\n▼ Biggest escalations (toward conflict):")
    for d, v0, v1, delta in escalations[:8]:
        print(f"  {fmt(d):42} {v0:+d} -> {v1:+d}  (Δ{delta:+d})")
    print("\n▲ Biggest de-escalations (toward cooperation):")
    for d, v0, v1, delta in deescalations[:8]:
        print(f"  {fmt(d):42} {v0:+d} -> {v1:+d}  (Δ{delta:+d})")
    print(f"\n+ New relations: {len(appeared)} · - Vanished: {len(vanished)}")
    for d, v in appeared[:6]:
        print(f"  + {fmt(d)} ({v:+d})")

    # maritime status changes
    mar_changes = []
    for name, m1 in last.get("maritime", {}).items():
        m0 = first.get("maritime", {}).get(name)
        if m0 and m0["class"] != m1["class"]:
            mar_changes.append(f"{name}: {m0['class']} -> {m1['class']}")

    _write_md(snaps, first, last, escalations, deescalations, appeared, vanished, mar_changes)
    print(f"\nMarkdown report written to {REPORT}")


def _write_md(snaps, first, last, esc, deesc, appeared, vanished, mar_changes) -> None:
    def fmt(d: str) -> str:
        return d.replace("|", " — ")

    L = [
        f"# World Observer — network evolution ({first['date']} → {last['date']})\n",
        f"_{len(snaps)} dated snapshots of the signed multi-layer network. Net stance per "
        "dyad summed across layers; media-derived._\n",
        "## Structural balance trend\n",
        "| date | balance |",
        "| --- | --: |",
    ]
    L += [f"| {s['date']} | {s['balance_pct']}% |" for s in snaps]
    L.append("\n## Biggest escalations (toward conflict)\n")
    L += [f"- **{fmt(d)}**: {v0:+d} → {v1:+d} (Δ{dl:+d})" for d, v0, v1, dl in esc[:10]]
    L.append("\n## Biggest de-escalations (toward cooperation)\n")
    L += [f"- **{fmt(d)}**: {v0:+d} → {v1:+d} (Δ{dl:+d})" for d, v0, v1, dl in deesc[:10]]
    L.append(f"\n## New relations ({len(appeared)})\n")
    L += [f"- {fmt(d)} ({v:+d})" for d, v in appeared[:15]]
    L.append(f"\n## Vanished relations ({len(vanished)})\n")
    L += [f"- {fmt(d)} (was {v:+d})" for d, v in vanished[:15]]
    if mar_changes:
        L.append("\n## Maritime status changes\n")
        L += [f"- {m}" for m in mar_changes]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
