"""A write permission that offers `commit` and `abort` is told how the write it permitted ended.

A one-use permission spent when it says yes is lost if the write then fails before changing anything. CCC tells a
permission that has `commit` and `abort` methods: `commit()` once the call returned, and on an exception `abort()` only
if the store is exactly as it was before the call (the number of records in every section it keeps), `commit()` if
anything was written. A call that fails halfway has used its permission: a retry on top of a partial write is not the
call that was approved. A permission with neither method behaves as before.
"""

from __future__ import annotations

import pytest

from ccc.errors import WritePermissionRefused
from ccc.models import Actor, EpistemicStatus
from ccc.system import CCCSystem

TEXT = "Invoice INV-2207 came to $412.00."


class Settling:
    def __init__(self, answer=True):
        self.answer, self.told = answer, []

    def __call__(self, request):
        return self.answer

    def commit(self):
        self.told.append("commit")

    def abort(self):
        self.told.append("abort")


def ingest(system, **more):
    return system.ingest(TEXT, actor=Actor.model("herald"), epistemic_status=EpistemicStatus.THEORY, **more)


def test_a_call_that_returns_tells_the_permission_to_commit():
    permission = Settling()
    ingest(CCCSystem(write_permission=permission))
    assert permission.told == ["commit"]


def test_a_call_that_fails_before_changing_anything_tells_the_permission_to_abort():
    permission = Settling()
    system = CCCSystem(write_permission=permission)
    with pytest.raises(Exception):
        ingest(system, source_material=("no-such-artifact",))
    assert permission.told == ["abort"] and len(system.store.artifacts) == 0


def test_a_call_that_fails_after_changing_the_store_has_used_its_permission(monkeypatch):
    permission = Settling()
    system = CCCSystem(write_permission=permission)

    def fails(event):
        raise RuntimeError("the audit trail could not take it")
    monkeypatch.setattr(system.store, "append_audit", fails)
    with pytest.raises(RuntimeError):
        ingest(system)
    assert len(system.store.artifacts) + len(system.store.provenance_events) > 0, "the failure must come after a write"
    assert permission.told == ["commit"]


def test_a_refusal_by_the_permission_is_not_a_write_and_tells_it_nothing():
    permission = Settling(answer=False)
    with pytest.raises(WritePermissionRefused):
        ingest(CCCSystem(write_permission=permission))
    assert permission.told == []


def test_a_permission_with_neither_method_works_as_before():
    system = CCCSystem(write_permission=lambda request: True)
    ingest(system)
    assert len(system.store.artifacts) == 1


def test_a_permission_whose_settling_raises_does_not_hide_the_write_or_its_failure():
    class Broken(Settling):
        def commit(self):
            raise RuntimeError("cannot settle")

        def abort(self):
            raise RuntimeError("cannot settle")
    ingest(CCCSystem(write_permission=Broken()))
    system = CCCSystem(write_permission=Broken())
    with pytest.raises(Exception) as caught:
        ingest(system, source_material=("no-such-artifact",))
    assert "cannot settle" not in str(caught.value)


def test_a_method_that_calls_another_gated_method_tells_the_permission_once():
    permission = Settling()
    system = CCCSystem(write_permission=permission)
    system.interpret(TEXT, actor=Actor.model("herald"))
    assert permission.told == ["commit"]
