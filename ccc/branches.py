"""Explicit branch lifecycle and parent-thread preservation."""

from __future__ import annotations

from dataclasses import replace

from .models import Actor, Branch, BranchStatus, RelationshipType, new_id


class BranchManager:
    def __init__(self, store, audit, rules, lineage, threads) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules
        self.lineage = lineage
        self.threads = threads

    def create_branch(
        self,
        thread_id: str,
        *,
        title: str,
        actor: Actor,
        source_artifact_id: str | None = None,
        deferred: bool = False,
    ) -> Branch:
        self.store.threads[thread_id]
        if source_artifact_id is not None:
            self.store.require_artifact(source_artifact_id)
        branch = Branch(
            branch_id=new_id("branch"),
            parent_thread_id=thread_id,
            title=title,
            created_by=actor,
            source_artifact_id=source_artifact_id,
            deferred=deferred,
            status=BranchStatus.RESUMABLE if deferred else BranchStatus.OPEN,
        )
        self.store.add_branch(branch)
        thread = self.store.threads[thread_id]
        self.store.replace_thread(replace(thread, branch_ids=tuple(dict.fromkeys((*thread.branch_ids, branch.branch_id)))))
        if source_artifact_id:
            self.lineage.link(
                source_artifact_id,
                branch.branch_id,
                RelationshipType.BRANCH_OF,
                actor=actor,
                reason="branch preserves the source artifact and parent thread",
            )
        self.audit.record(
            actor=actor,
            operation="CREATE_BRANCH",
            object_id=branch.branch_id,
            previous_state=None,
            new_state={"parent_thread_id": thread_id, "status": branch.status.value, "deferred": deferred},
            reason=title,
            constitutional_rule="CCC-THREAD-001",
        )
        return branch

    def attach_branch(self, thread_id: str, branch_id: str, *, actor: Actor, reason: str) -> Branch:
        branch = self.store.branches[branch_id]
        if branch.parent_thread_id != thread_id:
            raise ValueError("branch does not belong to thread")
        thread = self.store.threads[thread_id]
        if branch_id not in thread.branch_ids:
            self.store.replace_thread(replace(thread, branch_ids=(*thread.branch_ids, branch_id)))
        self.audit.record(
            actor=actor,
            operation="ATTACH_BRANCH",
            object_id=branch_id,
            previous_state={"parent_thread_id": branch.parent_thread_id},
            new_state={"parent_thread_id": thread_id},
            reason=reason,
            constitutional_rule="CCC-THREAD-001",
        )
        return branch

    def resume_thread(self, branch_id: str, *, actor: Actor, reason: str) -> Branch:
        return self._set_status(branch_id, BranchStatus.OPEN, actor=actor, reason=reason, operation="RESUME_BRANCH")

    def return_to_branch(self, branch_id: str, *, actor: Actor, reason: str) -> Branch:
        return self.resume_thread(branch_id, actor=actor, reason=reason)

    def resolve_branch(self, branch_id: str, *, actor: Actor, reason: str) -> Branch:
        return self._set_status(branch_id, BranchStatus.RESOLVED, actor=actor, reason=reason, operation="RESOLVE_BRANCH")

    def close_branch(self, branch_id: str, *, actor: Actor, reason: str) -> Branch:
        return self._set_status(branch_id, BranchStatus.CLOSED, actor=actor, reason=reason, operation="CLOSE_BRANCH")

    def _set_status(self, branch_id: str, status: BranchStatus, *, actor: Actor, reason: str, operation: str) -> Branch:
        branch = self.store.branches[branch_id]
        updated = replace(branch, status=status)
        self.store.replace_branch(updated)
        self.audit.record(
            actor=actor,
            operation=operation,
            object_id=branch_id,
            previous_state={"status": branch.status.value},
            new_state={"status": status.value},
            reason=reason,
            constitutional_rule="CCC-THREAD-001",
        )
        return updated
