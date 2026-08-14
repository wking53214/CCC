"""Machine-readable constitutional rules and deterministic rule evaluation."""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, Mapping

from .errors import ConstitutionViolation
from .models import ConstitutionalRule, RuleDecision, utc_now


def _rule(
    rule_id: str,
    requirement_id: str,
    requirement_text: str,
    condition: str,
    decision: str,
    reason: str,
    severity: str = "ERROR",
) -> ConstitutionalRule:
    return ConstitutionalRule(
        rule_id=rule_id,
        article=None,
        requirement_id=requirement_id,
        requirement_text=requirement_text,
        condition=condition,
        decision=decision,
        reason=reason,
        severity=severity,
        source="BUILD_DIRECTIVE",
    )


# No ratified CCC document is present in the repository.  These IDs therefore
# point to the explicit build directive, not to invented article numbers.
RULES: tuple[ConstitutionalRule, ...] = (
    _rule("CCC-PROVENANCE-001", "REQ.PROVENANCE.EXPLICIT_TRANSITIONS", "Provenance changes are explicit state transitions.", "transition requested through the provenance service", "ALLOW", "Direct mutation is not an accepted transition path."),
    _rule("CCC-PROVENANCE-002", "REQ.PROVENANCE.HUMAN_ADOPTION", "Machine proposals require an explicit human-originating adoption event before user status.", "target is USER_ACCEPTED or USER_ESTABLISHED", "ALLOW only with human adoption", "Machine processing, repetition, or consensus cannot substitute for human adoption."),
    _rule("CCC-PROVENANCE-003", "REQ.PROVENANCE.NO_AUTHORSHP_INFERENCE", "Later human authorship does not infer human origin of embedded machine material.", "origin is retained independently of container authorship", "ALLOW", "Origin and container authorship are separate fields."),
    _rule("CCC-EPISTEMIC-001", "REQ.EPISTEMIC.NON_INTERCHANGEABLE", "Epistemic categories are distinct and promotion is validated.", "target epistemic status has a permitted transition", "ALLOW only when validated", "A label alone cannot promote a conclusion."),
    _rule("CCC-EPISTEMIC-002", "REQ.EPISTEMIC.SIMULATION_NOT_HISTORY", "Simulation cannot become historical record.", "target is HISTORICAL_RECORD and source is SIMULATION", "REJECT", "Modeled information remains modeled information."),
    _rule("CCC-EPISTEMIC-003", "REQ.EPISTEMIC.EVIDENCE_BASIS", "Inference or theory promoted to evidence/fact requires legitimate evidence.", "promotion includes a valid evidentiary root", "ALLOW only with valid roots", "Machine agreement is not an evidentiary root."),
    _rule("CCC-EVIDENCE-001", "REQ.EVIDENCE.ROOT_INTEGRITY", "Every evidence-backed conclusion remains traceable to active legitimate roots.", "evidence chain has at least one valid root", "ALLOW only with valid roots", "Erased, rejected, or unavailable roots have no evidentiary authority."),
    _rule("CCC-EVIDENCE-002", "REQ.EVIDENCE.CHAIN_SEPARATION", "Origin provenance and evidentiary sufficiency are separate chains.", "origin, evidence, claim, and support links remain separate", "ALLOW", "A genuine human statement may still be insufficient for a conclusion."),
    _rule("CCC-HUMAN-001", "REQ.HUMAN_SOVEREIGNTY.NO_MACHINE_VETO", "Human decisions cannot be vetoed by machine recommendations.", "machine output is advisory and does not block human operation", "ALLOW", "Consequences may be disclosed but are not authorization gates."),
    _rule("CCC-HISTORY-001", "REQ.HISTORY.LINEAGE", "Correction and supersession preserve prior state and lineage.", "mutation is represented by a new event/version", "ALLOW", "Historical state is not silently rewritten."),
    _rule("CCC-HISTORY-002", "REQ.HISTORY.ERASURE_DISTINCT", "Erasure remains distinguishable from correction and supersession.", "operation is recorded as ERASE and leaves a tombstone", "ALLOW", "Erasure is a separate state and operation."),
    _rule("CCC-RATIFICATION-001", "REQ.RATIFICATION.NO_MACHINE_SELF_RATIFICATION", "Machine output cannot self-promote through machine consensus.", "promotion event is human-originating", "REJECT without human event", "Repeated model agreement is not human authority."),
    _rule("CCC-UNCERTAINTY-001", "REQ.UNCERTAINTY.PRESERVE", "Unknown, inferred, conflicted, candidate, and resolution-required states remain explicit.", "uncertain material is represented without forced certainty", "ALLOW", "The system must not manufacture certainty."),
    _rule("CCC-ROADSIGN-001", "REQ.ROAD_SIGNS.INDICATORS_NOT_CONCLUSIONS", "Road Signs are observable indicators rather than conclusions.", "recorded sign has no conclusion authority", "ALLOW", "A sign means examination is warranted."),
    _rule("CCC-INFLECTION-001", "REQ.INFLECTION.SEPARATE_DIMENSIONS", "Detection, divergence, sensitivity, and significance remain separate.", "each assessment dimension is stored independently", "ALLOW", "Machine weighting is advisory."),
    _rule("CCC-THREAD-001", "REQ.THREADS.BRANCH_LINEAGE", "Threads and branches preserve explicit lineage.", "branch relation references its parent thread", "ALLOW", "Chronology alone does not define a cognitive thread."),
    _rule("CCC-123-001", "REQ.ANALYSIS.ONE_TWO_THREE", "The human-attributed 1 to 2 to 3 method is anomaly to pattern to mandate.", "mandate follows a validated pattern and human action", "ALLOW only after validation", "An anomaly is not automatically a mandate."),
    _rule("CCC-DISCOVERY-001", "REQ.DISCOVERY.MACHINE_ATTRIBUTION", "Machine discovery remains machine-generated until explicit human adoption.", "machine origin and processing history are retained", "ALLOW", "Discovery may advise without becoming human-originated."),
    _rule("CCC-SIMULATION-001", "REQ.SIMULATION.ASSUMPTIONS", "Simulation inputs, provenance, assumptions, shared assumptions, and limitations are preserved.", "simulation record includes all required fields", "ALLOW", "Shared assumptions prevent false claims of independent confirmation."),
    _rule("CCC-CONFLICT-001", "REQ.CONFLICT.PRESERVE", "Material conflict is presented and not silently adjudicated.", "conflict remains open until human resolution", "ALLOW", "Evidence-versus-evidence conflict is distinct from theory-versus-evidence."),
    _rule("CCC-CANON-001", "REQ.CANONICALIZATION.HUMAN_STATUS", "Canonical terminology requires established provenance and explicit human action.", "canonicalization is a human transition with source material", "ALLOW only with human action", "Unknown-origin terms are not silently canonical."),
    _rule("CCC-QUERY-001", "REQ.QUERYABILITY.NO_PRESENTATION_DELETION", "Presentation priority does not delete or make unsurfaced candidates nonexistent.", "query and presentation are separate operations", "ALLOW", "All stored records remain queryable."),
    _rule("CCC-AUDIT-001", "REQ.AUDIT.CONSEQUENTIAL_TRANSITIONS", "Consequential transitions create complete audit events.", "audit contains actor, operation, object, state, reason, and rule", "ALLOW only when auditable", "Machine actions are not labeled as human actions."),
    _rule("CCC-ID-001", "REQ.DATA_INTEGRITY.IMMUTABLE_IDENTIFIERS", "Historical objects retain immutable identifiers through lifecycle changes.", "new versions link to prior identifiers", "ALLOW", "Identity is not maintained by text matching alone."),
)

RULE_INDEX: Mapping[str, ConstitutionalRule] = {rule.rule_id: rule for rule in RULES}


class ConstitutionalRuleEngine:
    """Central rule evaluator used by all state-changing services."""

    version = "0.1.0"

    def __init__(self, store) -> None:
        self.store = store

    def get(self, rule_id: str) -> ConstitutionalRule:
        try:
            return RULE_INDEX[rule_id]
        except KeyError as exc:
            raise KeyError(f"unknown constitutional rule {rule_id}") from exc

    def evaluate(
        self,
        rule_id: str,
        allowed: bool,
        *,
        reason: str | None = None,
        evidence: Iterable[str] = (),
        override_status: str = "NO_OVERRIDE",
    ) -> RuleDecision:
        result = self.assess(
            rule_id,
            allowed,
            reason=reason,
            evidence=evidence,
            override_status=override_status,
        )
        if not allowed:
            raise ConstitutionViolation(
                rule_id=result.rule_id,
                reason=result.reason,
                decision=result.decision,
                evidence=result.evidence,
            )
        return result

    def assess(
        self,
        rule_id: str,
        allowed: bool,
        *,
        reason: str | None = None,
        evidence: Iterable[str] = (),
        override_status: str = "NO_OVERRIDE",
    ) -> RuleDecision:
        """Record a rule decision without raising.

        Validation/reporting code uses this method when a rejection is a
        result to be returned rather than an operation to abort.
        """

        rule = self.get(rule_id)
        decision = "ALLOW" if allowed else "REJECT"
        result = RuleDecision(
            rule_id=rule.rule_id,
            article=rule.article,
            requirement_id=rule.requirement_id,
            condition=rule.condition,
            decision=decision,
            reason=reason or rule.reason,
            severity=rule.severity,
            evidence=tuple(evidence),
            override_status=override_status,
            evaluated_at=utc_now(),
        )
        self.store.rule_decisions.append(asdict(result))
        return result

    def why(self, rule_id: str) -> ConstitutionalRule:
        return self.get(rule_id)

    def trace(self, rule_id: str) -> dict[str, str | None]:
        """Return machine-readable implementation-to-requirement trace."""

        rule = self.get(rule_id)
        return {
            "implementation": rule.rule_id,
            "constitutional_rule": rule.rule_id,
            "article": rule.article,
            "requirement_id": rule.requirement_id,
            "requirement": rule.requirement_text,
            "source": rule.source,
            "version": rule.version,
        }

    def registry(self) -> tuple[ConstitutionalRule, ...]:
        return RULES
