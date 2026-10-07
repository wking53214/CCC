"""Public orchestration facade for the Cognitive Continuity Constitution."""

from __future__ import annotations

import warnings
from dataclasses import replace
from pathlib import Path
from typing import Any

from .audit import AuditTrail
from .conflict import ConflictManager
from .constitutional_rules import ConstitutionalRuleEngine
from .discovery import DiscoveryManager
from .text_matching import (
    TextMatcherMissing,
    checked_duplicate,
    checked_recurrence,
    require_matcher,
)
from .text_matching import INSTALL_HINT as _MATCHER_HINT
from .errors import PrivateSourcesNotStated
from .semantic import DEFAULT_SEMANTIC_THRESHOLD, evaluate_recurrence
from .epistemic_state import EpistemicManager
from .evidence import EvidenceManager
from .human_resolution import HumanResolutionManager
from .lineage import LineageManager
from .models import (
    Actor,
    ActorType,
    AnalysisStage,
    Artifact,
    ArtifactState,
    DiscoveryRecord,
    EpistemicStatus,
    ProvenanceStatus,
    RelationshipType,
    RoadSignCategory,
    new_id,
    utc_now,
)
from .provenance import ProvenanceManager
from .query import QueryEngine
from .road_signs import RoadSignManager
from .store import CCCStore


def _stated_private_sources(value) -> tuple[str, ...] | None:
    """The caller's private-source list, checked. None means not stated."""
    if value is None:
        return None
    if isinstance(value, str) or not all(isinstance(m, str) and m for m in value):
        raise TypeError(
            "private_source_markers must be a collection of non-empty strings "
            f"(an empty one states there are none); got {value!r}"
        )
    return tuple(value)


def _has_saved_state(path: str | Path) -> bool:
    """A persistence file worth loading: exists and isn't empty. An empty
    file (a bare `touch` of the path) is treated as "fresh, nothing to
    resume" rather than a corrupt-JSON error."""
    p = Path(path)
    return p.is_file() and p.stat().st_size > 0


# APM ladder position, for picking a recurrence cluster's representative:
# the member that has climbed furthest is the one escalation must branch on.
_STAGE_RANK = {
    AnalysisStage.ANOMALY: 0,
    AnalysisStage.PATTERN: 1,
    AnalysisStage.MANDATE: 2,
}


def _effective_event_time(record: "DiscoveryRecord") -> tuple:
    """Temporal sort key for a discovery: event-time if known, else ingest time.

    Returns a tuple that gives event times priority over ingest times, so a
    finding from an older conversation sorts earlier even if it was processed
    later. For discoveries with no known event time, created_at is the fallback.
    """
    if record.event_start_date is not None:
        return (0, record.event_start_date)
    return (1, record.created_at)

# Substring stamped into a discovery's `method` when it was recorded as an
# anti-probability duplicate. A duplicate is a re-observation, not an
# independent occurrence: it stays reachable through `relationships` for
# transitive cluster resolution, but is excluded from the occurrence count
# and from representative selection.
_DUPLICATE_METHOD_MARKER = "duplicate detection"


def _reconstructed_match_text(record) -> str | None:
    """Best-effort recovery of the text a discovery was matched on for
    duplicate / recurrence detection, for state files written before
    discovery_match_texts was persisted. The live value is the joined
    evidence excerpts, or the conclusion when there is no evidence;
    supporting_evidence stores them as ``f"{source}: {excerpt}"``, so
    splitting on the first ": " recovers the excerpt unless a source id
    itself contains ": ". Imperfect, but a stable approximation beats the
    discovery being invisible to both matchers forever after an upgrade."""
    if record.supporting_evidence:
        return "\n".join(
            line.split(": ", 1)[1] if ": " in line else line
            for line in record.supporting_evidence
        )
    return record.conclusion or None


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

    def __init__(self, *, store: CCCStore | None = None,
                 persistence_path: str | Path | None = None,
                 semantic_index=None,
                 semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
                 text_matcher=None,
                 private_source_markers=None) -> None:
        """
        private_source_markers: the sources a machine finding must not cite
            unless allow_private_source=True, matched as substrings of each
            source_material entry. CCC names no repositories; the application
            states them. Required by record_external_finding, which refuses
            until it is stated; an empty collection states there are none.
        text_matcher: provider satisfying ccc.text_matching.TextMatcher
            (cccb.TextMatcher). Injected, never imported. Required only by
            record_external_finding, which refuses without one; see
            ccc/text_matching.py.
        semantic_index: optional provider satisfying ccc.semantic.SemanticIndex.
            Injected, never imported -- CCC defines the interface and owns the
            policy; the model lives outside. None (the default) means
            recurrence stays purely lexical and behaves exactly as it did
            before the interface existed.
        semantic_threshold: CCC's declared policy for how similar counts.
            Provider-dependent and uncalibrated; see ccc/semantic.py.
        """
        if store is not None:
            self.store = store
        elif persistence_path is not None and _has_saved_state(persistence_path):
            # persistence_path meant "resume from here if there's something
            # to resume" -- it used to only mean "save here later," so
            # CCCSystem(persistence_path=p) silently started empty even when
            # p held a real prior state, and the only way to actually load
            # was CCCStore.load(p) + CCCSystem(store=...) as two steps.
            self.store = CCCStore.load(persistence_path)
        else:
            self.store = CCCStore(persistence_path)
        self.audit_trail = AuditTrail(self.store)
        self.rules = ConstitutionalRuleEngine(self.store)
        self.lineage = LineageManager(self.store, self.audit_trail, self.rules)
        self.evidence = EvidenceManager(self.store, self.audit_trail, self.rules)
        self.provenance = ProvenanceManager(self.store, self.audit_trail, self.lineage, self.rules, self.evidence)
        self.epistemic = EpistemicManager(self.store, self.audit_trail, self.rules, self.evidence)
        self.human_resolution = HumanResolutionManager(self.store, self.audit_trail, self.rules)
        self.road_signs = RoadSignManager(self.store, self.audit_trail, self.rules)
        self.discovery = DiscoveryManager(self.store, self.audit_trail, self.rules, self.evidence)
        require_matcher(text_matcher)
        self.text_matcher = text_matcher
        self.private_source_markers = _stated_private_sources(private_source_markers)
        self.semantic_index = semantic_index
        self.semantic_threshold = semantic_threshold
        self.conflict = ConflictManager(self.store, self.audit_trail, self.rules, self.human_resolution)
        self.query_engine = QueryEngine(self.store)
        self._restore_derived_indexes()

    def _index_match_text(self, discovery_id: str, text: str) -> None:
        if self.text_matcher is not None:
            self.text_matcher.add(discovery_id, text)

    def _restore_derived_indexes(self) -> None:
        """Rebuild the accelerators that live outside CCCStore: the attached
        text matcher's indexes.
        CCCStore persists the facts; these are derived
        structures built empty in __init__, so after CCCStore.load() they
        would start empty while the store is full -- occurrence #2 arriving
        in a new session would then match nothing and the
        anomaly -> pattern -> mandate ladder would never climb across a
        session boundary, which is the exact case this system exists for.

        A no-op for a fresh store (every source is empty), so it is always
        safe to run at the end of __init__.
        """
        indexed = set()
        for did, text in self.store.discovery_match_texts.items():
            if did in self.store.discoveries:
                self._index_match_text(did, text)
                indexed.add(did)

        # State file predates discovery_match_texts: reconstruct so prior
        # findings are not permanently invisible to the matchers. Only in
        # this case -- a current file's missing entries are direct
        # discover() records that were never indexed and must stay that way.
        if not self.store.match_texts_persisted:
            reconstructed = 0
            for did, record in self.store.discoveries.items():
                if did in indexed:
                    continue
                text = _reconstructed_match_text(record)
                if not text:
                    continue
                self._index_match_text(did, text)
                reconstructed += 1
            if reconstructed:
                warnings.warn(
                    f"CCC: rebuilt the duplicate/recurrence index for {reconstructed} "
                    "discovery(ies) from a state file predating discovery_match_texts; "
                    "the recovered texts are approximate. Re-save to persist exact values.",
                    stacklevel=3,
                )

        # The semantic index is a derived structure too. Before this the
        # lexical detectors were rebuilt on load and the semantic index was
        # not, so after a reopen every prior finding was invisible to a
        # non-persistent provider -- the cross-session case the rebuild
        # above exists for (measured 2026-09-08).
        if self.semantic_index is not None:
            for did, text in self.store.discovery_match_texts.items():
                if did in self.store.discoveries:
                    try:
                        self.semantic_index.add(did, text)
                    except Exception:  # noqa: BLE001 -- losing the provider costs reach, never integrity
                        pass

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

    # Relationship types that have their own gated lifecycle methods -- they
    # must not be recorded through the generic relate() door, which would
    # skip the state changes and human-authorization those operations carry.
    _LIFECYCLE_RELATIONSHIPS = frozenset({
        RelationshipType.CORRECTS, RelationshipType.AMENDS, RelationshipType.SUPERSEDES,
        RelationshipType.REDACTS, RelationshipType.ERASES,
    })

    def relate(self, source_id: str, target_id: str, relationship: RelationshipType, *,
               actor: Actor, reason: str, evidence: tuple[str, ...] = ()):
        """Record a typed, immutable relationship edge between two objects
        that is not a lifecycle change -- e.g. INSTANTIATES ("Citadel
        instantiates the VSA principle"), DERIVED_FROM, RELATED_TO. Lifecycle
        relationships (CORRECTS/AMENDS/SUPERSEDES/REDACTS/ERASES) are refused
        here; use correct()/amend()/supersede()/redact()/erase()."""
        if relationship in self._LIFECYCLE_RELATIONSHIPS:
            raise ValueError(
                f"{relationship.value} is a lifecycle relationship -- record it via its "
                "own method (correct/amend/supersede/redact/erase), not relate()"
            )
        return self.lineage.link(
            source_id, target_id, relationship, actor=actor, reason=reason, evidence=evidence,
        )

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

        - A finding whose `.source_material` names a private source is
          refused unless `allow_private_source=True` is passed explicitly.
          Which sources are private is the caller's statement
          (`private_source_markers` at construction), not CCC's: CCC names
          no repositories. Until it is stated, every machine finding is
          refused (PrivateSourcesNotStated), so the guard cannot be lost by
          forgetting to configure it. A content-search system pointed at a
          private corpus by mistake must not silently leak into an audit
          trail. This is a narrow substring check, not a general secrets
          scanner.

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
        (measured by the attached text matcher, cccb.matching), not a path comparison: it asks how implausible this
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
        if self.text_matcher is None:
            raise TextMatcherMissing(
                "refusing to record a machine finding with no text matcher "
                "attached: without it a re-submitted finding could count as a "
                "new occurrence and climb the anomaly -> pattern ladder. "
                + _MATCHER_HINT
            )
        if self.private_source_markers is None:
            raise PrivateSourcesNotStated(
                "refusing to record a machine finding before the private sources "
                "are stated: pass CCCSystem(private_source_markers=...), an empty "
                "collection if there are none, so the private-source guard cannot "
                "be lost by omission"
            )
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
            for marker in self.private_source_markers
        ):
            raise ValueError(
                f"source_material {finding.source_material!r} names a known-private "
                "source (one of the stated private_source_markers) -- refusing to "
                "record it into the audit trail without allow_private_source=True"
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

        # Duplicate check first. The matcher measures; CCC decides what a
        # duplicate means (below: linked, tagged, never counted).
        known = self.store.discoveries
        duplicate = checked_duplicate(
            self.text_matcher.duplicate_of(comparison_text), known)

        method = finding.method
        relationships: tuple = ()
        if duplicate is not None:
            matched_id, anti_probability, match_length = duplicate
            relationships = (matched_id,)
            method = (
                f"{finding.method} -- {_DUPLICATE_METHOD_MARKER}: anti-probability "
                f"{anti_probability:.3e} of coincidental match, "
                f"{match_length} char overlap with {matched_id}"
            )

        # Recurrence: a non-duplicate finding whose concept signature
        # matches an existing discovery is a fresh, independent occurrence
        # of the same pattern -- APM's 2nd (or 3rd). Checked only when this
        # is NOT an anti-probability duplicate: a re-observation of the same
        # content is the opposite signal and must not advance a pattern.
        is_duplicate = bool(relationships)
        recurrence = None if is_duplicate else checked_recurrence(
            self.text_matcher.recurrence_of(comparison_text), known)

        # Semantic evidence, when a provider is attached. Consulted for its
        # opinion and recorded either way; it never overrides the lexical
        # verdict, because a semantic-only match is a CANDIDATE and
        # establishes nothing. See ccc/semantic.py for why that asymmetry
        # exists -- a model's judgement does not silently become
        # authoritative in a governed store.
        recurrence_decision = None
        if not is_duplicate:
            recurrence_decision = evaluate_recurrence(
                text=comparison_text,
                lexical_match=recurrence is not None,
                semantic_index=self.semantic_index,
                semantic_threshold=self.semantic_threshold,
            )
            if recurrence_decision.is_candidate:
                # Lexical found nothing and semantic did. Recorded as an
                # observable indicator, not acted on: escalation still
                # requires the mechanism CCC actually trusts.
                self._flag_semantic_candidate(record_actor=actor,
                                              decision=recurrence_decision)

        representative_id = None
        if recurrence is not None:
            _best_id, best_jaccard, matches = recurrence
            # A pattern is a cluster of linked occurrences, not one record,
            # and lexical drift fragments it: occurrence #5 can match #2 and
            # #4 without matching #1. Expand each lexical match to its whole
            # cluster by following relationships back to roots already on
            # record, so a chain d1 <- d2 <- d3 resolves as one cluster even
            # when this finding only matched d3. Without this, escalation
            # branches on a fragment and mints a parallel PATTERN.
            cluster: set = {did for did, _j in matches}
            frontier = list(cluster)
            while frontier:
                did = frontier.pop()
                for rel in self.store.discoveries[did].relationships:
                    if rel in self.store.discoveries and rel not in cluster:
                        cluster.add(rel)
                        frontier.append(rel)
            # A duplicate is a re-observation, not an independent occurrence.
            # It stays in `cluster` for reachability -- a recurrence that
            # only matched a re-observation still has to reach the real root
            # through it -- but it is not itself an occurrence, so it is
            # excluded from the count and from representative selection.
            occurrences = [
                did for did in cluster
                if _DUPLICATE_METHOD_MARKER not in self.store.discoveries[did].method
            ] or list(cluster)
            # Representative: the occurrence furthest along the APM ladder,
            # ordered by event-time (when the underlying evidence occurred),
            # breaking ties by discovery_id for determinism. Event time is
            # preserved separately from created_at (when CCC learned of it);
            # discoveries with no known event time fall back to created_at.
            representative_id = min(
                occurrences,
                key=lambda did: (
                    -_STAGE_RANK[self.store.discoveries[did].stage],
                    _effective_event_time(self.store.discoveries[did]),
                    did,
                ),
            )
            rep = self.store.discoveries[representative_id]
            # Link the representative only, not every cluster member: a
            # strong pattern can recur hundreds of times, and every member
            # links the representative anyway, so the star is fully
            # reconstructable without an O(cluster) tuple on each record.
            relationships = (*relationships, representative_id)
            method = (
                f"{method} -- recurrence of {representative_id} "
                f"(best concept overlap {best_jaccard:.0%}, cluster stage "
                f"{rep.stage.value}, {len(occurrences)} prior occurrence(s))"
            )

        event_start_date = getattr(finding, "event_start_date", None)
        event_end_date = getattr(finding, "event_end_date", None)

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
            event_start_date=event_start_date,
            event_end_date=event_end_date,
        )

        if representative_id is not None:
            rep = self.store.discoveries[representative_id]
            if rep.stage is AnalysisStage.ANOMALY:
                # 2nd independent occurrence -> the pattern is real enough
                # to investigate. A machine may make this transition;
                # discovery.py only gates MANDATE behind a human.
                self.discovery.advance(
                    representative_id, stage=AnalysisStage.PATTERN, actor=actor,
                    reason=f"2nd independent occurrence detected: {record.discovery_id}",
                )
            elif rep.stage is AnalysisStage.PATTERN:
                # 3rd (or later) occurrence. MANDATE is human-only -- this
                # advances nothing. Every 3rd-and-later occurrence records
                # its OWN REPEATED_RETURN road sign (an observable
                # indicator, explicitly not a conclusion): APM's rule is
                # halt-and-review on the third strike, and a per-occurrence
                # trail is the pressure that produces -- each sign still
                # carries pattern_id + occurrence_count, so a reviewer can
                # still collapse them by pattern.
                self._flag_repeated_return(
                    representative_id, record.discovery_id, actor,
                    occurrence_count=len(occurrences) + 1,
                )
            # rep.stage is MANDATE: a human already established it. The new
            # occurrence is linked (via relationships, above) and nothing
            # else -- the machine does not get to add to a human's mandate.

        self.store.discovery_match_texts[record.discovery_id] = comparison_text
        # A provider that failed used to leave no trace at all: the decision
        # went out of scope and the trail filled with correct-looking
        # lexical_only verdicts while a whole signal was dead (measured
        # 2026-09-08). The failure is now an audit event on the finding.
        if recurrence_decision is not None and recurrence_decision.semantic_error:
            self.audit_trail.record(
                actor=self.system_actor,
                operation="semantic_provider_failed",
                object_id=record.discovery_id,
                previous_state=None,
                new_state={
                    "semantic_provider": recurrence_decision.semantic_provider,
                    "semantic_threshold": recurrence_decision.semantic_threshold,
                    "semantic_error": recurrence_decision.semantic_error,
                    "decision": recurrence_decision.decision,
                },
                reason="the semantic provider did not answer; this decision is lexical-only",
            )
        self._index_match_text(record.discovery_id, comparison_text)
        if self.semantic_index is not None:
            try:
                self.semantic_index.add(record.discovery_id, comparison_text)
            except Exception:  # noqa: BLE001
                # A provider that cannot index must not stop CCC recording a
                # finding. Losing the provider costs reach, never integrity.
                pass
        return record

    def _flag_repeated_return(
        self, pattern_id: str, occurrence_id: str, actor: Actor, *, occurrence_count: int
    ) -> None:
        """Record a REPEATED_RETURN road sign for the 3rd-or-later
        occurrence of a pattern. One sign per occurrence -- APM halts and
        reviews on the third strike, and the per-occurrence trail is that
        pressure made visible. `occurrence_count` is the true count of
        independent (non-duplicate) occurrences on record including this
        one; `pattern_id` groups the signs for a reviewer who wants them
        collapsed."""
        self.road_signs.detect_road_sign(
            category=RoadSignCategory.REPEATED_RETURN,
            observation=(
                f"occurrence {occurrence_count} of pattern {pattern_id}: {occurrence_id} "
                "-- MANDATE candidate, human establishment required"
            ),
            actor=actor,
            linked_ids=(pattern_id, occurrence_id),
            metadata={"pattern_id": pattern_id, "occurrence_count": occurrence_count},
        )

    def _flag_semantic_candidate(self, *, record_actor: Actor, decision) -> None:
        """Record an UNEXPECTED_CONNECTION road sign for a semantic-only match.

        Lexical recurrence found nothing and the semantic provider did. That
        is a relationship worth a reviewer's attention and NOT a recurrence:
        it establishes nothing, advances no stage, and joins no cluster.

        A road sign is the right shape for it precisely because a road sign is
        an observable indicator and explicitly not a conclusion -- which is
        exactly what a model's similarity score is. The threshold, provider
        and nearest score travel in the metadata so the reviewer can judge the
        claim rather than take it.
        """
        nearest = decision.semantic_matches[0] if decision.semantic_matches else None
        self.road_signs.detect_road_sign(
            category=RoadSignCategory.UNEXPECTED_CONNECTION,
            observation=(
                "semantic-only recurrence candidate: lexical matching found no "
                "prior occurrence, "
                + (f"but {decision.semantic_provider} places this nearest to "
                   f"{nearest.finding_id} at similarity {nearest.similarity:.3f} "
                   f"(threshold {decision.semantic_threshold}). "
                   if nearest else "")
                + "Candidate only -- establishes no recurrence and advances no stage."
            ),
            actor=record_actor,
            linked_ids=tuple(m.finding_id for m in decision.semantic_matches[:3]),
            metadata={
                "decision": decision.decision,
                "semantic_provider": decision.semantic_provider,
                "semantic_threshold": decision.semantic_threshold,
                "nearest_similarity": nearest.similarity if nearest else None,
                "established": False,
            },
        )

    def advance_discovery(self, *args, **kwargs):
        return self.discovery.advance(*args, **kwargs)

    def adopt_discovery(self, *args, **kwargs):
        return self.discovery.adopt(*args, **kwargs)

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
    def load(cls, path: str | Path, *, semantic_index=None,
             semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
             text_matcher=None,
             private_source_markers=None) -> "CCCSystem":
        # The provider is attached at load so the derived semantic index is
        # rebuilt from the store along with the lexical ones.
        return cls(store=CCCStore.load(path), semantic_index=semantic_index,
                   semantic_threshold=semantic_threshold, text_matcher=text_matcher,
                   private_source_markers=private_source_markers)
