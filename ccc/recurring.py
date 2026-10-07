"""Recurring groups: what CCC has already decided keeps happening.

`record_external_finding` links a repeat sighting of a machine finding to
the earlier one, so recorded findings form groups (CCC's anomaly -> pattern
ladder runs on these). CCC built the groups but nothing listed them. This
module lists them, read-only, so a consumer can show "these 14 findings are
3 recurring problems" without keeping its own copy or re-deciding what
counts as the same problem.

How a group is read, all from what CCC already recorded:

- Members: every discovery connected through `relationships`, in either
  direction. This is the same reachability `record_external_finding` uses,
  so a chain d1 <- d2 <- d3 is one group.
- Occurrences: members that are not anti-probability duplicates. A
  duplicate is a re-observation, kept in the group but never counted.
- Stage: the stage of the group's representative, the member furthest up
  the ladder (earliest event time, then id, breaking ties). The same rule
  `record_external_finding` uses to pick it.
- needs_human_review: True when the group is a PATTERN with three or more
  occurrences. That is exactly when CCC starts raising REPEATED_RETURN road
  signs; MANDATE stays human-only, and this module changes nothing.

Nothing here writes. The groups are recomputed from the store each call.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import AnalysisStage, DiscoveryRecord

__all__ = ["RecurringGroup", "recurring_groups"]

# Kept equal to the values in system.py (imported there for recording);
# duplicated rather than imported to avoid a circular import.
_DUPLICATE_METHOD_MARKER = "duplicate detection"
_STAGE_RANK = {
    AnalysisStage.ANOMALY: 0,
    AnalysisStage.PATTERN: 1,
    AnalysisStage.MANDATE: 2,
    None: -1,
}


def _event_key(record: DiscoveryRecord) -> tuple:
    if record.event_start_date is not None:
        return (0, record.event_start_date)
    return (1, record.created_at)


def _event_date(record: DiscoveryRecord) -> str:
    return record.event_start_date or record.created_at


@dataclass(frozen=True)
class RecurringGroup:
    """One group of linked findings, as CCC recorded them."""

    representative_id: str
    stage: AnalysisStage | None
    conclusion: str
    occurrences: tuple[str, ...]
    duplicates: tuple[str, ...]
    first_seen: str
    last_seen: str

    @property
    def occurrence_count(self) -> int:
        return len(self.occurrences)

    @property
    def needs_human_review(self) -> bool:
        return self.stage is AnalysisStage.PATTERN and self.occurrence_count >= 3


def recurring_groups(discoveries: dict[str, DiscoveryRecord], *, min_occurrences: int = 1) -> tuple[RecurringGroup, ...]:
    """Every group of linked findings, most serious first.

    Ordered by stage (MANDATE, PATTERN, ANOMALY), then occurrence count, then
    representative id. `min_occurrences` hides groups smaller than that
    (pass 2 to see only things that happened more than once).
    """
    if isinstance(min_occurrences, bool) or not isinstance(min_occurrences, int) or min_occurrences < 1:
        raise ValueError("min_occurrences must be a positive integer")

    neighbours: dict[str, set[str]] = {did: set() for did in discoveries}
    for did, record in discoveries.items():
        for rel in record.relationships:
            if rel in discoveries and rel != did:
                neighbours[did].add(rel)
                neighbours[rel].add(did)

    seen: set[str] = set()
    groups: list[RecurringGroup] = []
    for start in sorted(discoveries):
        if start in seen:
            continue
        members = {start}
        frontier = [start]
        while frontier:
            for nxt in neighbours[frontier.pop()]:
                if nxt not in members:
                    members.add(nxt)
                    frontier.append(nxt)
        seen |= members

        duplicates = sorted(d for d in members if _DUPLICATE_METHOD_MARKER in discoveries[d].method)
        occurrences = sorted(members - set(duplicates)) or sorted(members)
        rep_id = min(
            occurrences,
            key=lambda d: (-_STAGE_RANK[discoveries[d].stage], _event_key(discoveries[d]), d),
        )
        rep = discoveries[rep_id]
        dates = sorted(_event_date(discoveries[d]) for d in occurrences)
        groups.append(RecurringGroup(
            representative_id=rep_id,
            stage=rep.stage,
            conclusion=rep.conclusion,
            occurrences=tuple(occurrences),
            duplicates=tuple(duplicates),
            first_seen=dates[0],
            last_seen=dates[-1],
        ))

    groups = [g for g in groups if g.occurrence_count >= min_occurrences]
    groups.sort(key=lambda g: (-_STAGE_RANK[g.stage], -g.occurrence_count, g.representative_id))
    return tuple(groups)
