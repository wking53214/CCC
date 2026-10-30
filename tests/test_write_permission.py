"""The permission check an application can put in front of CCC's record-creating methods.

A system given ``write_permission`` asks it once, first, at ingest, record, derive, infer and interpret, and goes on
only if the answer is exactly True. Anything else refuses before CCC touches its store, rules or audit trail. The
methods that carry a human's action (decide, correct, amend, supersede, redact, erase) never ask. Without a check
nothing changes. None of these tests needs CNS and none skips.
"""

from __future__ import annotations

import inspect
import threading

import pytest

from ccc import Actor, CCCSystem
from ccc.cns_connector import _scratches
from ccc.errors import WritePermissionRefused
from ccc.permission import WriteRequest

HUMAN = Actor.human("william")
BASIS = "explicit human decision"

#: Each covered method with a call that works on an empty store, and the text its first argument carries.
COVERED = {
    "ingest": lambda s: s.ingest("a document", actor=HUMAN),
    "record": lambda s: s.record("a record", actor=HUMAN),
    "derive": lambda s: s.derive("a conclusion", actor=Actor.model()),
    "infer": lambda s: s.infer("an inference", actor=Actor.model()),
    "interpret": lambda s: s.interpret("an interpretation", actor=Actor.model()),
}


class Check:
    """A permission check that records what it was asked and answers as told."""

    def __init__(self, verdict=True):
        self.verdict = verdict
        self.requests: list[WriteRequest] = []

    def __call__(self, request):
        self.requests.append(request)
        if isinstance(self.verdict, BaseException):
            raise self.verdict
        return self.verdict


def _bytes(system: CCCSystem, tmp_path, name: str) -> bytes:
    return system.store.save(tmp_path / name).read_bytes()


def test_without_a_permission_every_method_works_as_before():
    system = CCCSystem()
    for call in COVERED.values():
        assert call(system).artifact_id


@pytest.mark.parametrize("method", COVERED)
def test_a_yes_lets_the_call_through_and_the_check_is_asked_exactly_once(method):
    check = Check(True)
    system = CCCSystem(write_permission=check)
    artifact = COVERED[method](system)
    assert system.store.require_artifact(artifact.artifact_id) is not None
    # interpret calls derive, which writes the record; the nesting must not ask again.
    assert [r.operation for r in check.requests] == [method]


def test_the_request_names_the_method_and_carries_the_callers_arguments_as_given():
    check = Check(True)
    CCCSystem(write_permission=check).ingest("the text", actor=HUMAN, topics=("a",), metadata={"source_id": "s1"})
    (request,) = check.requests
    assert request.operation == "ingest"
    assert request.args == ("the text",)
    assert set(request.kwargs) == {"actor", "topics", "metadata"}  # no defaults filled in
    assert request.kwargs["metadata"]["source_id"] == "s1"


def test_the_request_is_a_copy_so_the_check_cannot_change_what_is_written():
    seen = {}

    def tampering(request):
        request.kwargs["metadata"]["source_id"] = "forged"
        seen["ok"] = True
        return True

    theirs = {"source_id": "real"}
    artifact = CCCSystem(write_permission=tampering).ingest("text", actor=HUMAN, metadata=theirs)
    assert seen["ok"]
    assert theirs == {"source_id": "real"}
    assert artifact.metadata["source_id"] == "real"


@pytest.mark.parametrize("verdict", [False, None, 1, "yes", object(), [True]])
@pytest.mark.parametrize("method", COVERED)
def test_anything_but_true_refuses_and_leaves_the_store_untouched(method, verdict, tmp_path):
    system = CCCSystem(write_permission=Check(verdict))
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(WritePermissionRefused) as refused:
        COVERED[method](system)
    assert refused.value.operation == method
    assert _bytes(system, tmp_path, "after.json") == before
    assert list(system.audit_trail.all()) == []


@pytest.mark.parametrize("method", COVERED)
def test_a_check_that_raises_is_a_refusal_and_the_error_is_its_cause(method, tmp_path):
    system = CCCSystem(write_permission=Check(RuntimeError("roster down")))
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(WritePermissionRefused) as refused:
        COVERED[method](system)
    assert isinstance(refused.value.__cause__, RuntimeError)
    assert "roster down" in str(refused.value)
    assert _bytes(system, tmp_path, "after.json") == before


def test_arguments_that_cannot_be_copied_are_refused_not_written(tmp_path):
    check = Check(True)
    system = CCCSystem(write_permission=check)
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(WritePermissionRefused):
        system.ingest("text", actor=HUMAN, metadata={"lock": threading.Lock()})
    assert check.requests == []  # it never got as far as asking
    assert _bytes(system, tmp_path, "after.json") == before


def test_the_methods_that_carry_a_humans_action_never_ask():
    plain = CCCSystem()
    ids = {
        name: plain.ingest(f"material for {name}", actor=HUMAN).artifact_id
        for name in ("correct", "amend", "supersede", "redact", "erase")
    }
    deny = Check(False)
    system = CCCSystem(store=plain.store, write_permission=deny)

    system.decide("a human decision", actor=HUMAN, reason="r", authorization_basis=BASIS)
    for name in ("correct", "amend", "supersede"):
        getattr(system, name)(ids[name], content=f"new text for {name}", actor=HUMAN, reason="r",
                              authorization_basis=BASIS)
    system.redact(ids["redact"], actor=HUMAN, reason="r", authorization_basis=BASIS)
    system.erase(ids["erase"], actor=HUMAN, reason="r", authorization_basis=BASIS)

    assert deny.requests == []


def test_a_permission_must_be_callable():
    with pytest.raises(TypeError):
        CCCSystem(write_permission="yes")  # type: ignore[arg-type]


def test_the_permission_is_not_saved_with_the_store_and_load_can_be_given_one(tmp_path):
    guarded = CCCSystem(write_permission=Check(False))
    path = guarded.save(tmp_path / "s.json")
    assert CCCSystem.load(path).ingest("loaded without a check", actor=HUMAN)
    with pytest.raises(WritePermissionRefused):
        CCCSystem.load(path, write_permission=Check(False)).ingest("x", actor=HUMAN)


def test_the_connectors_scratch_copies_carry_no_permission():
    """A scratch copy is where the CNS connector judges an attempt; it must never ask a check, or judging would
    spend a one-use permission."""
    check = Check(False)
    system = CCCSystem(write_permission=check)
    with _scratches(system) as fresh:
        scratch = fresh()
        assert scratch._write_permission is None
        assert scratch.ingest("judged here", actor=HUMAN)
    assert check.requests == []


@pytest.mark.parametrize("method", ["ingest", "derive"])
def test_the_public_signature_is_unchanged(method):
    """The CNS connector binds a call to the real signature to build its digest, so the signature is part of
    the contract. The front door must show the same parameters as before the check existed."""
    signature = inspect.signature(getattr(CCCSystem, method))
    expected = {
        "ingest": ["self", "content", "actor", "provenance_status", "epistemic_status", "source_material", "topics",
                   "instrument", "confidence", "presentation_priority", "thread_id", "branch_id",
                   "machine_processing", "metadata", "human_independent_origin", "reason", "authorization_basis"],
        "derive": ["self", "conclusion", "evidence_ids", "actor", "method", "confidence", "source_material",
                   "machine_consensus", "topics"],
    }[method]
    assert list(signature.parameters) == expected
    assert getattr(CCCSystem, method).__name__ == method
