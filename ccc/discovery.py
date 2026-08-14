"""Machine discovery records and the explicit 1 -> 2 -> 3 progression."""

from __future__ import annotations

from dataclasses import replace

from .errors import ConstitutionViolation, InvalidTransition
from .models import (
    Actor,
    ActorType,
    AnalysisStage,
    DiscoveryRecord,
    EpistemicStatus,
    ProvenanceStatus,
    new_id,
)


class DiscoveryManager:
    HUMAN_123_ATTRIBUTION = "HUMAN_ESTABLISHED: 1 = anomaly, 2 = pattern, 3 = mandate"

    def __init__(self, store, audit, rules, evidence) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules
        self.evidence = evidence

    def discover(
        self,
        *,
        source_material: tuple[str, ...],
        method: str,
        conclusion: str,
        confidence: float | None,
        supporting_evidence: tuple[str, ...] = (),
        actor: Actor,
        epistemic_status: EpistemicStatus = EpistemicStatus.INFERENCE,
        stage: AnalysisStage | None = None,
        relationships: tuple[str, ...] = (),
    ) -> DiscoveryRecord:
        if epistemic_status in {EpistemicStatus.HISTORICAL_RECORD, EpistemicStatus.EVIDENCE} and actor.kind in {ActorType.MODEL, ActorType.SYSTEM}:
            self.rules.evaluate(
                "CCC-DISCOVERY-001",
                False,
                reason="machine discovery cannot be created as human evidence",
            )
        machine_origin = actor.kind in {ActorType.MODEL, ActorType.SYSTEM}
        record = DiscoveryRecord(
            discovery_id=new_id("discovery"),
            source_material=tuple(source_material),
            machine_origin=machine_origin,
            machine_processing_history=(method,) if machine_origin else (),
            method=method,
            conclusion=conclusion,
            confidence=confidence,
            supporting_evidence=tuple(supporting_evidence),
            epistemic_status=epistemic_status,
            provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED if machine_origin else ProvenanceStatus.USER_ESTABLISHED,
            relationships=tuple(relationships),
            stage=stage,
            attribution=self.HUMAN_123_ATTRIBUTION if stage is not None else None,
            created_by=actor,
        )
        self.store.add_discovery(record)
        self.audit.record(
            actor=actor,
            operation="DISCOVER",
            object_id=record.discovery_id,
            previous_state=None,
            new_state={"machine_origin": machine_origin, "epistemic_status": epistemic_status.value, "stage": stage.value if stage else None},
            reason=method,
            provenance=record.provenance_status,
            evidence=supporting_evidence,
            constitutional_rule="CCC-DISCOVERY-001",
        )
        return record

    def advance(
        self,
        discovery_id: str,
        *,
        stage: AnalysisStage,
        actor: Actor,
        reason: str,
        evidence_ids: tuple[str, ...] = (),
        human_event: bool = False,
        authorization_basis: str | None = None,
    ) -> DiscoveryRecord:
        record = self.store.discoveries[discovery_id]
        expected = {
            AnalysisStage.ANOMALY: AnalysisStage.PATTERN,
            AnalysisStage.PATTERN: AnalysisStage.MANDATE,
        }
        if record.stage not in expected or expected[record.stage] is not stage:
            raise InvalidTransition(f"{record.stage} -> {stage} is not a valid 1 -> 2 -> 3 progression")
        if stage is AnalysisStage.MANDATE:
            self.rules.evaluate(
                "CCC-123-001",
                actor.kind is ActorType.HUMAN and human_event and bool(authorization_basis),
                reason="mandate requires human establishment after a pattern",
                evidence=evidence_ids,
            )
            if not evidence_ids:
                raise ConstitutionViolation("CCC-123-001", "mandate requires supporting evidence")
            roots = set()
            for evidence_id in evidence_ids:
                roots.update(self.evidence.evidence_root(evidence_id))
            if not roots:
                raise ConstitutionViolation("CCC-123-001", "mandate requires a legitimate evidentiary root")
            provenance = ProvenanceStatus.USER_ESTABLISHED
        else:
            provenance = record.provenance_status
        updated = replace(
            record,
            stage=stage,
            relationships=tuple(dict.fromkeys((*record.relationships, discovery_id))),
            provenance_status=provenance,
            human_resolution=reason if stage is AnalysisStage.MANDATE else record.human_resolution,
        )
        self.store.replace_discovery(updated)
        self.audit.record(
            actor=actor,
            operation=f"ADVANCE_{stage.value}",
            object_id=discovery_id,
            previous_state={"stage": record.stage.value if record.stage else None, "provenance_status": record.provenance_status.value},
            new_state={"stage": stage.value, "provenance_status": updated.provenance_status.value},
            reason=reason,
            provenance=updated.provenance_status,
            evidence=evidence_ids,
            constitutional_rule="CCC-123-001",
            authorization_basis=authorization_basis,
        )
        return updated
    def adopt(
        self,
        discovery_id: str,
        *,
        actor: Actor,
        reason: str,
        authorization_basis: str,
    ) -> DiscoveryRecord:
        self.rules.evaluate(
            "CCC-RATIFICATION-001",
            actor.kind is ActorType.HUMAN and bool(authorization_basis),
            reason="discovery adoption requires a human event",
        )
        record = self.store.discoveries[discovery_id]
        updated = replace(record, provenance_status=ProvenanceStatus.USER_ACCEPTED, human_resolution=reason)
        self.store.replace_discovery(updated)
        self.audit.record(
            actor=actor,
            operation="ADOPT_DISCOVERY",
            object_id=discovery_id,
            previous_state={"provenance_status": record.provenance_status.value},
            new_state={"provenance_status": updated.provenance_status.value},
            reason=reason,
            provenance=updated.provenance_status,
            constitutional_rule="CCC-RATIFICATION-001",
            authorization_basis=authorization_basis,
        )
        return updated
