"""Immutable domain objects and closed vocabularies used by CCC."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ProvenanceStatus(_ValueEnum):
    USER_ESTABLISHED = "USER_ESTABLISHED"
    USER_ACCEPTED = "USER_ACCEPTED"
    ASSISTANT_PROPOSED = "ASSISTANT_PROPOSED"
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"
    PROVENANCE_UNCERTAIN = "PROVENANCE_UNCERTAIN"


class EpistemicStatus(_ValueEnum):
    HISTORICAL_RECORD = "HISTORICAL_RECORD"
    EVIDENCE = "EVIDENCE"
    INFERENCE = "INFERENCE"
    INTERPRETATION = "INTERPRETATION"
    SIMULATION = "SIMULATION"
    THEORY = "THEORY"
    UNKNOWN = "UNKNOWN"
    CONFLICTED = "CONFLICTED"


class ActorType(_ValueEnum):
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
    MODEL = "MODEL"
    EXTERNAL = "EXTERNAL"


class ArtifactState(_ValueEnum):
    ACTIVE = "ACTIVE"
    REDACTED = "REDACTED"
    ERASED = "ERASED"


class RelationshipType(_ValueEnum):
    SUPPORTS = "SUPPORTS"
    DERIVED_FROM = "DERIVED_FROM"
    CONTRADICTS = "CONTRADICTS"
    CORRECTS = "CORRECTS"
    AMENDS = "AMENDS"
    SUPERSEDES = "SUPERSEDES"
    REDACTS = "REDACTS"
    ERASES = "ERASES"
    ADOPTS = "ADOPTS"
    BRANCH_OF = "BRANCH_OF"
    THREAD_CONTINUATION = "THREAD_CONTINUATION"
    # X instantiates principle Y -- the container/principle relationship
    # surfaced in the VSA/Citadel reconstruction ("Citadel is the system,
    # VSA is the governing law it was built to enforce"). Distinct from
    # DERIVED_FROM (X came out of Y) and SUPPORTS (X is evidence for Y).
    INSTANTIATES = "INSTANTIATES"
    RELATED_TO = "RELATED_TO"
    RESOLVES = "RESOLVES"


class RoadSignCategory(_ValueEnum):
    DIRECTION_CHANGE = "direction_change"
    CONTRADICTION = "contradiction"
    REPEATED_RETURN = "repeated_return"
    ABANDONMENT = "abandonment"
    CERTAINTY_SHIFT = "certainty_shift"
    UNCERTAINTY_SHIFT = "uncertainty_shift"
    INTUITION_SIGNAL = "intuition_signal"
    EMOTIONAL_DEVIATION = "emotional_deviation"
    FRUSTRATION = "frustration"
    BREAKTHROUGH = "breakthrough"
    REVERSAL = "reversal"
    DISAGREEMENT = "disagreement"
    ENTHUSIASM = "enthusiasm"
    UNEXPECTED_CONNECTION = "unexpected_connection"


class InflectionStatus(_ValueEnum):
    DETECTED = "DETECTED"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class ThreadStatus(_ValueEnum):
    OPEN = "OPEN"
    PAUSED = "PAUSED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class BranchStatus(_ValueEnum):
    OPEN = "OPEN"
    RESUMABLE = "RESUMABLE"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class AnalysisStage(_ValueEnum):
    ANOMALY = "ANOMALY"
    PATTERN = "PATTERN"
    MANDATE = "MANDATE"


class ConflictClass(_ValueEnum):
    EVIDENCE_VS_EVIDENCE = "EVIDENCE_VS_EVIDENCE"
    MACHINE_THEORY_VS_EVIDENCE = "MACHINE_THEORY_VS_EVIDENCE"
    THEORY_VS_EVIDENCE = "THEORY_VS_EVIDENCE"
    PROVENANCE_CONFLICT = "PROVENANCE_CONFLICT"
    EPISTEMIC_CONFLICT = "EPISTEMIC_CONFLICT"


class ConflictStatus(_ValueEnum):
    OPEN = "OPEN"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    RESOLVED = "RESOLVED"


class TermStatus(_ValueEnum):
    CANONICAL = "canonical"
    PROPOSED = "proposed"
    UNCERTAIN = "uncertain"
    EXTERNAL = "external"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def content_digest(content: str | None) -> str | None:
    """Return a content fingerprint; this is not an identity or signature."""

    if content is None:
        return None
    return sha256(content.encode("utf-8")).hexdigest()


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True)
class Actor:
    actor_id: str
    kind: ActorType
    label: str = ""

    @classmethod
    def human(cls, actor_id: str = "human", label: str = "") -> "Actor":
        return cls(actor_id, ActorType.HUMAN, label)

    @classmethod
    def system(cls, actor_id: str = "ccc", label: str = "") -> "Actor":
        return cls(actor_id, ActorType.SYSTEM, label)

    @classmethod
    def model(cls, actor_id: str = "model", label: str = "") -> "Actor":
        return cls(actor_id, ActorType.MODEL, label)

    @classmethod
    def external(cls, actor_id: str = "external", label: str = "") -> "Actor":
        return cls(actor_id, ActorType.EXTERNAL, label)


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    content: str | None
    origin: Actor
    provenance_status: ProvenanceStatus
    epistemic_status: EpistemicStatus
    state: ArtifactState = ArtifactState.ACTIVE
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    topics: tuple[str, ...] = field(default_factory=tuple)
    source_material: tuple[str, ...] = field(default_factory=tuple)
    instrument: str | None = None
    confidence: float | None = None
    presentation_priority: int = 0
    thread_id: str | None = None
    branch_id: str | None = None
    content_digest: str | None = None
    machine_processing_history: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "topics", tuple(self.topics))
        object.__setattr__(self, "source_material", tuple(self.source_material))
        object.__setattr__(self, "machine_processing_history", tuple(self.machine_processing_history))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        if self.content_digest is None and self.content is not None:
            object.__setattr__(self, "content_digest", content_digest(self.content))

    @property
    def machine_origin(self) -> bool:
        return self.origin.kind in {ActorType.MODEL, ActorType.SYSTEM}

    @property
    def machine_influenced(self) -> bool:
        """Whether this artifact explicitly carries machine-source lineage."""

        return bool(self.metadata.get("machine_source_ids"))

    @property
    def available(self) -> bool:
        return self.state is ArtifactState.ACTIVE and self.content is not None


@dataclass(frozen=True)
class ProvenanceEvent:
    event_id: str
    artifact_id: str
    event_type: str
    actor: Actor
    from_status: ProvenanceStatus | None
    to_status: ProvenanceStatus
    reason: str
    timestamp: str = field(default_factory=utc_now)
    human_originating: bool = False
    authorization_basis: str | None = None
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EpistemicEvent:
    event_id: str
    artifact_id: str
    actor: Actor
    from_status: EpistemicStatus
    to_status: EpistemicStatus
    reason: str
    timestamp: str = field(default_factory=utc_now)
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EvidenceLink:
    link_id: str
    evidence_id: str
    claim_id: str
    relation: RelationshipType = RelationshipType.SUPPORTS
    created_by: Actor = field(default_factory=Actor.system)
    rationale: str = ""
    support_strength: float | None = None
    active: bool = True
    invalidated_reason: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class LineageEvent:
    event_id: str
    source_id: str
    target_id: str
    relationship: RelationshipType
    actor: Actor
    reason: str
    timestamp: str = field(default_factory=utc_now)
    previous_state: str | None = None
    new_state: str | None = None
    provenance: ProvenanceStatus | None = None


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    timestamp: str
    actor: Actor
    operation: str
    object_id: str
    previous_state: Mapping[str, Any] | None
    new_state: Mapping[str, Any] | None
    reason: str
    provenance: ProvenanceStatus | None = None
    evidence: tuple[str, ...] = field(default_factory=tuple)
    constitutional_rule: str | None = None
    authorization_basis: str | None = None

    def __post_init__(self) -> None:
        if self.previous_state is not None:
            object.__setattr__(self, "previous_state", _freeze_mapping(self.previous_state))
        if self.new_state is not None:
            object.__setattr__(self, "new_state", _freeze_mapping(self.new_state))
        object.__setattr__(self, "evidence", tuple(self.evidence))


@dataclass(frozen=True)
class RoadSign:
    road_sign_id: str
    category: RoadSignCategory
    observation: str
    source_material: tuple[str, ...]
    detected_by: Actor
    confidence: float | None = None
    timestamp: str = field(default_factory=utc_now)
    linked_ids: tuple[str, ...] = field(default_factory=tuple)
    is_conclusion: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.is_conclusion:
            raise ValueError("a Road Sign is an indicator and cannot be a conclusion")
        object.__setattr__(self, "source_material", tuple(self.source_material))
        object.__setattr__(self, "linked_ids", tuple(self.linked_ids))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class InflectionPoint:
    inflection_id: str
    artifact_id: str | None
    thread_id: str | None
    detected_by: Actor
    directions: tuple[str, ...]
    divergence: float | None
    sensitivity: float | None
    significance: str | None = None
    machine_weight: float | None = None
    status: InflectionStatus = InflectionStatus.DETECTED
    reason: str = ""
    timestamp: str = field(default_factory=utc_now)
    human_resolution: str | None = None


@dataclass(frozen=True)
class Thread:
    thread_id: str
    title: str
    created_by: Actor
    status: ThreadStatus = ThreadStatus.OPEN
    parent_thread_id: str | None = None
    active_artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    branch_ids: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class Branch:
    branch_id: str
    parent_thread_id: str
    title: str
    created_by: Actor
    status: BranchStatus = BranchStatus.OPEN
    source_artifact_id: str | None = None
    deferred: bool = False
    current_artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class DiscoveryRecord:
    discovery_id: str
    source_material: tuple[str, ...]
    machine_origin: bool
    machine_processing_history: tuple[str, ...]
    method: str
    conclusion: str
    confidence: float | None
    supporting_evidence: tuple[str, ...]
    epistemic_status: EpistemicStatus
    provenance_status: ProvenanceStatus
    human_resolution: str | None = None
    relationships: tuple[str, ...] = field(default_factory=tuple)
    stage: AnalysisStage | None = None
    attribution: str | None = None
    created_by: Actor = field(default_factory=Actor.system)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class SimulationRecord:
    simulation_id: str
    inputs: tuple[str, ...]
    input_provenance: tuple[tuple[str, str], ...]
    assumptions: tuple[str, ...]
    shared_assumptions: tuple[str, ...]
    trajectory: tuple[str, ...]
    counterfactual: str
    output: str
    sensitivity: Mapping[str, Any]
    limitations: tuple[str, ...]
    created_by: Actor
    provenance_status: ProvenanceStatus = ProvenanceStatus.ASSISTANT_PROPOSED
    epistemic_status: EpistemicStatus = EpistemicStatus.SIMULATION
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "input_provenance", tuple(self.input_provenance))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "shared_assumptions", tuple(self.shared_assumptions))
        object.__setattr__(self, "trajectory", tuple(self.trajectory))
        object.__setattr__(self, "limitations", tuple(self.limitations))
        object.__setattr__(self, "sensitivity", _freeze_mapping(self.sensitivity))


@dataclass(frozen=True)
class UncertaintyRecord:
    uncertainty_id: str
    context: str
    known: tuple[str, ...]
    unknown: tuple[str, ...]
    inferred: tuple[str, ...]
    conflicted: tuple[str, ...]
    candidates: tuple[str, ...]
    requires_human_resolution: bool
    question: str
    created_by: Actor
    resolved_choice: str | None = None
    resolved_by: Actor | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class ConflictRecord:
    conflict_id: str
    material_ids: tuple[str, ...]
    classification: ConflictClass
    why_material: str
    choices: tuple[str, ...]
    downstream_consequences: tuple[str, ...]
    remaining_uncertainty: tuple[str, ...]
    detected_by: Actor
    status: ConflictStatus = ConflictStatus.OPEN
    human_resolution: str | None = None
    resolved_by: Actor | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CanonicalTerm:
    term_id: str
    term: str
    definition: str
    status: TermStatus
    origin_actor: Actor
    provenance_status: ProvenanceStatus
    source_material: tuple[str, ...] = field(default_factory=tuple)
    canonicalized_by: Actor | None = None
    superseded_by: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class RuleDecision:
    rule_id: str
    article: str | None
    requirement_id: str
    condition: str
    decision: str
    reason: str
    severity: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    override_status: str = "NO_OVERRIDE"
    evaluated_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class ConstitutionalRule:
    rule_id: str
    article: str | None
    requirement_id: str
    requirement_text: str
    condition: str
    decision: str
    reason: str
    severity: str = "ERROR"
    version: str = "1.0"
    source: str = "BUILD_DIRECTIVE"


@dataclass(frozen=True)
class HarnessRecord:
    harness_id: str
    constitutional_requirement: str
    test_description: str
    expected_result: str
    actual_result: str
    status: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    implementation_version: str = "0.1.0"
    historical_meaning: str = "UNSPECIFIED"


@dataclass(frozen=True)
class EvidenceValidation:
    claim_id: str
    valid: bool
    roots: tuple[str, ...]
    paths: tuple[tuple[str, ...], ...]
    invalid_links: tuple[str, ...]
    reason: str
