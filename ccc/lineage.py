"""Explicit lineage relationships and immutable lifecycle events."""

from __future__ import annotations

from typing import Iterable

from .models import (
    Actor,
    LineageEvent,
    ProvenanceStatus,
    RelationshipType,
    new_id,
    utc_now,
)


class LineageManager:
    def __init__(self, store, audit, rules) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules

    def link(
        self,
        source_id: str,
        target_id: str,
        relationship: RelationshipType,
        *,
        actor: Actor,
        reason: str,
        previous_state: str | None = None,
        new_state: str | None = None,
        provenance: ProvenanceStatus | None = None,
        evidence: Iterable[str] = (),
    ) -> LineageEvent:
        self.store.require_artifact(source_id) if source_id in self.store.artifacts else None
        self.store.require_artifact(target_id) if target_id in self.store.artifacts else None
        self.rules.evaluate(
            "CCC-HISTORY-001" if relationship in {RelationshipType.CORRECTS, RelationshipType.AMENDS, RelationshipType.SUPERSEDES} else "CCC-ID-001",
            True,
            reason="explicit immutable lineage event recorded",
            evidence=evidence,
        )
        event = LineageEvent(
            event_id=new_id("lineage"),
            source_id=source_id,
            target_id=target_id,
            relationship=relationship,
            actor=actor,
            reason=reason,
            timestamp=utc_now(),
            previous_state=previous_state,
            new_state=new_state,
            provenance=provenance,
        )
        self.store.append_lineage(event)
        self.audit.record(
            actor=actor,
            operation=f"LINEAGE_{relationship.value}",
            object_id=target_id,
            previous_state={"source_id": source_id, "relationship": relationship.value},
            new_state={"target_id": target_id, "relationship": relationship.value},
            reason=reason,
            provenance=provenance,
            evidence=evidence,
            constitutional_rule="CCC-HISTORY-001",
        )
        return event

    def for_object(self, object_id: str) -> tuple[LineageEvent, ...]:
        return tuple(
            event
            for event in self.store.lineage_events
            if event.source_id == object_id or event.target_id == object_id
        )

    def related(self, object_id: str, relationship: RelationshipType | None = None) -> tuple[LineageEvent, ...]:
        events = self.for_object(object_id)
        if relationship is not None:
            events = tuple(event for event in events if event.relationship is relationship)
        return events
