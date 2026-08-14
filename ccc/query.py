"""Query and presentation surfaces; ranking never deletes records."""

from __future__ import annotations

from .models import Artifact, ArtifactState, EpistemicStatus, ProvenanceStatus, RelationshipType


class QueryEngine:
    def __init__(self, store) -> None:
        self.store = store

    def query(
        self,
        *,
        time_start: str | None = None,
        time_end: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        event_type: str | None = None,
        instrument: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        presentation_priority: int | None = None,
        min_presentation_priority: int | None = None,
        max_presentation_priority: int | None = None,
        provenance: ProvenanceStatus | None = None,
        epistemic_status: EpistemicStatus | None = None,
        thread: str | None = None,
        branch: str | None = None,
        relationship: RelationshipType | None = None,
        artifact: str | None = None,
        include_erased: bool = True,
    ) -> tuple[Artifact, ...]:
        records = tuple(self.store.artifacts.values())
        if artifact is not None:
            records = tuple(item for item in records if item.artifact_id == artifact)
        if not include_erased:
            records = tuple(item for item in records if item.state is not ArtifactState.ERASED)
        if time_start is not None:
            records = tuple(item for item in records if item.created_at >= time_start)
        if time_end is not None:
            records = tuple(item for item in records if item.created_at <= time_end)
        if topic is not None:
            records = tuple(item for item in records if topic in item.topics)
        if source is not None:
            records = tuple(item for item in records if item.origin.actor_id == source or source in item.source_material)
        if instrument is not None:
            records = tuple(item for item in records if item.instrument == instrument)
        if min_confidence is not None:
            records = tuple(item for item in records if item.confidence is not None and item.confidence >= min_confidence)
        if max_confidence is not None:
            records = tuple(item for item in records if item.confidence is not None and item.confidence <= max_confidence)
        if presentation_priority is not None:
            records = tuple(item for item in records if item.presentation_priority == presentation_priority)
        if min_presentation_priority is not None:
            records = tuple(item for item in records if item.presentation_priority >= min_presentation_priority)
        if max_presentation_priority is not None:
            records = tuple(item for item in records if item.presentation_priority <= max_presentation_priority)
        if provenance is not None:
            records = tuple(item for item in records if item.provenance_status is provenance)
        if epistemic_status is not None:
            records = tuple(item for item in records if item.epistemic_status is epistemic_status)
        if thread is not None:
            records = tuple(item for item in records if item.thread_id == thread)
        if branch is not None:
            records = tuple(item for item in records if item.branch_id == branch)
        if event_type is not None:
            ids = {event.object_id for event in self.store.audit_events if event.operation == event_type}
            records = tuple(item for item in records if item.artifact_id in ids)
        if relationship is not None:
            ids = {
                object_id
                for event in self.store.lineage_events
                if event.relationship is relationship
                for object_id in (event.source_id, event.target_id)
            }
            records = tuple(item for item in records if item.artifact_id in ids)
        return records

    def present(self, records: tuple[Artifact, ...] | None = None, *, limit: int | None = None) -> tuple[Artifact, ...]:
        selected = records if records is not None else self.query()
        ranked = tuple(sorted(selected, key=lambda item: (item.presentation_priority, item.created_at), reverse=True))
        return ranked[:limit] if limit is not None else ranked

    def query_audit(self, *, operation: str | None = None, actor_kind: str | None = None):
        events = tuple(self.store.audit_events)
        if operation is not None:
            events = tuple(event for event in events if event.operation == operation)
        if actor_kind is not None:
            events = tuple(event for event in events if event.actor.kind.value == actor_kind)
        return events
