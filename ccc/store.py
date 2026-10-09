"""Small in-memory store with JSON snapshot persistence.

The store is deliberately boring: identity is held in dictionaries, history
is append-only lists, and erasure changes an artifact into a discoverable
tombstone rather than removing its identifier.
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, TypeVar

from .errors import DuplicateId, NotFound
from .models import (
    Actor,
    ActorType,
    Artifact,
    ArtifactState,
    ConflictClass,
    ConflictRecord,
    ConflictStatus,
    DiscoveryRecord,
    EpistemicEvent,
    EpistemicStatus,
    EvidenceLink,
    LineageEvent,
    ProvenanceEvent,
    ProvenanceStatus,
    RelationshipType,
    RoadSign,
    RoadSignCategory,
    UncertaintyRecord,
    AuditEvent,
)


T = TypeVar("T")


def _primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_primitive(item) for item in value]
    return value


def _actor(value: Mapping[str, Any]) -> Actor:
    return Actor(actor_id=value["actor_id"], kind=ActorType(value["kind"]), label=value.get("label", ""))


def _tuple(value: Iterable[Any] | None) -> tuple[Any, ...]:
    return tuple(value or ())


#: State-file sections for record types buried in wking53214/Graveyard
#: (ccc/2026-10-06-unused-record-types): turning points, threads, branches,
#: simulations and official terms. Kept verbatim across load and save.
RETIRED_SECTIONS = ("inflection_points", "threads", "branches", "simulations", "terms")


class CCCStore:
    """Canonical object store used by every CCC service."""

    def __init__(self, persistence_path: str | Path | None = None) -> None:
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self.artifacts: dict[str, Artifact] = {}
        self.provenance_events: list[ProvenanceEvent] = []
        self.epistemic_events: list[EpistemicEvent] = []
        self.evidence_links: dict[str, EvidenceLink] = {}
        self.lineage_events: list[LineageEvent] = []
        self.audit_events: list[AuditEvent] = []
        self.road_signs: dict[str, RoadSign] = {}
        self.discoveries: dict[str, DiscoveryRecord] = {}
        # discovery_id -> the exact text that discovery was matched on for
        # duplicate / recurrence detection (the joined evidence excerpts, or
        # the conclusion when there is no evidence). Persisted because the
        # shingle index and the recurrence detector are in-memory accelerators
        # rebuilt from this on load -- see CCCSystem._restore_derived_indexes.
        self.discovery_match_texts: dict[str, str] = {}
        # True once a state file that includes discovery_match_texts has been
        # loaded (or for a fresh store). False only after loading a file
        # written before that field existed -- the signal for CCCSystem to
        # reconstruct match texts rather than trust an absent list.
        self.match_texts_persisted: bool = True
        self.uncertainties: dict[str, UncertaintyRecord] = {}
        self.conflicts: dict[str, ConflictRecord] = {}
        self.rule_decisions: list[dict[str, Any]] = []
        # Sections for record types CCC no longer carries (buried in
        # wking53214/Graveyard, ccc/2026-10-06-unused-record-types). A state
        # file that holds them loads; the raw contents are kept exactly as
        # read and written back on save, so nothing is lost and a revival can
        # read them. Nothing in CCC interprets them.
        self.retired_sections: dict[str, Any] = {}

    def add_artifact(self, artifact: Artifact) -> None:
        if artifact.artifact_id in self.artifacts:
            raise DuplicateId(f"artifact {artifact.artifact_id} already exists")
        self.artifacts[artifact.artifact_id] = artifact

    def replace_artifact(self, artifact: Artifact) -> None:
        if artifact.artifact_id not in self.artifacts:
            raise NotFound(artifact.artifact_id)
        self.artifacts[artifact.artifact_id] = artifact

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        return self.artifacts.get(artifact_id)

    def require_artifact(self, artifact_id: str) -> Artifact:
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise NotFound(f"artifact {artifact_id}")
        return artifact

    def append_provenance(self, event: ProvenanceEvent) -> None:
        self.provenance_events.append(event)

    def append_epistemic(self, event: EpistemicEvent) -> None:
        self.epistemic_events.append(event)

    def add_evidence_link(self, link: EvidenceLink) -> None:
        self.evidence_links[link.link_id] = link

    def replace_evidence_link(self, link: EvidenceLink) -> None:
        if link.link_id not in self.evidence_links:
            raise NotFound(f"evidence link {link.link_id}")
        self.evidence_links[link.link_id] = link

    def append_lineage(self, event: LineageEvent) -> None:
        self.lineage_events.append(event)

    def append_audit(self, event: AuditEvent) -> None:
        self.audit_events.append(event)

    def add_road_sign(self, road_sign: RoadSign) -> None:
        self.road_signs[road_sign.road_sign_id] = road_sign

    def replace_road_sign(self, road_sign: RoadSign) -> None:
        if road_sign.road_sign_id not in self.road_signs:
            raise NotFound(f"road sign {road_sign.road_sign_id}")
        self.road_signs[road_sign.road_sign_id] = road_sign

    def add_discovery(self, discovery: DiscoveryRecord) -> None:
        self.discoveries[discovery.discovery_id] = discovery

    def replace_discovery(self, discovery: DiscoveryRecord) -> None:
        if discovery.discovery_id not in self.discoveries:
            raise NotFound(f"discovery {discovery.discovery_id}")
        self.discoveries[discovery.discovery_id] = discovery

    def add_uncertainty(self, uncertainty: UncertaintyRecord) -> None:
        self.uncertainties[uncertainty.uncertainty_id] = uncertainty

    def replace_uncertainty(self, uncertainty: UncertaintyRecord) -> None:
        if uncertainty.uncertainty_id not in self.uncertainties:
            raise NotFound(f"uncertainty {uncertainty.uncertainty_id}")
        self.uncertainties[uncertainty.uncertainty_id] = uncertainty

    def add_conflict(self, conflict: ConflictRecord) -> None:
        self.conflicts[conflict.conflict_id] = conflict

    def replace_conflict(self, conflict: ConflictRecord) -> None:
        if conflict.conflict_id not in self.conflicts:
            raise NotFound(f"conflict {conflict.conflict_id}")
        self.conflicts[conflict.conflict_id] = conflict

    def links_for_claim(self, claim_id: str, active_only: bool = False) -> tuple[EvidenceLink, ...]:
        links = tuple(link for link in self.evidence_links.values() if link.claim_id == claim_id)
        if active_only:
            links = tuple(link for link in links if link.active)
        return links

    def links_for_evidence(self, evidence_id: str, active_only: bool = False) -> tuple[EvidenceLink, ...]:
        links = tuple(link for link in self.evidence_links.values() if link.evidence_id == evidence_id)
        if active_only:
            links = tuple(link for link in links if link.active)
        return links

    def snapshot(self) -> dict[str, Any]:
        return {
            "artifacts": [_primitive(item) for item in self.artifacts.values()],
            "provenance_events": [_primitive(item) for item in self.provenance_events],
            "epistemic_events": [_primitive(item) for item in self.epistemic_events],
            "evidence_links": [_primitive(item) for item in self.evidence_links.values()],
            "lineage_events": [_primitive(item) for item in self.lineage_events],
            "audit_events": [_primitive(item) for item in self.audit_events],
            "road_signs": [_primitive(item) for item in self.road_signs.values()],
            "discoveries": [_primitive(item) for item in self.discoveries.values()],
            "discovery_match_texts": dict(self.discovery_match_texts),
            "uncertainties": [_primitive(item) for item in self.uncertainties.values()],
            "conflicts": [_primitive(item) for item in self.conflicts.values()],
            "rule_decisions": [_primitive(item) for item in self.rule_decisions],
            **self.retired_sections,
        }

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.persistence_path
        if target is None:
            raise ValueError("a persistence path is required")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.snapshot(), indent=2, sort_keys=True), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "CCCStore":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        store = cls(path)

        for value in raw.get("artifacts", []):
            store.add_artifact(
                Artifact(
                    artifact_id=value["artifact_id"],
                    content=value.get("content"),
                    origin=_actor(value["origin"]),
                    provenance_status=ProvenanceStatus(value["provenance_status"]),
                    epistemic_status=EpistemicStatus(value["epistemic_status"]),
                    state=ArtifactState(value.get("state", ArtifactState.ACTIVE.value)),
                    created_at=value["created_at"],
                    updated_at=value["updated_at"],
                    topics=_tuple(value.get("topics")),
                    source_material=_tuple(value.get("source_material")),
                    instrument=value.get("instrument"),
                    confidence=value.get("confidence"),
                    presentation_priority=value.get("presentation_priority", 0),
                    thread_id=value.get("thread_id"),
                    branch_id=value.get("branch_id"),
                    content_digest=value.get("content_digest"),
                    machine_processing_history=_tuple(value.get("machine_processing_history")),
                    metadata=value.get("metadata", {}),
                )
            )
        for value in raw.get("provenance_events", []):
            store.append_provenance(
                ProvenanceEvent(
                    event_id=value["event_id"],
                    artifact_id=value["artifact_id"],
                    event_type=value["event_type"],
                    actor=_actor(value["actor"]),
                    from_status=ProvenanceStatus(value["from_status"]) if value.get("from_status") else None,
                    to_status=ProvenanceStatus(value["to_status"]),
                    reason=value["reason"],
                    timestamp=value["timestamp"],
                    human_originating=value.get("human_originating", False),
                    authorization_basis=value.get("authorization_basis"),
                    evidence_ids=_tuple(value.get("evidence_ids")),
                )
            )
        for value in raw.get("epistemic_events", []):
            store.append_epistemic(
                EpistemicEvent(
                    event_id=value["event_id"],
                    artifact_id=value["artifact_id"],
                    actor=_actor(value["actor"]),
                    from_status=EpistemicStatus(value["from_status"]),
                    to_status=EpistemicStatus(value["to_status"]),
                    reason=value["reason"],
                    timestamp=value["timestamp"],
                    evidence_ids=_tuple(value.get("evidence_ids")),
                )
            )
        for value in raw.get("evidence_links", []):
            store.add_evidence_link(
                EvidenceLink(
                    link_id=value["link_id"],
                    evidence_id=value["evidence_id"],
                    claim_id=value["claim_id"],
                    relation=RelationshipType(value["relation"]),
                    created_by=_actor(value["created_by"]),
                    rationale=value.get("rationale", ""),
                    support_strength=value.get("support_strength"),
                    active=value.get("active", True),
                    invalidated_reason=value.get("invalidated_reason"),
                    created_at=value["created_at"],
                )
            )
        for value in raw.get("lineage_events", []):
            store.append_lineage(
                LineageEvent(
                    event_id=value["event_id"],
                    source_id=value["source_id"],
                    target_id=value["target_id"],
                    relationship=RelationshipType(value["relationship"]),
                    actor=_actor(value["actor"]),
                    reason=value["reason"],
                    timestamp=value["timestamp"],
                    previous_state=value.get("previous_state"),
                    new_state=value.get("new_state"),
                    provenance=ProvenanceStatus(value["provenance"]) if value.get("provenance") else None,
                )
            )
        for value in raw.get("audit_events", []):
            store.append_audit(
                AuditEvent(
                    event_id=value["event_id"],
                    timestamp=value["timestamp"],
                    actor=_actor(value["actor"]),
                    operation=value["operation"],
                    object_id=value["object_id"],
                    previous_state=value.get("previous_state"),
                    new_state=value.get("new_state"),
                    reason=value["reason"],
                    provenance=ProvenanceStatus(value["provenance"]) if value.get("provenance") else None,
                    evidence=_tuple(value.get("evidence")),
                    constitutional_rule=value.get("constitutional_rule"),
                    authorization_basis=value.get("authorization_basis"),
                )
            )
        for value in raw.get("road_signs", []):
            store.add_road_sign(
                RoadSign(
                    road_sign_id=value["road_sign_id"],
                    category=RoadSignCategory(value["category"]),
                    observation=value["observation"],
                    source_material=_tuple(value.get("source_material")),
                    detected_by=_actor(value["detected_by"]),
                    confidence=value.get("confidence"),
                    timestamp=value["timestamp"],
                    linked_ids=_tuple(value.get("linked_ids")),
                    is_conclusion=value.get("is_conclusion", False),
                    metadata=value.get("metadata", {}),
                )
            )
        for value in raw.get("discoveries", []):
            store.add_discovery(
                DiscoveryRecord(
                    discovery_id=value["discovery_id"],
                    source_material=_tuple(value.get("source_material")),
                    machine_origin=value["machine_origin"],
                    machine_processing_history=_tuple(value.get("machine_processing_history")),
                    method=value["method"],
                    conclusion=value["conclusion"],
                    confidence=value.get("confidence"),
                    supporting_evidence=_tuple(value.get("supporting_evidence")),
                    epistemic_status=EpistemicStatus(value["epistemic_status"]),
                    provenance_status=ProvenanceStatus(value["provenance_status"]),
                    human_resolution=value.get("human_resolution"),
                    relationships=_tuple(value.get("relationships")),
                    stage=__import__("ccc.models", fromlist=["AnalysisStage"]).AnalysisStage(value["stage"]) if value.get("stage") else None,
                    attribution=value.get("attribution"),
                    created_by=_actor(value["created_by"]),
                    created_at=value["created_at"],
                    # Serialized all along, never restored (measured 2026-09-08):
                    # after a reopen every record's event time fell back to
                    # created_at, and event time is the tiebreaker that picks a
                    # recurrence cluster's representative. Same inputs, a
                    # different governed outcome, no warning.
                    event_start_date=value.get("event_start_date"),
                    event_end_date=value.get("event_end_date"),
                )
            )
        store.match_texts_persisted = "discovery_match_texts" in raw
        store.discovery_match_texts = {
            str(k): str(v) for k, v in raw.get("discovery_match_texts", {}).items()
        }
        for value in raw.get("uncertainties", []):
            store.add_uncertainty(
                UncertaintyRecord(
                    uncertainty_id=value["uncertainty_id"],
                    context=value["context"],
                    known=_tuple(value.get("known")),
                    unknown=_tuple(value.get("unknown")),
                    inferred=_tuple(value.get("inferred")),
                    conflicted=_tuple(value.get("conflicted")),
                    candidates=_tuple(value.get("candidates")),
                    requires_human_resolution=value["requires_human_resolution"],
                    question=value["question"],
                    created_by=_actor(value["created_by"]),
                    resolved_choice=value.get("resolved_choice"),
                    resolved_by=_actor(value["resolved_by"]) if value.get("resolved_by") else None,
                    created_at=value["created_at"],
                )
            )
        for value in raw.get("conflicts", []):
            store.add_conflict(
                ConflictRecord(
                    conflict_id=value["conflict_id"],
                    material_ids=_tuple(value.get("material_ids")),
                    classification=ConflictClass(value["classification"]),
                    why_material=value["why_material"],
                    choices=_tuple(value.get("choices")),
                    downstream_consequences=_tuple(value.get("downstream_consequences")),
                    remaining_uncertainty=_tuple(value.get("remaining_uncertainty")),
                    detected_by=_actor(value["detected_by"]),
                    status=ConflictStatus(value.get("status", ConflictStatus.OPEN.value)),
                    human_resolution=value.get("human_resolution"),
                    resolved_by=_actor(value["resolved_by"]) if value.get("resolved_by") else None,
                    created_at=value["created_at"],
                )
            )
        store.rule_decisions.extend(raw.get("rule_decisions", []))
        store.retired_sections = {
            key: raw[key] for key in RETIRED_SECTIONS if raw.get(key)
        }
        return store
