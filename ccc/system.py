"""Public orchestration facade for the Cognitive Continuity Constitution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from .audit import AuditTrail
from .branches import BranchManager
from .canonicalization import CanonicalizationManager
from .conflict import ConflictManager
from .constitutional_rules import ConstitutionalRuleEngine
from .dialogue import DialogueEngine
from .discovery import DiscoveryManager
from . import matching
from .epistemic_state import EpistemicManager
from .evidence import EvidenceManager
from .human_resolution import HumanResolutionManager
from .inflection import InflectionManager
from .lineage import LineageManager
from .models import (
    Actor,
    ActorType,
    AnalysisStage,
    Artifact,
    ArtifactState,
    EpistemicStatus,
    ProvenanceStatus,
    RelationshipType,
    new_id,
    utc_now,
)
from .provenance import ProvenanceManager
from .query import QueryEngine
from .road_signs import RoadSignManager
from .simulation import SimulationManager
from .store import CCCStore
from .threads import ThreadManager


# Named, specific, from this project's own history -- not a placeholder or
# a general secrets pattern. Resume_OS stays private permanently, chosen as
# the validation domain precisely because it holds real ground truth that
# must not leak into a public repo's audit trail. ChatGPT_History carries
# un-scrubbed third-party PII, flagged as a real dependency of this whole
# system if it's ever ingested at scale, never resolved. A finding whose
# source cites either one, into a public repository, is refused by default.
PRIVATE_SOURCE_MARKERS = ("Resume_OS", "ChatGPT_History")


def _state(artifact: Artifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "state": artifact.state.value,
        "provenance_status": artifact.provenance_status.value,
        "epistemic_status": artifact.epistemic_status.value,
        "origin_actor": artifact.origin.actor_id,
        "origin_actor_type": artifact.origin.kind.value,
        "content_available": artifact.content is not None,
    }


class CCCSystem:
    """A dependency-free, auditable CCC enforcement layer."""

    version = "0.1.0"

    def __init__(self, *, store: CCCStore | None = None, persistence_path: str | Path | None = None) -> None:
        self.store = store or CCCStore(persistence_path)
        self.audit_trail = AuditTrail(self.store)
        self.rules = ConstitutionalRuleEngine(self.store)
        self.lineage = LineageManager(self.store, self.audit_trail, self.rules)
        self.evidence = EvidenceManager(self.store, self.audit_trail, self.rules)
        self.provenance = ProvenanceManager(self.store, self.audit_trail, self.lineage, self.rules, self.evidence)
        self.epistemic = EpistemicManager(self.store, self.audit_trail, self.rules, self.evidence)
        self.human_resolution = HumanResolutionManager(self.store, self.audit_trail, self.rules)
        self.road_signs = RoadSignManager(self.store, self.audit_trail, self.rules)
        self.inflection = InflectionManager(self.store, self.audit_trail, self.rules)
        self.threads = ThreadManager(self.store, self.audit_trail, self.rules)
        self.branches = BranchManager(self.store, self.audit_trail, self.rules, self.lineage, self.threads)
        self.discovery = DiscoveryManager(self.store, self.audit_trail, self.rules, self.evidence)
        self.dialogue = DialogueEngine(self.human_resolution)
        self._finding_shingle_index = matching.ShingleIndex()
        self.simulation = SimulationManager(self.store, self.audit_trail, self.rules)
        self.conflict = ConflictManager(self.store, self.audit_trail, self.rules, self.human_resolution)
        self.canonicalization = CanonicalizationManager(self.store, self.audit_trail, self.rules)
        self.query_engine = QueryEngine(self.store)

    @property
    def system_actor(self) -> Actor:
        return Actor.system()

    def ingest(
        self,
        content: str,
        *,
        actor: Actor | None = None,
        provenance_status: ProvenanceStatus | None = None,
        epistemic_status: EpistemicStatus = EpistemicStatus.UNKNOWN,
        source_material: tuple[str, ...] = (),
        topics: tuple[str, ...] = (),
        instrument: str | None = None,
        confidence: float | None = None,
        presentation_priority: int = 0,
        thread_id: str | None = None,
        branch_id: str | None = None,
        machine_processing: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
        human_independent_origin: bool = False,
        reason: str = "material ingested",
        authorization_basis: str | None = None,
    ) -> Artifact:
        actor = actor or Actor.system()
        metadata = dict(metadata or {})
        for source_id in source_material:
            self.store.require_artifact(source_id)
        machine_source_ids = tuple(
            source_id
            for source_id in source_material
            if self.store.require_artifact(source_id).machine_origin
        )
        if provenance_status is None:
            provenance_status = (
                ProvenanceStatus.PROVENANCE_UNCERTAIN
                if actor.kind is ActorType.HUMAN and machine_source_ids
                else ProvenanceStatus.USER_ESTABLISHED
                if actor.kind is ActorType.HUMAN
                else ProvenanceStatus.ASSISTANT_PROPOSED
                if actor.kind is ActorType.MODEL
                else ProvenanceStatus.PROVENANCE_UNCERTAIN
            )
        if machine_source_ids:
            metadata["machine_source_ids"] = machine_source_ids
            metadata["human_independent_origin"] = human_independent_origin
            self.rules.evaluate(
                "CCC-PROVENANCE-003",
                True,
                reason="machine source lineage is retained separately from container authorship",
                evidence=machine_source_ids,
            )
        self.epistemic.validate_initial(actor=actor, status=epistemic_status)
        if provenance_status in {ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.USER_ACCEPTED}:
            self.rules.evaluate(
                "CCC-PROVENANCE-002",
                actor.kind is ActorType.HUMAN and bool(authorization_basis or actor.kind is ActorType.HUMAN),
                reason="human-originating ingestion requires an explicit human basis",
            )
        if actor.kind in {ActorType.MODEL, ActorType.SYSTEM}:
            metadata["machine_generated"] = True
            machine_processing = tuple(machine_processing) or (reason,)
        artifact = Artifact(
            artifact_id=new_id("artifact"),
            content=content,
            origin=actor,
            provenance_status=provenance_status,
            epistemic_status=epistemic_status,
            topics=tuple(topics),
            source_material=tuple(source_material),
            instrument=instrument,
            confidence=confidence,
            presentation_priority=presentation_priority,
            thread_id=thread_id,
            branch_id=branch_id,
            machine_processing_history=tuple(machine_processing),
            metadata=metadata or {},
        )
        self.provenance.register(
            artifact,
            actor=actor,
            status=provenance_status,
            reason=reason,
            authorization_basis=authorization_basis or ("human-originating ingestion" if actor.kind is ActorType.HUMAN else None),
        )
        self.store.add_artifact(artifact)
        self.audit_trail.record(
            actor=actor,
            operation="INGEST",
            object_id=artifact.artifact_id,
            previous_state=None,
            new_state=_state(artifact),
            reason=reason,
            provenance=artifact.provenance_status,
            constitutional_rule="CCC-PROVENANCE-001",
            authorization_basis=authorization_basis,
        )
        return artifact

    def record(self, content: str, **kwargs) -> Artifact:
        return self.ingest(content, **kwargs)

    def derive(
        self,
        conclusion: str,
        *,
        evidence_ids: tuple[str, ...] = (),
        actor: Actor | None = None,
        method: str = "machine inference",
        confidence: float | None = None,
        source_material: tuple[str, ...] = (),
        machine_consensus: bool = False,
        topics: tuple[str, ...] = (),
    ) -> Artifact:
        actor = actor or Actor.model()
        artifact = self.ingest(
            conclusion,
            actor=actor,
            provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
            epistemic_status=EpistemicStatus.INFERENCE,
            source_material=tuple(dict.fromkeys((*source_material, *evidence_ids))),
            confidence=confidence,
            topics=topics,
            machine_processing=(method,),
            metadata={"machine_consensus": machine_consensus, "method": method},
            reason=method,
        )
        for evidence_id in evidence_ids:
            self.evidence.attach_evidence(
                artifact.artifact_id,
                evidence_id,
                actor=actor,
                rationale=f"{method} uses this material",
            )
        return self.store.require_artifact(artifact.artifact_id)

    def infer(self, conclusion: str, **kwargs) -> Artifact:
        return self.derive(conclusion, **kwargs)

    def interpret(self, interpretation: str, **kwargs) -> Artifact:
        kwargs.setdefault("method", "machine interpretation")
        artifact = self.derive(interpretation, **kwargs)
        return self.epistemic.transition(
            artifact.artifact_id,
            EpistemicStatus.INTERPRETATION,
            actor=kwargs.get("actor") or Actor.model(),
            reason="interpretive status explicitly recorded",
            evidence_ids=tuple(kwargs.get("evidence_ids", ())),
        )

    def attach_evidence(self, claim_id: str, evidence_id: str, *, actor: Actor | None = None, rationale: str, support_strength: float | None = None):
        return self.evidence.attach_evidence(
            claim_id,
            evidence_id,
            actor=actor or Actor.system(),
            rationale=rationale,
            support_strength=support_strength,
        )

    def evidence_root(self, artifact_id: str) -> tuple[str, ...]:
        return self.evidence.evidence_root(artifact_id)

    def trace_evidence_chain(self, artifact_id: str):
        return self.evidence.trace_evidence_chain(artifact_id)

    def validate_evidence_chain(self, artifact_id: str):
        return self.evidence.validate_evidence_chain(artifact_id)

    def establish_provenance(self, artifact_id: str, *, actor: Actor, reason: str, authorization_basis: str, evidence_ids: tuple[str, ...] = ()):
        return self.provenance.establish_provenance(artifact_id, actor=actor, reason=reason, authorization_basis=authorization_basis, evidence_ids=evidence_ids)

    def accept(self, artifact_id: str, *, actor: Actor, reason: str, authorization_basis: str, evidence_ids: tuple[str, ...] = ()):
        return self.provenance.accept(artifact_id, actor=actor, reason=reason, authorization_basis=authorization_basis, evidence_ids=evidence_ids)

    def reject(self, artifact_id: str, *, actor: Actor, reason: str, authorization_basis: str):
        return self.provenance.reject(artifact_id, actor=actor, reason=reason, authorization_basis=authorization_basis)

    def classify(self, artifact_id: str, status: EpistemicStatus, *, actor: Actor, reason: str, evidence_ids: tuple[str, ...] = ()):
        return self.epistemic.classify(artifact_id, status, actor=actor, reason=reason, evidence_ids=evidence_ids)

    def ratify(
        self,
        artifact_id: str,
        *,
        actor: Actor,
        reason: str,
        authorization_basis: str,
        status: ProvenanceStatus = ProvenanceStatus.USER_ACCEPTED,
        evidence_ids: tuple[str, ...] = (),
    ):
        if status is ProvenanceStatus.USER_ESTABLISHED:
            return self.establish_provenance(artifact_id, actor=actor, reason=reason, authorization_basis=authorization_basis, evidence_ids=evidence_ids)
        return self.accept(artifact_id, actor=actor, reason=reason, authorization_basis=authorization_basis, evidence_ids=evidence_ids)

    def decide(
        self,
        choice: str,
        *,
        actor: Actor,
        reason: str,
        authorization_basis: str,
        recommendation_id: str | None = None,
    ) -> Artifact:
        """Record a human decision; a model recommendation is never a decision."""

        self.rules.evaluate(
            "CCC-HUMAN-001",
            actor.kind is ActorType.HUMAN and bool(authorization_basis),
            reason="decision authority belongs to the human actor",
            evidence=(recommendation_id,) if recommendation_id else (),
        )
        if recommendation_id is not None:
            self.store.require_artifact(recommendation_id)
        decision = self.ingest(
            choice,
            actor=actor,
            provenance_status=ProvenanceStatus.USER_ESTABLISHED,
            epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
            source_material=(recommendation_id,) if recommendation_id else (),
            metadata={"decision": True, "recommendation_id": recommendation_id},
            reason=reason,
            authorization_basis=authorization_basis,
        )
        self.audit_trail.record(
            actor=actor,
            operation="DECIDE",
            object_id=decision.artifact_id,
            previous_state=None,
            new_state={"decision": True, "recommendation_id": recommendation_id},
            reason=reason,
            provenance=decision.provenance_status,
            evidence=(recommendation_id,) if recommendation_id else (),
            constitutional_rule="CCC-HUMAN-001",
            authorization_basis=authorization_basis,
        )
        return decision

    def correct(self, artifact_id: str, *, content: str, actor: Actor, reason: str, authorization_basis: str) -> Artifact:
        return self._version(artifact_id, content=content, actor=actor, reason=reason, authorization_basis=authorization_basis, relationship=RelationshipType.CORRECTS, operation="CORRECT")

    def amend(self, artifact_id: str, *, content: str, actor: Actor, reason: str, authorization_basis: str) -> Artifact:
        return self._version(artifact_id, content=content, actor=actor, reason=reason, authorization_basis=authorization_basis, relationship=RelationshipType.AMENDS, operation="AMEND")

    def supersede(self, artifact_id: str, *, content: str, actor: Actor, reason: str, authorization_basis: str) -> Artifact:
        return self._version(artifact_id, content=content, actor=actor, reason=reason, authorization_basis=authorization_basis, relationship=RelationshipType.SUPERSEDES, operation="SUPERSEDE")

    def _version(self, artifact_id: str, *, content: str, actor: Actor, reason: str, authorization_basis: str, relationship: RelationshipType, operation: str) -> Artifact:
        old = self.store.require_artifact(artifact_id)
        self.rules.evaluate(
            "CCC-HUMAN-001",
            actor.kind is ActorType.HUMAN and bool(authorization_basis),
            reason="historical lifecycle changes require an explicit human operation",
        )
        new_artifact = self.ingest(
            content,
            actor=actor,
            provenance_status=ProvenanceStatus.USER_ESTABLISHED,
            epistemic_status=old.epistemic_status,
            source_material=(artifact_id,),
            topics=old.topics,
            instrument=old.instrument,
            confidence=old.confidence,
            presentation_priority=old.presentation_priority,
            thread_id=old.thread_id,
            branch_id=old.branch_id,
            metadata={"version_of": artifact_id, "operation": operation},
            reason=reason,
            authorization_basis=authorization_basis,
        )
        self.lineage.link(
            new_artifact.artifact_id,
            artifact_id,
            relationship,
            actor=actor,
            reason=reason,
            previous_state=_state(old)["epistemic_status"],
            new_state=_state(new_artifact)["epistemic_status"],
            provenance=new_artifact.provenance_status,
        )
        self.audit_trail.record(
            actor=actor,
            operation=operation,
            object_id=artifact_id,
            previous_state=_state(old),
            new_state={"replacement_id": new_artifact.artifact_id, "relationship": relationship.value},
            reason=reason,
            provenance=new_artifact.provenance_status,
            constitutional_rule="CCC-HISTORY-001",
            authorization_basis=authorization_basis,
        )
        return new_artifact

    def redact(self, artifact_id: str, *, actor: Actor, reason: str, authorization_basis: str) -> Artifact:
        return self._make_unavailable(artifact_id, actor=actor, reason=reason, authorization_basis=authorization_basis, state=ArtifactState.REDACTED, relationship=RelationshipType.REDACTS, operation="REDACT")

    def erase(self, artifact_id: str, *, actor: Actor, reason: str, authorization_basis: str) -> Artifact:
        return self._make_unavailable(artifact_id, actor=actor, reason=reason, authorization_basis=authorization_basis, state=ArtifactState.ERASED, relationship=RelationshipType.ERASES, operation="ERASE")

    def _make_unavailable(self, artifact_id: str, *, actor: Actor, reason: str, authorization_basis: str, state: ArtifactState, relationship: RelationshipType, operation: str) -> Artifact:
        old = self.store.require_artifact(artifact_id)
        self.rules.evaluate(
            "CCC-HUMAN-001",
            actor.kind is ActorType.HUMAN and bool(authorization_basis),
            reason=f"{operation.lower()} is a human sovereign operation",
        )
        updated = replace(
            old,
            content=None,
            state=state,
            updated_at=utc_now(),
            metadata={**old.metadata, f"{operation.lower()}_reason": reason},
        )
        self.store.replace_artifact(updated)
        self.lineage.link(
            artifact_id,
            artifact_id,
            relationship,
            actor=actor,
            reason=reason,
            previous_state=old.state.value,
            new_state=state.value,
            provenance=old.provenance_status,
        )
        invalidated = self.evidence.invalidate_dependents(artifact_id, actor=self.system_actor, reason=f"{operation.lower()} root unavailable: {reason}")
        self.audit_trail.record(
            actor=actor,
            operation=operation,
            object_id=artifact_id,
            previous_state=_state(old),
            new_state={**_state(updated), "invalidated_dependents": list(invalidated)},
            reason=reason,
            provenance=updated.provenance_status,
            constitutional_rule="CCC-HISTORY-002",
            authorization_basis=authorization_basis,
        )
        return updated

    def detect_road_sign(self, **kwargs):
        return self.road_signs.detect_road_sign(**kwargs)

    def record_road_sign(self, **kwargs):
        return self.road_signs.record_road_sign(**kwargs)

    def link_road_sign(self, *args, **kwargs):
        return self.road_signs.link_road_sign(*args, **kwargs)

    def query_road_signs(self, **kwargs):
        return self.road_signs.query_road_signs(**kwargs)

    def detect_inflection(self, **kwargs):
        return self.inflection.detect_inflection(**kwargs)

    def resolve_inflection(self, *args, **kwargs):
        return self.inflection.resolve_inflection(*args, **kwargs)

    def create_thread(self, **kwargs):
        return self.threads.create_thread(**kwargs)

    def create_branch(self, *args, **kwargs):
        return self.branches.create_branch(*args, **kwargs)

    def attach_branch(self, *args, **kwargs):
        return self.branches.attach_branch(*args, **kwargs)

    def resume_thread(self, thread_id: str, *, actor: Actor, reason: str):
        if thread_id in self.store.threads:
            return self.threads.resume_thread(thread_id, actor=actor, reason=reason)
        return self.branches.resume_thread(thread_id, actor=actor, reason=reason)

    def return_to_branch(self, branch_id: str, *, actor: Actor, reason: str):
        return self.branches.return_to_branch(branch_id, actor=actor, reason=reason)

    def resolve_branch(self, branch_id: str, *, actor: Actor, reason: str):
        return self.branches.resolve_branch(branch_id, actor=actor, reason=reason)

    def close_branch(self, branch_id: str, *, actor: Actor, reason: str):
        return self.branches.close_branch(branch_id, actor=actor, reason=reason)

    def close_thread(self, thread_id: str, *, actor: Actor, reason: str):
        return self.threads.close_thread(thread_id, actor=actor, reason=reason)

    def discover(self, **kwargs):
        return self.discovery.discover(**kwargs)

    def record_external_finding(self, finding, *, actor: Actor,
                                 epistemic_status: EpistemicStatus = EpistemicStatus.INFERENCE,
                                 allow_private_source: bool = False):
        """Record a finding from an external evidence-search system (such as
        Ecology's FindingRecord) as a CCC anomaly.

        This package does not import the producing system. Anything
        supplying `.conclusion`, `.method`, `.source_material`,
        `.confidence`, `.verified`, and (optionally) `.evidence` -- a tuple
        of (source, excerpt) pairs -- can be recorded this way; the contract
        is structural, not a dependency.

        Four refusals, none of them silent downgrades:

        - A finding whose `.source_material` names a known-private source
          (PRIVATE_SOURCE_MARKERS below) is refused unless
          `allow_private_source=True` is passed explicitly. CCC is a public
          repository; Resume_OS stays private permanently specifically
          because it's this project's validation domain (real ground
          truth, deliberately not exposed), and ChatGPT_History carries
          un-scrubbed third-party PII that was flagged, not resolved. A
          content-search system pointed at either one by mistake must not
          silently leak into a public audit trail. This is a narrow,
          named-marker check, not a general secrets scanner -- it catches
          the two specific, already-identified cases, honestly, nothing
          more.

        - An unverified finding (`.verified` is False) is refused outright:
          an honest non-answer is not an anomaly worth recording.
        - A finding can only be machine-originated -- pass a MODEL or
          SYSTEM actor, never HUMAN, since nothing external to CCC gets to
          assert something as a human-established fact.
        - Internal self-inconsistency is refused: `.verified` True with no
          `.source_material`, or a `.confidence` outside [0, 1], is not a
          finding CCC can trust just because the boolean says so. This
          catches sloppy or malformed input; it does not, by itself, stop a
          deliberately forged one -- nothing here cryptographically proves
          `.verified` was honestly computed by whatever produced it. That
          requires a sealed, hash-verified claim (HERALD's discipline, not
          this intake), and isn't solved here.

        Duplicate detection is content-based and anti-probabilistic
        (ccc.matching), not a path comparison: it asks how implausible this
        finding's content overlap with an existing discovery would be as
        pure coincidence between two independent, honest processes, using
        the entropy of the matched text, not whether file paths line up.
        This is never proof either finding is genuine -- two forgeries can
        match each other perfectly and this will say so with full
        confidence. It only says the overlap is not plausibly accidental.

        A duplicate is still recorded, not silently absorbed: the point is
        an auditable, timestamped fact that this was re-observed, locked in
        via `relationships` pointing at what it matches and a `method`
        string carrying the anti-probability and match length -- not a
        second ANOMALY that would let a re-run query inflate an
        independent-occurrence count into a false pattern. Anything
        counting toward pattern-advancement later must exclude
        duplicate-tagged records; that filtering isn't built yet, but the
        tag it depends on now exists and is on the record.
        """
        if not finding.verified:
            raise ValueError(
                "refusing to record an unverified finding as a discovery -- "
                "an honest non-answer is not an anomaly"
            )
        if actor.kind not in (ActorType.MODEL, ActorType.SYSTEM):
            raise ValueError(
                "an external finding is machine-originated by construction; "
                "pass a MODEL or SYSTEM actor, not HUMAN"
            )
        if not finding.source_material:
            raise ValueError(
                "a verified finding with no source_material is "
                "self-inconsistent -- refusing to record it"
            )
        if not all(isinstance(s, str) and s for s in finding.source_material):
            raise ValueError(
                f"source_material {finding.source_material!r} contains a "
                "non-string or empty entry -- refusing a self-inconsistent finding"
            )
        # Shape is validated (all entries are real, non-empty strings) --
        # only now is it safe to search them for a private-source marker.
        if not allow_private_source and any(
            marker in source
            for source in finding.source_material
            for marker in PRIVATE_SOURCE_MARKERS
        ):
            raise ValueError(
                f"source_material {finding.source_material!r} names a known-private "
                "source (Resume_OS or ChatGPT_History) -- refusing to record into "
                "this public repository's audit trail without allow_private_source=True"
            )
        if not finding.conclusion:
            raise ValueError(
                "a verified finding with an empty conclusion is "
                "self-inconsistent -- refusing to record it"
            )
        if finding.confidence is not None and not 0.0 <= finding.confidence <= 1.0:
            raise ValueError(
                f"confidence {finding.confidence!r} is outside [0, 1] -- "
                "refusing a self-inconsistent finding"
            )

        evidence = getattr(finding, "evidence", ())
        for pair in evidence:
            if (not isinstance(pair, tuple) or len(pair) != 2
                    or not all(isinstance(x, str) and x for x in pair)):
                raise ValueError(
                    f"evidence entry {pair!r} is not a (source, excerpt) pair "
                    "of non-empty strings -- refusing a malformed finding "
                    "rather than raising a bare TypeError deeper in the call"
                )
        supporting_evidence = tuple(f"{source}: {excerpt}" for source, excerpt in evidence)
        comparison_text = "\n".join(excerpt for _source, excerpt in evidence) or finding.conclusion

        # Indexed lookup, not a scan of every prior discovery: candidates
        # are only the ones sharing at least one shingle with this finding,
        # so cost is independent of how many prior findings exist for the
        # (common) case of genuinely novel content. See ShingleIndex's
        # docstring for why this is safe -- exhaustive shingle extraction
        # has no recall gap, unlike a sampled/strided index.
        candidates = self._finding_shingle_index.candidates_for(comparison_text)
        match = matching.best_match_against(comparison_text, candidates)

        method = finding.method
        relationships: tuple = ()
        if match is not None and match[1].implausible_as_coincidence:
            matched_id, result = match
            relationships = (matched_id,)
            method = (
                f"{finding.method} -- duplicate detection: anti-probability "
                f"{result.anti_probability:.3e} of coincidental match, "
                f"{result.match_length} char overlap with {matched_id}"
            )

        record = self.discovery.discover(
            source_material=finding.source_material,
            method=method,
            conclusion=finding.conclusion,
            confidence=finding.confidence,
            supporting_evidence=supporting_evidence,
            actor=actor,
            epistemic_status=epistemic_status,
            stage=AnalysisStage.ANOMALY,
            relationships=relationships,
        )
        self._finding_shingle_index.add(record.discovery_id, comparison_text)
        return record

    def advance_discovery(self, *args, **kwargs):
        return self.discovery.advance(*args, **kwargs)

    def adopt_discovery(self, *args, **kwargs):
        return self.discovery.adopt(*args, **kwargs)

    def simulate(self, **kwargs):
        return self.simulation.simulate(**kwargs)

    def detect_conflict(self, **kwargs):
        return self.conflict.detect_conflict(**kwargs)

    def classify_conflict(self, *args, **kwargs):
        return self.conflict.classify_conflict(*args, **kwargs)

    def present_conflict(self, *args, **kwargs):
        return self.conflict.present_conflict(*args, **kwargs)

    def request_human_resolution(self, *args, **kwargs):
        return self.conflict.request_human_resolution(*args, **kwargs)

    def record_resolution(self, *args, **kwargs):
        return self.conflict.record_resolution(*args, **kwargs)

    def ask(self, **kwargs):
        return self.human_resolution.ask(**kwargs)

    def resolve_uncertainty(self, *args, **kwargs):
        return self.human_resolution.resolve(*args, **kwargs)

    def propose_term(self, **kwargs):
        return self.canonicalization.propose_term(**kwargs)

    def canonicalize(self, *args, **kwargs):
        return self.canonicalization.canonicalize(*args, **kwargs)

    def deprecate_term(self, *args, **kwargs):
        return self.canonicalization.deprecate(*args, **kwargs)

    def supersede_term(self, *args, **kwargs):
        return self.canonicalization.supersede(*args, **kwargs)

    def query(self, **kwargs):
        return self.query_engine.query(**kwargs)

    def present(self, *args, **kwargs):
        return self.query_engine.present(*args, **kwargs)

    def audit(self, *, object_id: str | None = None, operation: str | None = None):
        if object_id is not None:
            return self.audit_trail.for_object(object_id)
        return self.query_engine.query_audit(operation=operation)

    def resolve(self, object_id: str, *, kind: str = "uncertainty", actor: Actor, reason: str, authorization_basis: str, **kwargs):
        """Resolve one explicitly named human-resolution surface."""

        if kind == "uncertainty":
            return self.resolve_uncertainty(
                object_id,
                choice=kwargs["choice"],
                actor=actor,
                reason=reason,
                authorization_basis=authorization_basis,
            )
        if kind == "conflict":
            return self.record_resolution(
                object_id,
                choice=kwargs["choice"],
                actor=actor,
                reason=reason,
                authorization_basis=authorization_basis,
            )
        if kind == "inflection":
            return self.resolve_inflection(
                object_id,
                significance=kwargs["significance"],
                actor=actor,
                reason=reason,
                authorization_basis=authorization_basis,
            )
        raise ValueError(f"unknown resolution kind: {kind}")

    def validate_constitution(self) -> dict[str, Any]:
        violations: list[str] = []
        checks = 0
        for artifact in self.store.artifacts.values():
            checks += 1
            if artifact.machine_origin and artifact.provenance_status in {ProvenanceStatus.USER_ACCEPTED, ProvenanceStatus.USER_ESTABLISHED}:
                events = self.provenance.history(artifact.artifact_id)
                if not any(event.human_originating and event.to_status in {ProvenanceStatus.USER_ACCEPTED, ProvenanceStatus.USER_ESTABLISHED} for event in events):
                    violations.append(f"{artifact.artifact_id}: machine-origin user status lacks human event")
            if artifact.state in {ArtifactState.REDACTED, ArtifactState.ERASED}:
                checks += 1
                if artifact.content is not None:
                    violations.append(f"{artifact.artifact_id}: unavailable state retains content")
        for link in self.store.evidence_links.values():
            checks += 1
            if link.active:
                evidence = self.store.get_artifact(link.evidence_id)
                if evidence is None or not evidence.available:
                    violations.append(f"{link.link_id}: active link points to unavailable evidence")
        for sign in self.store.road_signs.values():
            checks += 1
            if sign.is_conclusion:
                violations.append(f"{sign.road_sign_id}: road sign is marked conclusion")
        for simulation in self.store.simulations.values():
            checks += 1
            if simulation.epistemic_status is not EpistemicStatus.SIMULATION:
                violations.append(f"{simulation.simulation_id}: simulation lost modeled status")
        for event in self.store.audit_events:
            checks += 1
            if event.actor.kind not in {ActorType.HUMAN, ActorType.SYSTEM, ActorType.MODEL, ActorType.EXTERNAL}:
                violations.append(f"{event.event_id}: unknown audit actor")
        return {
            "valid": not violations,
            "checks": checks,
            "violations": tuple(violations),
            "rule_version": self.rules.version,
            "constitutional_source": "BUILD_DIRECTIVE_ONLY; RATIFIED CCC TEXT NOT PRESENT",
        }

    def save(self, path: str | Path | None = None) -> Path:
        return self.store.save(path)

    @classmethod
    def load(cls, path: str | Path) -> "CCCSystem":
        return cls(store=CCCStore.load(path))
