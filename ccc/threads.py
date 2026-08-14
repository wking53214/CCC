"""Primary cognitive thread lifecycle."""

from __future__ import annotations

from dataclasses import replace

from .models import Actor, Thread, ThreadStatus, new_id


class ThreadManager:
    def __init__(self, store, audit, rules) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules

    def create_thread(self, *, title: str, actor: Actor, parent_thread_id: str | None = None) -> Thread:
        thread = Thread(thread_id=new_id("thread"), title=title, created_by=actor, parent_thread_id=parent_thread_id)
        self.store.add_thread(thread)
        self.audit.record(
            actor=actor,
            operation="CREATE_THREAD",
            object_id=thread.thread_id,
            previous_state=None,
            new_state={"status": thread.status.value, "parent_thread_id": parent_thread_id},
            reason="explicit cognitive thread created",
            constitutional_rule="CCC-THREAD-001",
        )
        return thread

    def attach_artifact(self, thread_id: str, artifact_id: str, *, actor: Actor, reason: str) -> Thread:
        thread = self.store.threads[thread_id]
        self.store.require_artifact(artifact_id)
        updated = replace(thread, active_artifact_ids=tuple(dict.fromkeys((*thread.active_artifact_ids, artifact_id))))
        self.store.replace_thread(updated)
        self.audit.record(
            actor=actor,
            operation="ATTACH_THREAD_ARTIFACT",
            object_id=thread_id,
            previous_state={"active_artifact_ids": list(thread.active_artifact_ids)},
            new_state={"active_artifact_ids": list(updated.active_artifact_ids)},
            reason=reason,
            constitutional_rule="CCC-THREAD-001",
        )
        return updated
    def resume_thread(self, thread_id: str, *, actor: Actor, reason: str) -> Thread:
        return self._set_status(thread_id, ThreadStatus.OPEN, actor=actor, reason=reason, operation="RESUME_THREAD")

    def resolve_thread(self, thread_id: str, *, actor: Actor, reason: str) -> Thread:
        return self._set_status(thread_id, ThreadStatus.RESOLVED, actor=actor, reason=reason, operation="RESOLVE_THREAD")

    def close_thread(self, thread_id: str, *, actor: Actor, reason: str) -> Thread:
        return self._set_status(thread_id, ThreadStatus.CLOSED, actor=actor, reason=reason, operation="CLOSE_THREAD")

    def _set_status(self, thread_id: str, status: ThreadStatus, *, actor: Actor, reason: str, operation: str) -> Thread:
        thread = self.store.threads[thread_id]
        updated = replace(thread, status=status)
        self.store.replace_thread(updated)
        self.audit.record(
            actor=actor,
            operation=operation,
            object_id=thread_id,
            previous_state={"status": thread.status.value},
            new_state={"status": status.value},
            reason=reason,
            constitutional_rule="CCC-THREAD-001",
        )
        return updated
