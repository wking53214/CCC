"""Append-only constitutional audit trail."""

from __future__ import annotations

from typing import Any, Iterable

from .models import Actor, AuditEvent, ProvenanceStatus, new_id, utc_now


class AuditTrail:
    def __init__(self, store) -> None:
        self.store = store

    def record(
        self,
        *,
        actor: Actor,
        operation: str,
        object_id: str,
        previous_state: dict[str, Any] | None,
        new_state: dict[str, Any] | None,
        reason: str,
        provenance: ProvenanceStatus | None = None,
        evidence: Iterable[str] = (),
        constitutional_rule: str | None = None,
        authorization_basis: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=new_id("audit"),
            timestamp=utc_now(),
            actor=actor,
            operation=operation,
            object_id=object_id,
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            provenance=provenance,
            evidence=tuple(evidence),
            constitutional_rule=constitutional_rule,
            authorization_basis=authorization_basis,
        )
        self.store.append_audit(event)
        return event

    def for_object(self, object_id: str) -> tuple[AuditEvent, ...]:
        return tuple(event for event in self.store.audit_events if event.object_id == object_id)

    def all(self) -> tuple[AuditEvent, ...]:
        return tuple(self.store.audit_events)
