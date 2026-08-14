"""Chain-independent epistemic state transitions."""

from __future__ import annotations

from dataclasses import replace

from .errors import ConstitutionViolation, InvalidTransition
from .models import (
    Actor,
    ActorType,
    ArtifactState,
    EpistemicEvent,
    EpistemicStatus,
    new_id,
    utc_now,
)


class EpistemicManager:
    def __init__(self, store, audit, rules, evidence) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules
        self.evidence = evidence

    def validate_initial(self, *, actor: Actor, status: EpistemicStatus) -> None:
        if status in {EpistemicStatus.HISTORICAL_RECORD, EpistemicStatus.EVIDENCE} and actor.kind in {ActorType.MODEL, ActorType.SYSTEM}:
            self.rules.evaluate(
                "CCC-RATIFICATION-001",
                False,
                reason="machine-generated material cannot be ingested as human-established history/evidence",
            )
        if status is EpistemicStatus.HISTORICAL_RECORD and actor.kind is ActorType.EXTERNAL:
            self.rules.evaluate(
                "CCC-EPISTEMIC-001",
                False,
                reason="external material requires human classification before historical-record status",
            )

    def transition(
        self,
        artifact_id: str,
        target: EpistemicStatus,
        *,
        actor: Actor,
        reason: str,
        evidence_ids: tuple[str, ...] = (),
    ):
        artifact = self.store.require_artifact(artifact_id)
        current = artifact.epistemic_status
        if artifact.state is ArtifactState.ERASED:
            raise ConstitutionViolation("CCC-HISTORY-002", "erased material cannot be reclassified")
        if current is target:
            raise InvalidTransition(f"{current.value} -> {target.value} is not a transition")
        if current is EpistemicStatus.SIMULATION and target in {
            EpistemicStatus.HISTORICAL_RECORD,
            EpistemicStatus.EVIDENCE,
        }:
            self.rules.evaluate(
                "CCC-EPISTEMIC-002",
                False,
                reason="simulation output cannot become historical record or evidence",
            )
        if target in {EpistemicStatus.HISTORICAL_RECORD, EpistemicStatus.EVIDENCE}:
            self.rules.evaluate(
                "CCC-EPISTEMIC-001",
                actor.kind is ActorType.HUMAN,
                reason="promotion into historical/evidence status requires human action",
                evidence=evidence_ids,
            )
            if artifact.metadata.get("machine_consensus"):
                self.rules.evaluate(
                    "CCC-RATIFICATION-001",
                    False,
                    reason="machine consensus cannot be converted into human-established fact",
                )
            if current in {
                EpistemicStatus.INFERENCE,
                EpistemicStatus.INTERPRETATION,
                EpistemicStatus.THEORY,
                EpistemicStatus.CONFLICTED,
            }:
                validation = self.evidence.validate_evidence_chain(artifact_id)
                if evidence_ids and not validation.valid:
                    raise ConstitutionViolation(
                        "CCC-EPISTEMIC-003",
                        "promotion requires a valid evidentiary root",
                        evidence=validation.roots,
                    )
                if not validation.valid:
                    raise ConstitutionViolation(
                        "CCC-EPISTEMIC-003",
                        "promotion requires a valid evidentiary root",
                    )
        elif target is EpistemicStatus.THEORY:
            self.rules.evaluate("CCC-EPISTEMIC-001", True, reason="explicit lower epistemic status recorded")
        elif target is EpistemicStatus.CONFLICTED:
            self.rules.evaluate("CCC-CONFLICT-001", True, reason="conflict status preserves unresolved material")

        updated = replace(artifact, epistemic_status=target, updated_at=utc_now())
        self.store.replace_artifact(updated)
        event = EpistemicEvent(
            event_id=new_id("epistemic"),
            artifact_id=artifact_id,
            actor=actor,
            from_status=current,
            to_status=target,
            reason=reason,
            timestamp=utc_now(),
            evidence_ids=tuple(evidence_ids),
        )
        self.store.append_epistemic(event)
        if current in {EpistemicStatus.HISTORICAL_RECORD, EpistemicStatus.EVIDENCE} and target not in {
            EpistemicStatus.HISTORICAL_RECORD,
            EpistemicStatus.EVIDENCE,
        }:
            self.evidence.invalidate_dependents(
                artifact_id,
                actor=Actor.system(),
                reason=f"evidence root reclassified as {target.value}: {reason}",
            )
        self.audit.record(
            actor=actor,
            operation="CLASSIFY_EPISTEMIC",
            object_id=artifact_id,
            previous_state={"epistemic_status": current.value},
            new_state={"epistemic_status": target.value},
            reason=reason,
            provenance=updated.provenance_status,
            evidence=evidence_ids,
            constitutional_rule="CCC-EPISTEMIC-001",
        )
        return updated

    def classify(self, artifact_id: str, status: EpistemicStatus, *, actor: Actor, reason: str, evidence_ids: tuple[str, ...] = ()):
        return self.transition(artifact_id, status, actor=actor, reason=reason, evidence_ids=evidence_ids)
