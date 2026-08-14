"""Explicit Chain A provenance state transitions."""

from __future__ import annotations

from dataclasses import replace

from .errors import ConstitutionViolation, InvalidTransition
from .models import (
    Actor,
    ActorType,
    ArtifactState,
    ProvenanceEvent,
    ProvenanceStatus,
    new_id,
    utc_now,
)


_ALLOWED_TRANSITIONS: dict[ProvenanceStatus, frozenset[ProvenanceStatus]] = {
    ProvenanceStatus.USER_ESTABLISHED: frozenset({ProvenanceStatus.USER_ACCEPTED, ProvenanceStatus.REJECTED, ProvenanceStatus.UNRESOLVED}),
    ProvenanceStatus.USER_ACCEPTED: frozenset({ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.REJECTED, ProvenanceStatus.UNRESOLVED}),
    ProvenanceStatus.ASSISTANT_PROPOSED: frozenset({ProvenanceStatus.USER_ACCEPTED, ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.REJECTED, ProvenanceStatus.UNRESOLVED, ProvenanceStatus.PROVENANCE_UNCERTAIN}),
    ProvenanceStatus.UNRESOLVED: frozenset({ProvenanceStatus.USER_ACCEPTED, ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.REJECTED, ProvenanceStatus.PROVENANCE_UNCERTAIN}),
    ProvenanceStatus.REJECTED: frozenset({ProvenanceStatus.USER_ACCEPTED, ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.UNRESOLVED}),
    ProvenanceStatus.PROVENANCE_UNCERTAIN: frozenset({ProvenanceStatus.USER_ACCEPTED, ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.REJECTED, ProvenanceStatus.UNRESOLVED}),
}


class ProvenanceManager:
    """Owns every provenance mutation; callers cannot set the field directly."""

    def __init__(self, store, audit, lineage, rules, evidence=None) -> None:
        self.store = store
        self.audit = audit
        self.lineage = lineage
        self.rules = rules
        self.evidence = evidence

    def register(
        self,
        artifact,
        *,
        actor: Actor,
        status: ProvenanceStatus,
        reason: str,
        authorization_basis: str | None = None,
    ):
        human_event = actor.kind is ActorType.HUMAN and status in {
            ProvenanceStatus.USER_ESTABLISHED,
            ProvenanceStatus.USER_ACCEPTED,
        }
        if status in {ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.USER_ACCEPTED}:
            self.rules.evaluate(
                "CCC-PROVENANCE-002",
                actor.kind is ActorType.HUMAN and bool(authorization_basis) and human_event,
                reason="human-originating origin/adoption event required",
            )
        if actor.kind is ActorType.MODEL and status is ProvenanceStatus.USER_ESTABLISHED:
            self.rules.evaluate("CCC-RATIFICATION-001", False, reason="model actor cannot establish human provenance")
        event = ProvenanceEvent(
            event_id=new_id("prov"),
            artifact_id=artifact.artifact_id,
            event_type="ORIGIN",
            actor=actor,
            from_status=None,
            to_status=status,
            reason=reason,
            timestamp=utc_now(),
            human_originating=human_event,
            authorization_basis=authorization_basis,
        )
        self.store.append_provenance(event)
        self.audit.record(
            actor=actor,
            operation="INGEST_PROVENANCE",
            object_id=artifact.artifact_id,
            previous_state=None,
            new_state={"provenance_status": status.value},
            reason=reason,
            provenance=status,
            constitutional_rule="CCC-PROVENANCE-001",
            authorization_basis=authorization_basis,
        )
        return artifact

    def transition(
        self,
        artifact_id: str,
        target: ProvenanceStatus,
        *,
        actor: Actor,
        reason: str,
        authorization_basis: str | None = None,
        human_event: bool = False,
        evidence_ids: tuple[str, ...] = (),
    ):
        artifact = self.store.require_artifact(artifact_id)
        current = artifact.provenance_status
        if artifact.state is ArtifactState.ERASED:
            raise ConstitutionViolation("CCC-HISTORY-002", "erased material cannot be promoted")
        if target is current:
            raise InvalidTransition(f"{current.value} -> {target.value} is not a transition")
        if target not in _ALLOWED_TRANSITIONS[current]:
            raise InvalidTransition(f"{current.value} -> {target.value} is not permitted")

        is_user_status = target in {ProvenanceStatus.USER_ACCEPTED, ProvenanceStatus.USER_ESTABLISHED}
        if is_user_status:
            if target is ProvenanceStatus.USER_ESTABLISHED and artifact.metadata.get("machine_consensus"):
                self.rules.evaluate(
                    "CCC-RATIFICATION-001",
                    False,
                    reason="machine consensus cannot become USER_ESTABLISHED",
                    evidence=evidence_ids,
                )
            self.rules.evaluate(
                "CCC-PROVENANCE-002",
                actor.kind is ActorType.HUMAN and human_event and bool(authorization_basis),
                reason="user provenance requires an explicit human-originating adoption event",
                evidence=evidence_ids,
            )
            self.rules.evaluate(
                "CCC-RATIFICATION-001",
                actor.kind is ActorType.HUMAN,
                reason="machine actors cannot self-ratify",
                evidence=evidence_ids,
            )
        elif target is ProvenanceStatus.REJECTED:
            self.rules.evaluate(
                "CCC-HUMAN-001",
                actor.kind is ActorType.HUMAN,
                reason="rejection is a human sovereign decision",
            )
        else:
            self.rules.evaluate("CCC-PROVENANCE-001", True, reason="explicit provenance transition requested")

        updated = replace(artifact, provenance_status=target, updated_at=utc_now())
        self.store.replace_artifact(updated)
        event_type = {
            ProvenanceStatus.USER_ACCEPTED: "HUMAN_ADOPTION",
            ProvenanceStatus.USER_ESTABLISHED: "HUMAN_ESTABLISHMENT",
            ProvenanceStatus.REJECTED: "HUMAN_REJECTION",
            ProvenanceStatus.UNRESOLVED: "RESOLUTION_PENDING",
            ProvenanceStatus.PROVENANCE_UNCERTAIN: "UNCERTAINTY_RECORDED",
        }.get(target, "MODIFICATION")
        event = ProvenanceEvent(
            event_id=new_id("prov"),
            artifact_id=artifact_id,
            event_type=event_type,
            actor=actor,
            from_status=current,
            to_status=target,
            reason=reason,
            timestamp=utc_now(),
            human_originating=human_event and actor.kind is ActorType.HUMAN,
            authorization_basis=authorization_basis,
            evidence_ids=tuple(evidence_ids),
        )
        self.store.append_provenance(event)
        if target is ProvenanceStatus.REJECTED and self.evidence is not None:
            self.evidence.invalidate_dependents(
                artifact_id,
                actor=Actor.system(),
                reason=f"evidence root rejected: {reason}",
            )
        if is_user_status and artifact.machine_origin:
            self.lineage.link(
                artifact_id,
                artifact_id,
                __import__("ccc.models", fromlist=["RelationshipType"]).RelationshipType.ADOPTS,
                actor=actor,
                reason="human adoption of machine-originated proposal recorded without changing origin",
                provenance=target,
                evidence=evidence_ids,
            )
        self.audit.record(
            actor=actor,
            operation=event_type,
            object_id=artifact_id,
            previous_state={"provenance_status": current.value},
            new_state={"provenance_status": target.value},
            reason=reason,
            provenance=target,
            evidence=evidence_ids,
            constitutional_rule="CCC-PROVENANCE-002" if is_user_status else "CCC-PROVENANCE-001",
            authorization_basis=authorization_basis,
        )
        return updated

    def establish_provenance(self, artifact_id: str, *, actor: Actor, reason: str, authorization_basis: str, evidence_ids: tuple[str, ...] = ()):
        return self.transition(
            artifact_id,
            ProvenanceStatus.USER_ESTABLISHED,
            actor=actor,
            reason=reason,
            authorization_basis=authorization_basis,
            human_event=True,
            evidence_ids=evidence_ids,
        )

    def accept(self, artifact_id: str, *, actor: Actor, reason: str, authorization_basis: str, evidence_ids: tuple[str, ...] = ()):
        return self.transition(
            artifact_id,
            ProvenanceStatus.USER_ACCEPTED,
            actor=actor,
            reason=reason,
            authorization_basis=authorization_basis,
            human_event=True,
            evidence_ids=evidence_ids,
        )

    def reject(self, artifact_id: str, *, actor: Actor, reason: str, authorization_basis: str):
        return self.transition(
            artifact_id,
            ProvenanceStatus.REJECTED,
            actor=actor,
            reason=reason,
            authorization_basis=authorization_basis,
            human_event=True,
        )

    def resolve(self, artifact_id: str, *, actor: Actor, status: ProvenanceStatus, reason: str, authorization_basis: str):
        return self.transition(
            artifact_id,
            status,
            actor=actor,
            reason=reason,
            authorization_basis=authorization_basis,
            human_event=True,
        )

    def history(self, artifact_id: str) -> tuple[ProvenanceEvent, ...]:
        return tuple(event for event in self.store.provenance_events if event.artifact_id == artifact_id)
