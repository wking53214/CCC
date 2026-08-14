"""Conflict preservation and human-resolution workflow."""

from __future__ import annotations

from dataclasses import replace

from .models import (
    Actor,
    ActorType,
    ConflictClass,
    ConflictRecord,
    ConflictStatus,
    EpistemicStatus,
    new_id,
)


class ConflictManager:
    def __init__(self, store, audit, rules, uncertainty) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules
        self.uncertainty = uncertainty

    def classify_conflict(self, material_ids: tuple[str, ...]) -> ConflictClass:
        artifacts = [self.store.require_artifact(item) for item in material_ids]
        evidence_count = sum(item.epistemic_status in {EpistemicStatus.EVIDENCE, EpistemicStatus.HISTORICAL_RECORD} for item in artifacts)
        theory_artifacts = [item for item in artifacts if item.epistemic_status in {EpistemicStatus.THEORY, EpistemicStatus.INFERENCE, EpistemicStatus.INTERPRETATION}]
        theory_count = len(theory_artifacts)
        if evidence_count >= 2:
            return ConflictClass.EVIDENCE_VS_EVIDENCE
        if evidence_count and theory_count:
            if any(item.machine_origin for item in theory_artifacts):
                return ConflictClass.MACHINE_THEORY_VS_EVIDENCE
            return ConflictClass.THEORY_VS_EVIDENCE
        if len({item.provenance_status for item in artifacts}) > 1:
            return ConflictClass.PROVENANCE_CONFLICT
        return ConflictClass.EPISTEMIC_CONFLICT

    def detect_conflict(
        self,
        *,
        material_ids: tuple[str, ...],
        why_material: str,
        choices: tuple[str, ...],
        downstream_consequences: tuple[str, ...],
        remaining_uncertainty: tuple[str, ...],
        actor: Actor,
    ) -> ConflictRecord:
        if len(material_ids) < 2:
            raise ValueError("a conflict needs at least two material objects")
        classification = self.classify_conflict(material_ids)
        self.rules.evaluate(
            "CCC-CONFLICT-001",
            bool(why_material.strip()) and bool(remaining_uncertainty),
            reason="conflict presentation must preserve materiality and remaining uncertainty",
            evidence=material_ids,
        )
        conflict = ConflictRecord(
            conflict_id=new_id("conflict"),
            material_ids=tuple(material_ids),
            classification=classification,
            why_material=why_material,
            choices=tuple(choices),
            downstream_consequences=tuple(downstream_consequences),
            remaining_uncertainty=tuple(remaining_uncertainty),
            detected_by=actor,
        )
        self.store.add_conflict(conflict)
        self.audit.record(
            actor=actor,
            operation="DETECT_CONFLICT",
            object_id=conflict.conflict_id,
            previous_state=None,
            new_state={"classification": classification.value, "status": conflict.status.value},
            reason=why_material,
            evidence=material_ids,
            constitutional_rule="CCC-CONFLICT-001",
        )
        return conflict

    def present_conflict(self, conflict_id: str) -> ConflictRecord:
        return self.store.conflicts[conflict_id]

    def request_human_resolution(self, conflict_id: str, *, actor: Actor):
        conflict = self.store.conflicts[conflict_id]
        updated = replace(conflict, status=ConflictStatus.AWAITING_HUMAN)
        self.store.replace_conflict(updated)
        uncertainty = self.uncertainty.ask(
            context=f"conflict:{conflict_id}",
            known=tuple(conflict.material_ids),
            conflicted=(conflict.why_material,),
            candidates=conflict.choices,
            question="Which available resolution, if any, should govern this conflict?",
            actor=actor,
        )
        self.audit.record(
            actor=actor,
            operation="REQUEST_HUMAN_RESOLUTION",
            object_id=conflict_id,
            previous_state={"status": conflict.status.value},
            new_state={"status": updated.status.value, "uncertainty_id": uncertainty.uncertainty_id},
            reason="conflict remains unresolved pending human choice",
            evidence=conflict.material_ids,
            constitutional_rule="CCC-CONFLICT-001",
        )
        return uncertainty

    def record_resolution(
        self,
        conflict_id: str,
        *,
        choice: str,
        actor: Actor,
        reason: str,
        authorization_basis: str,
    ) -> ConflictRecord:
        self.rules.evaluate(
            "CCC-HUMAN-001",
            actor.kind is ActorType.HUMAN and bool(authorization_basis),
            reason="conflict resolution is a human decision",
        )
        conflict = self.store.conflicts[conflict_id]
        updated = replace(conflict, status=ConflictStatus.RESOLVED, human_resolution=choice, resolved_by=actor)
        self.store.replace_conflict(updated)
        self.audit.record(
            actor=actor,
            operation="RECORD_CONFLICT_RESOLUTION",
            object_id=conflict_id,
            previous_state={"status": conflict.status.value, "human_resolution": conflict.human_resolution},
            new_state={"status": updated.status.value, "human_resolution": choice},
            reason=reason,
            evidence=conflict.material_ids,
            constitutional_rule="CCC-HUMAN-001",
            authorization_basis=authorization_basis,
        )
        return updated
