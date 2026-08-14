"""Minimal executable demonstration of the constitutional boundary."""

from __future__ import annotations

import json

from .errors import ConstitutionViolation
from .models import Actor, EpistemicStatus
from .system import CCCSystem


def run_demo() -> dict:
    system = CCCSystem()
    human = Actor.human("demo-human", "human operator")
    model = Actor.model("demo-model", "machine analyst")

    fact = system.ingest(
        "The human record establishes the source observation.",
        actor=human,
        epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
        reason="human establishes a fact",
        authorization_basis="human-originating record",
    )
    inference = system.derive(
        "The machine proposes an inference from the source observation.",
        actor=model,
        evidence_ids=(fact.artifact_id,),
        method="machine inference",
    )

    self_promotion_blocked = False
    try:
        system.accept(
            inference.artifact_id,
            actor=model,
            reason="model consensus",
            authorization_basis="machine consensus",
        )
    except ConstitutionViolation:
        self_promotion_blocked = True

    before_accept = system.store.require_artifact(inference.artifact_id)
    accepted = system.accept(
        inference.artifact_id,
        actor=human,
        reason="human reviewed and accepts the proposed inference",
        authorization_basis="explicit human adoption event",
        evidence_ids=(fact.artifact_id,),
    )
    evidence_linked = bool(system.store.links_for_claim(inference.artifact_id, active_only=True))
    system.erase(
        fact.artifact_id,
        actor=human,
        reason="human requested erasure of the source root",
        authorization_basis="explicit human erasure request",
    )
    after_erase = system.store.require_artifact(inference.artifact_id)
    audit = system.audit()
    return {
        "fact_id": fact.artifact_id,
        "inference_id": inference.artifact_id,
        "inference_before_accept": before_accept.provenance_status.value,
        "inference_after_accept": accepted.provenance_status.value,
        "inference_origin_remains": accepted.origin.kind.value,
        "self_promotion_blocked": self_promotion_blocked,
        "evidence_attached": evidence_linked,
        "root_erased": system.store.require_artifact(fact.artifact_id).state.value == "ERASED",
        "dependent_status_after_erasure": after_erase.epistemic_status.value,
        "audit_events": len(audit),
        "audit_operations": [event.operation for event in audit],
        "constitution_valid": system.validate_constitution()["valid"],
    }


def main() -> int:
    print(json.dumps(run_demo(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
