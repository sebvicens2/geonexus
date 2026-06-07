"""EventMemory: store dated graph snapshots and compare them over time.

A snapshot is a frozen copy of an :class:`EventGraph` keyed by a date. From a
series of snapshots you can:

- track how a node's risk hotspot score evolves (:meth:`hotspot_series`),
- diff the hotspots between two dates — what *appeared*, *disappeared*,
  *intensified* or *faded* (:meth:`compare_hotspots`),
- diff the communities between two dates — what crises *emerged*, *dissolved*
  or *persisted* (:meth:`compare_clusters`).

Snapshots can optionally be persisted to a directory (one JSON file per date).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from eventgraph.graph.knowledge_graph import EventGraph


def _norm_date(value: str | date | datetime) -> str:
    """Normalise a date-ish value to an ``YYYY-MM-DD`` key."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _entities(members: set[str]) -> set[str]:
    """Keep only the stable (non-event) nodes of a cluster."""
    return {m for m in members if not m.startswith("event:")}


@dataclass(frozen=True, slots=True)
class HotspotChange:
    """How a node's risk hotspot score changed between two dates.

    ``status`` is one of ``appeared``, ``disappeared``, ``intensified``,
    ``faded`` or ``stable``.
    """

    node_id: str
    status: str
    before: float
    after: float

    @property
    def delta(self) -> float:
        return self.after - self.before

    def __str__(self) -> str:
        return f"{self.node_id:<26} {self.status:<12} {self.before:.3f} -> {self.after:.3f}"


@dataclass(frozen=True, slots=True)
class ClusterChange:
    """How one community changed between two dates.

    ``status`` is one of ``emerged``, ``dissolved`` or ``persisted``.
    """

    status: str
    label: str
    size: int
    added: tuple[str, ...]
    removed: tuple[str, ...]
    jaccard: float

    def __str__(self) -> str:
        return f"[{self.status:<9}] {self.label}  ({self.size} nodes, overlap={self.jaccard:.2f})"


@dataclass(frozen=True, slots=True)
class ClusterDiff:
    """Result of comparing communities between two dates."""

    changes: tuple[ClusterChange, ...]

    @property
    def emerged(self) -> list[ClusterChange]:
        return [c for c in self.changes if c.status == "emerged"]

    @property
    def dissolved(self) -> list[ClusterChange]:
        return [c for c in self.changes if c.status == "dissolved"]

    @property
    def persisted(self) -> list[ClusterChange]:
        return [c for c in self.changes if c.status == "persisted"]


class EventMemory:
    """A time-indexed collection of EventGraph snapshots."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self._dir = Path(directory) if directory else None
        self._snapshots: dict[str, EventGraph] = {}
        if self._dir and self._dir.exists():
            for f in sorted(self._dir.glob("*.json")):
                self._snapshots[f.stem] = EventGraph.load_json(f)

    # ------------------------------------------------------------------ #
    # storage
    # ------------------------------------------------------------------ #
    def snapshot(self, when: str | date | datetime, graph: EventGraph) -> str:
        """Freeze ``graph`` under date ``when`` and return the normalised key."""
        key = _norm_date(when)
        frozen = EventGraph.from_dict(graph.to_dict())  # decouple from later mutation
        self._snapshots[key] = frozen
        if self._dir is not None:
            self._dir.mkdir(parents=True, exist_ok=True)
            frozen.save_json(self._dir / f"{key}.json")
        return key

    def dates(self) -> list[str]:
        """All snapshot dates, ascending."""
        return sorted(self._snapshots)

    def get(self, when: str | date | datetime) -> EventGraph:
        """Return the snapshot stored at ``when``.

        Raises:
            KeyError: If no snapshot exists for that date.
        """
        return self._snapshots[_norm_date(when)]

    def __contains__(self, when: str | date | datetime) -> bool:
        return _norm_date(when) in self._snapshots

    def __len__(self) -> int:
        return len(self._snapshots)

    def label(self, node_id: str) -> str:
        """Human-readable label for a node, looked up in the latest snapshot holding it."""
        for key in reversed(self.dates()):
            g = self._snapshots[key]
            if node_id in g:
                return g.label(node_id)
        return node_id.split(":", 1)[-1]

    # ------------------------------------------------------------------ #
    # temporal analytics
    # ------------------------------------------------------------------ #
    def hotspot_series(self, *, top_k: int = 50) -> dict[str, dict[str, float]]:
        """Risk hotspot scores per date: ``{date: {node_id: score}}``."""
        return {
            key: {s.node_id: s.score for s in g.risk_hotspots(top_k=top_k)}
            for key, g in sorted(self._snapshots.items())
        }

    def compare_hotspots(
        self,
        before: str | date | datetime,
        after: str | date | datetime,
        *,
        top_k: int = 30,
        threshold: float = 0.05,
    ) -> list[HotspotChange]:
        """Diff risk hotspots between two dates.

        Args:
            before: Earlier snapshot date.
            after: Later snapshot date.
            top_k: How many hotspots to consider per snapshot.
            threshold: Minimum score change to count as intensified/faded.

        Returns:
            Changes sorted by descending delta (biggest risers first).
        """
        a = {s.node_id: s.score for s in self.get(before).risk_hotspots(top_k=top_k)}
        b = {s.node_id: s.score for s in self.get(after).risk_hotspots(top_k=top_k)}

        changes: list[HotspotChange] = []
        for node_id in a.keys() | b.keys():
            x, y = a.get(node_id, 0.0), b.get(node_id, 0.0)
            if x == 0.0 and y > 0.0:
                status = "appeared"
            elif y == 0.0 and x > 0.0:
                status = "disappeared"
            elif y - x >= threshold:
                status = "intensified"
            elif y - x <= -threshold:
                status = "faded"
            else:
                status = "stable"
            changes.append(HotspotChange(node_id=node_id, status=status, before=x, after=y))

        changes.sort(key=lambda c: c.delta, reverse=True)
        return changes

    def compare_clusters(
        self,
        before: str | date | datetime,
        after: str | date | datetime,
        *,
        min_size: int = 3,
        match_threshold: float = 0.3,
    ) -> ClusterDiff:
        """Diff communities between two dates by membership overlap.

        Clusters are matched on a *signature*: their most influential entity
        members (the dominant players), ignoring transient events and the long
        tail of one-off actors — so a theatre that recurs day to day is recognised
        as the same cluster. Above ``match_threshold`` (signature Jaccard) a
        cluster is ``persisted`` (with the players added/removed from its core);
        otherwise it ``emerged``. Earlier clusters left unmatched are ``dissolved``.
        """
        g_before, g_after = self.get(before), self.get(after)
        full_a = [set(c) for c in g_before.emerging_clusters(min_size=min_size)]
        full_b = [set(c) for c in g_after.emerging_clusters(min_size=min_size)]
        sig_a = [self._signature(g_before, c) for c in full_a]
        sig_b = [self._signature(g_after, c) for c in full_b]

        changes: list[ClusterChange] = []
        matched_a: set[int] = set()
        for members_b, signature_b in zip(full_b, sig_b, strict=True):
            best_idx, best_j = -1, 0.0
            for i, signature_a in enumerate(sig_a):
                j = _jaccard(signature_a, signature_b)
                if j > best_j:
                    best_idx, best_j = i, j
            label = self._cluster_label(g_after, members_b)
            if best_idx >= 0 and best_j >= match_threshold:
                matched_a.add(best_idx)
                changes.append(
                    ClusterChange(
                        status="persisted",
                        label=label,
                        size=len(members_b),
                        added=tuple(sorted(signature_b - sig_a[best_idx])),
                        removed=tuple(sorted(sig_a[best_idx] - signature_b)),
                        jaccard=best_j,
                    )
                )
            else:
                changes.append(
                    ClusterChange(
                        status="emerged",
                        label=label,
                        size=len(members_b),
                        added=tuple(sorted(signature_b)),
                        removed=(),
                        jaccard=best_j,
                    )
                )

        for i, members_a in enumerate(full_a):
            if i not in matched_a:
                changes.append(
                    ClusterChange(
                        status="dissolved",
                        label=self._cluster_label(g_before, members_a),
                        size=len(members_a),
                        added=(),
                        removed=tuple(sorted(sig_a[i])),
                        jaccard=0.0,
                    )
                )
        return ClusterDiff(tuple(changes))

    @staticmethod
    def _signature(graph: EventGraph, members: set[str], k: int = 8) -> set[str]:
        """A cluster's identity: its ``k`` most influential entity members."""
        entities = sorted(_entities(members), key=graph.influence_score, reverse=True)
        return set(entities[:k])

    @staticmethod
    def _cluster_label(graph: EventGraph, members: set[str], n: int = 3) -> str:
        """Name a cluster by its most influential non-event members."""
        entities = [m for m in members if not m.startswith("event:")]
        entities.sort(key=graph.influence_score, reverse=True)
        names = [graph.label(m) for m in entities[:n]]
        return ", ".join(names) if names else "(events only)"
