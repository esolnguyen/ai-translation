"""Sync reporting types shared by the indexer and the structured stores."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SyncDelta:
    """Per-collection outcome of one sync run."""

    added: int = 0
    updated: int = 0
    removed: int = 0


@dataclass(slots=True)
class SyncReport:
    """Aggregated outcome across every collection touched by a sync run."""

    deltas: dict[str, SyncDelta] = field(default_factory=dict)

    def record(self, collection: str, delta: SyncDelta) -> None:
        self.deltas[collection] = delta

    def format(self) -> str:
        """Human-readable summary for CLI output."""
        if not self.deltas:
            return "Nothing to sync."
        rows = ["collection           added  updated  removed"]
        for name in sorted(self.deltas):
            d = self.deltas[name]
            rows.append(f"{name:<20} {d.added:>5}  {d.updated:>7}  {d.removed:>7}")
        return "\n".join(rows)

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {
            name: {"added": d.added, "updated": d.updated, "removed": d.removed}
            for name, d in self.deltas.items()
        }
