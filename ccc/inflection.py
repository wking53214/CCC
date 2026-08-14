"""Candidate inflection-point detection with separate assessment dimensions."""

from __future__ import annotations

from dataclasses import replace

from .models import Actor, ActorType, InflectionPoint, InflectionStatus, new_id


class InflectionManager:
    def __init__(self, store, audit, rules) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules

    def detect_inflection(
        self,
        *,
        artifact_id: str | None = None,
        thread_id: str | None = None,
        directions: tuple[str, ...],
        divergence: float | None,
        sensitivity: float | None,
        actor: Actor,
        machine_weight: float | None = None,
        reason: str = "candidate trajectory change detected",
    ) -> InflectionPoint:
        self.rules.evaluate(
            "CCC-INFLECTION-001",
            bool(directions),
            reason="candidate detection requires an explicit direction and separate dimensions",
        )
        point = InflectionPoint(
            inflection_id=new_id("inflection"),
            artifact_id=artifact_id,
            thread_id=thread_id,
            detected_by=actor,
            directions=tuple(directions),
            divergence=divergence,
            sensitivity=sensitivity,
            significance=None,
            machine_weight=machine_weight,
            status=InflectionStatus.DETECTED,
            reason=reason,
        )
        self.store.add_inflection(point)
        self.audit.record(
            actor=actor,
            operation="DETECT_INFLECTION",
            object_id=point.inflection_id,
            previous_state=None,
            new_state={"status": point.status.value, "significance": None, "divergence": divergence, "sensitivity": sensitivity},
            reason=reason,
            constitutional_rule="CCC-INFLECTION-001",
        )
        return point

    def resolve_inflection(
        self,
        inflection_id: str,
        *,
        significance: str,
        actor: Actor,
        reason: str,
        authorization_basis: str,
    ) -> InflectionPoint:
        self.rules.evaluate(
            "CCC-HUMAN-001",
            actor.kind is ActorType.HUMAN,
            reason="inflection significance requires human resolution",
        )
        point = self.store.inflection_points[inflection_id]
        updated = replace(
            point,
            significance=significance,
            status=InflectionStatus.RESOLVED,
            human_resolution=reason,
        )
        self.store.replace_inflection(updated)
        self.audit.record(
            actor=actor,
            operation="RESOLVE_INFLECTION",
            object_id=inflection_id,
            previous_state={"status": point.status.value, "significance": point.significance},
            new_state={"status": updated.status.value, "significance": significance},
            reason=reason,
            constitutional_rule="CCC-HUMAN-001",
            authorization_basis=authorization_basis,
        )
        return updated
