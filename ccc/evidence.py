"""Chain B: evidentiary sufficiency and root-integrity propagation."""

from __future__ import annotations

from dataclasses import replace

from .errors import ConstitutionViolation
from .models import (
    Actor,
    EpistemicEvent,
    EpistemicStatus,
    EvidenceLink,
    EvidenceValidation,
    ProvenanceStatus,
    RelationshipType,
    new_id,
    utc_now,
)


class EvidenceManager:
    """Keeps evidentiary support independent from Chain A provenance."""

    def __init__(self, store, audit, rules) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules

    def attach_evidence(
        self,
        claim_id: str,
        evidence_id: str,
        *,
        actor: Actor,
        rationale: str,
        support_strength: float | None = None,
    ) -> EvidenceLink:
        claim = self.store.require_artifact(claim_id)
        evidence = self.store.require_artifact(evidence_id)
        if claim_id == evidence_id:
            raise ConstitutionViolation("CCC-EVIDENCE-002", "a claim cannot support itself")
        if not claim.available or not evidence.available:
            raise ConstitutionViolation("CCC-EVIDENCE-001", "only available material can be attached as evidence")
        if support_strength is not None and not 0.0 <= support_strength <= 1.0:
            raise ValueError("support_strength must be between 0 and 1")
        link = EvidenceLink(
            link_id=new_id("evidence"),
            evidence_id=evidence_id,
            claim_id=claim_id,
            relation=RelationshipType.SUPPORTS,
            created_by=actor,
            rationale=rationale,
            support_strength=support_strength,
        )
        self.store.add_evidence_link(link)
        self.audit.record(
            actor=actor,
            operation="ATTACH_EVIDENCE",
            object_id=claim_id,
            previous_state={"evidence_links": len(self.store.links_for_claim(claim_id)) - 1},
            new_state={"evidence_links": len(self.store.links_for_claim(claim_id))},
            reason=rationale,
            provenance=claim.provenance_status,
            evidence=(evidence_id,),
            constitutional_rule="CCC-EVIDENCE-002",
        )
        return link

    def _is_legitimate_root(self, artifact_id: str) -> bool:
        artifact = self.store.get_artifact(artifact_id)
        if artifact is None or not artifact.available:
            return False
        if artifact.provenance_status in {ProvenanceStatus.REJECTED, ProvenanceStatus.PROVENANCE_UNCERTAIN, ProvenanceStatus.UNRESOLVED}:
            return False
        if artifact.epistemic_status not in {EpistemicStatus.HISTORICAL_RECORD, EpistemicStatus.EVIDENCE}:
            return False
        # A machine result cannot be a root merely because it was copied into
        # a human document or accepted without a human evidentiary source.
        if artifact.machine_origin:
            return False
        if artifact.machine_influenced and not artifact.metadata.get("human_independent_origin", False):
            return False
        return artifact.provenance_status in {ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.USER_ACCEPTED}

    def evidence_root(self, artifact_id: str) -> tuple[str, ...]:
        roots: set[str] = set()
        visited: set[str] = set()

        def visit(current_id: str) -> None:
            if current_id in visited:
                return
            visited.add(current_id)
            if self._is_legitimate_root(current_id):
                roots.add(current_id)
                return
            for link in self.store.links_for_claim(current_id, active_only=True):
                visit(link.evidence_id)

        visit(artifact_id)
        return tuple(sorted(roots))

    def trace_evidence_chain(self, artifact_id: str) -> tuple[tuple[str, ...], ...]:
        paths: list[tuple[str, ...]] = []
        visited: set[tuple[str, ...]] = set()

        def visit(current_id: str, path: tuple[str, ...]) -> None:
            if current_id in path:
                return
            next_path = path + (current_id,)
            if self._is_legitimate_root(current_id):
                if next_path not in visited:
                    visited.add(next_path)
                    paths.append(next_path)
                return
            for link in self.store.links_for_claim(current_id, active_only=True):
                visit(link.evidence_id, next_path)

        visit(artifact_id, ())
        return tuple(paths)

    def validate_evidence_chain(self, artifact_id: str) -> EvidenceValidation:
        self.store.require_artifact(artifact_id)
        paths = self.trace_evidence_chain(artifact_id)
        invalid: list[str] = []
        for link in self.store.links_for_claim(artifact_id, active_only=True):
            if not self.store.get_artifact(link.evidence_id) or not self.store.require_artifact(link.evidence_id).available:
                invalid.append(link.link_id)
        roots = self.evidence_root(artifact_id)
        valid = bool(roots)
        reason = "active legitimate evidentiary root exists" if valid else "no active legitimate evidentiary root remains"
        self.rules.assess(
            "CCC-EVIDENCE-001",
            valid,
            reason=reason,
            evidence=roots,
        )
        return EvidenceValidation(
            claim_id=artifact_id,
            valid=valid,
            roots=roots,
            paths=paths,
            invalid_links=tuple(invalid),
            reason=reason,
        )

    def downgrade_evidentiary_status(self, artifact_id: str, *, actor: Actor, reason: str) -> bool:
        artifact = self.store.require_artifact(artifact_id)
        if artifact.epistemic_status is EpistemicStatus.SIMULATION:
            return False
        if artifact.epistemic_status not in {
            EpistemicStatus.HISTORICAL_RECORD,
            EpistemicStatus.EVIDENCE,
            EpistemicStatus.INFERENCE,
            EpistemicStatus.INTERPRETATION,
        }:
            return False
        previous = artifact.epistemic_status
        updated = replace(artifact, epistemic_status=EpistemicStatus.THEORY, updated_at=utc_now())
        self.store.replace_artifact(updated)
        self.store.append_epistemic(
            EpistemicEvent(
                event_id=new_id("epistemic"),
                artifact_id=artifact_id,
                actor=actor,
                from_status=previous,
                to_status=EpistemicStatus.THEORY,
                reason=reason,
                evidence_ids=(),
            )
        )
        self.audit.record(
            actor=actor,
            operation="DOWNGRADE_EVIDENTIARY_STATUS",
            object_id=artifact_id,
            previous_state={"epistemic_status": previous.value},
            new_state={"epistemic_status": EpistemicStatus.THEORY.value},
            reason=reason,
            provenance=updated.provenance_status,
            constitutional_rule="CCC-EVIDENCE-001",
        )
        return True

    def invalidate_dependents(self, root_id: str, *, actor: Actor, reason: str) -> tuple[str, ...]:
        """Invalidate links transitively and downgrade only unsupported claims."""

        changed: list[str] = []
        queue = [root_id]
        seen: set[str] = set()
        while queue:
            evidence_id = queue.pop(0)
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            for link in self.store.links_for_evidence(evidence_id, active_only=True):
                self.store.replace_evidence_link(replace(link, active=False, invalidated_reason=reason))
                self.audit.record(
                    actor=actor,
                    operation="INVALIDATE_EVIDENCE_LINK",
                    object_id=link.link_id,
                    previous_state={"active": True, "evidence_id": evidence_id, "claim_id": link.claim_id},
                    new_state={"active": False, "evidence_id": evidence_id, "claim_id": link.claim_id},
                    reason=reason,
                    evidence=(evidence_id,),
                    constitutional_rule="CCC-EVIDENCE-001",
                )
                validation = self.validate_evidence_chain(link.claim_id)
                if not validation.valid:
                    if self.downgrade_evidentiary_status(link.claim_id, actor=actor, reason=reason):
                        changed.append(link.claim_id)
                    queue.append(link.claim_id)
        return tuple(dict.fromkeys(changed))
