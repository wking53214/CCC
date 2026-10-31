"""The human verifier: an optional check in front of every human-only operation.

``CCCSystem(human_verifier=...)`` calls the verifier once, first, with a frozen HumanRequest, before decide, correct,
amend, supersede, redact, erase, accept, establish_provenance, reject, ratify, record_resolution,
resolve_uncertainty, adopt_discovery, a MANDATE advancement or an epistemic promotion writes anything. Only the exact
value True permits. Without a verifier nothing changes, and a human operation never asks the machine write
permission. None of these tests needs CNS and none skips.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ccc import Actor, AnalysisStage, CCCSystem, EpistemicStatus, ProvenanceStatus
from ccc.errors import HumanVerificationRefused, WritePermissionRefused
from ccc.human_auth import HumanRequest
from ccc.models import content_digest

HUMAN = Actor.human("william")
ANYONE = Actor.human("anyone")
MODEL = Actor.model("model")
BASIS = "explicit human decision"


class Verifier:
    """A verifier that records what it was asked and answers as told."""

    def __init__(self, verdict=True):
        self.verdict = verdict
        self.requests: list[HumanRequest] = []

    def __call__(self, request):
        self.requests.append(request)
        if isinstance(self.verdict, BaseException):
            raise self.verdict
        return self.verdict


class World:
    """One store holding what each human operation needs, built with no guard on it."""


def _world() -> World:
    plain = CCCSystem()
    w = World()
    w.store = plain.store

    def human_fact(text, **kw):
        return plain.ingest(text, actor=HUMAN, epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
                            authorization_basis=BASIS, **kw)

    w.fact = human_fact("a human-established fact")
    w.fact2 = human_fact("a second human-established fact")
    for name in ("correct", "amend", "supersede", "redact", "erase"):
        setattr(w, name, human_fact(f"a fact to {name}"))
    w.unclassified = plain.ingest("a note", actor=HUMAN, authorization_basis=BASIS)
    w.proposals = {
        name: plain.derive(f"a proposal for {name}", actor=MODEL, evidence_ids=(w.fact.artifact_id,))
        for name in ("accept", "establish", "reject", "ratify", "ratify_established")
    }
    w.pattern = plain.discover(source_material=(w.fact.artifact_id,), method="scan", conclusion="a pattern",
                               confidence=0.5, actor=MODEL, stage=AnalysisStage.PATTERN)
    w.anomaly = plain.discover(source_material=(w.fact.artifact_id,), method="scan", conclusion="an anomaly",
                               confidence=0.5, actor=MODEL, stage=AnalysisStage.ANOMALY)
    w.conflict = plain.detect_conflict(
        material_ids=(w.fact.artifact_id, w.fact2.artifact_id), why_material="two facts disagree",
        choices=("a", "b"), downstream_consequences=("an effect",), remaining_uncertainty=("which holds",),
        actor=MODEL)
    w.uncertainty = plain.ask(context="a context", question="which one?", actor=MODEL)
    return w


def _guarded(w: World, verifier, **extra) -> CCCSystem:
    return CCCSystem(store=w.store, human_verifier=verifier, **extra)


#: Every human-only operation with a call that works on _world(), and what its request must say.
OPERATIONS = {
    "decide": lambda s, w: s.decide("a human decision", actor=ANYONE, reason="r", authorization_basis=BASIS),
    "correct": lambda s, w: s.correct(w.correct.artifact_id, content="fixed", actor=HUMAN, reason="r",
                                      authorization_basis=BASIS),
    "amend": lambda s, w: s.amend(w.amend.artifact_id, content="amended", actor=HUMAN, reason="r",
                                  authorization_basis=BASIS),
    "supersede": lambda s, w: s.supersede(w.supersede.artifact_id, content="replaced", actor=HUMAN, reason="r",
                                          authorization_basis=BASIS),
    "redact": lambda s, w: s.redact(w.redact.artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS),
    "erase": lambda s, w: s.erase(w.erase.artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS),
    "accept": lambda s, w: s.accept(w.proposals["accept"].artifact_id, actor=HUMAN, reason="r",
                                    authorization_basis=BASIS),
    "establish_provenance": lambda s, w: s.establish_provenance(
        w.proposals["establish"].artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS),
    "reject": lambda s, w: s.reject(w.proposals["reject"].artifact_id, actor=HUMAN, reason="r",
                                    authorization_basis=BASIS),
    "ratify": lambda s, w: s.ratify(w.proposals["ratify"].artifact_id, actor=HUMAN, reason="r",
                                    authorization_basis=BASIS),
    "record_resolution": lambda s, w: s.record_resolution(w.conflict.conflict_id, choice="a", actor=HUMAN,
                                                          reason="r", authorization_basis=BASIS),
    "resolve_uncertainty": lambda s, w: s.resolve_uncertainty(w.uncertainty.uncertainty_id, choice="a",
                                                              actor=HUMAN, reason="r", authorization_basis=BASIS),
    "adopt_discovery": lambda s, w: s.adopt_discovery(w.anomaly.discovery_id, actor=HUMAN, reason="r",
                                                      authorization_basis=BASIS),
    "advance_discovery": lambda s, w: s.advance_discovery(
        w.pattern.discovery_id, stage=AnalysisStage.MANDATE, actor=HUMAN, reason="r", human_event=True,
        authorization_basis=BASIS, evidence_ids=(w.fact.artifact_id,)),
    "classify": lambda s, w: s.classify(w.unclassified.artifact_id, EpistemicStatus.HISTORICAL_RECORD, actor=HUMAN,
                                        reason="r"),
}


def _bytes(system: CCCSystem, tmp_path, name: str) -> bytes:
    return system.store.save(tmp_path / name).read_bytes()


def test_the_defect_a_human_decision_by_anyone_is_written_even_when_upstream_said_no(tmp_path):
    """Before the verifier, decide(actor=Actor.human("anyone")) wrote a USER_ESTABLISHED record whatever had been
    decided upstream. With a verifier that refuses, it writes nothing."""
    system = CCCSystem(human_verifier=Verifier(False))
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(HumanVerificationRefused):
        system.decide("let it ship", actor=ANYONE, reason="r", authorization_basis=BASIS)
    assert _bytes(system, tmp_path, "after.json") == before
    assert not system.store.artifacts and list(system.audit_trail.all()) == []


def test_without_a_verifier_every_human_operation_works_as_before():
    w = _world()
    system = CCCSystem(store=w.store)
    for call in OPERATIONS.values():
        call(system, w)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_a_yes_lets_the_call_through_and_the_verifier_is_asked_exactly_once(operation):
    w = _world()
    verifier = Verifier(True)
    OPERATIONS[operation](_guarded(w, verifier), w)
    # ratify calls accept, and resolve calls its own door: the nesting must not ask again.
    assert [r.operation for r in verifier.requests] == [operation]


@pytest.mark.parametrize("verdict", [False, None, 1, "yes", object(), [True]])
@pytest.mark.parametrize("operation", OPERATIONS)
def test_anything_but_true_refuses_and_writes_nothing(operation, verdict, tmp_path):
    w = _world()
    system = _guarded(w, Verifier(verdict))
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(HumanVerificationRefused) as refused:
        OPERATIONS[operation](system, w)
    assert refused.value.operation == operation
    assert _bytes(system, tmp_path, "after.json") == before  # byte for byte


@pytest.mark.parametrize("operation", OPERATIONS)
def test_a_verifier_that_raises_is_a_refusal_and_the_error_is_its_cause(operation, tmp_path):
    w = _world()
    system = _guarded(w, Verifier(RuntimeError("identity service down")))
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(HumanVerificationRefused) as refused:
        OPERATIONS[operation](system, w)
    assert isinstance(refused.value.__cause__, RuntimeError)
    assert "identity service down" in str(refused.value)
    assert _bytes(system, tmp_path, "after.json") == before


def test_the_request_names_the_operation_the_actor_the_targets_the_content_and_the_basis():
    w = _world()
    verifier = Verifier(True)
    system = _guarded(w, verifier)
    system.correct(w.correct.artifact_id, content="fixed text", actor=HUMAN, reason="r", authorization_basis=BASIS,
                   attestation={"signed_by": "william", "token": "t-1"})
    (request,) = verifier.requests
    assert request == HumanRequest(
        operation="correct", actor_id="william", target_ids=(w.correct.artifact_id,),
        content_digest=content_digest("fixed text"), authorization_basis=BASIS,
        attestation={"signed_by": "william", "token": "t-1"})


def test_a_request_with_no_new_content_carries_no_digest_and_no_attestation_by_default():
    w = _world()
    verifier = Verifier(True)
    _guarded(w, verifier).redact(w.redact.artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS)
    (request,) = verifier.requests
    assert request.content_digest is None and request.attestation is None
    assert request.target_ids == (w.redact.artifact_id,)


def test_the_request_is_frozen_and_a_copy_so_the_verifier_cannot_change_what_is_written():
    w = _world()
    seen = {}

    def tampering(request):
        with pytest.raises(FrozenInstanceError):
            request.operation = "something else"  # type: ignore[misc]
        request.attestation["token"] = "forged"
        seen["ok"] = True
        return True

    theirs = {"token": "real"}
    _guarded(w, tampering).redact(w.redact.artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS,
                                  attestation=theirs)
    assert seen["ok"] and theirs == {"token": "real"}


def test_an_attestation_that_cannot_be_copied_is_refused_not_written(tmp_path):
    import threading

    w = _world()
    system = _guarded(w, Verifier(True))
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(HumanVerificationRefused):
        system.redact(w.redact.artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS,
                      attestation=threading.Lock())
    assert _bytes(system, tmp_path, "after.json") == before


def test_ratify_and_resolve_ask_once_under_the_name_of_the_call_made():
    w = _world()
    verifier = Verifier(True)
    system = _guarded(w, verifier)
    system.ratify(w.proposals["ratify_established"].artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS,
                  status=ProvenanceStatus.USER_ESTABLISHED)
    system.resolve(w.uncertainty.uncertainty_id, kind="uncertainty", choice="a", actor=HUMAN, reason="r",
                   authorization_basis=BASIS)
    assert [r.operation for r in verifier.requests] == ["ratify", "resolve_uncertainty"]


def test_a_machine_stage_advance_does_not_ask_but_a_mandate_does():
    w = _world()
    verifier = Verifier(True)
    system = _guarded(w, verifier)
    system.advance_discovery(w.anomaly.discovery_id, stage=AnalysisStage.PATTERN, actor=MODEL, reason="2nd")
    assert verifier.requests == []
    OPERATIONS["advance_discovery"](system, w)
    assert [r.operation for r in verifier.requests] == ["advance_discovery"]


def test_machine_operations_never_ask_the_human_verifier():
    verifier = Verifier(False)
    system = CCCSystem(human_verifier=verifier)
    system.ingest("a document", actor=MODEL)
    system.derive("a conclusion", actor=MODEL)
    system.detect_road_sign(observation="seen", category=__import__("ccc").RoadSignCategory.REVERSAL, actor=MODEL)
    assert verifier.requests == []


def test_a_machine_epistemic_change_does_not_ask_but_a_promotion_does():
    w = _world()
    verifier = Verifier(True)
    system = _guarded(w, verifier)
    system.classify(w.proposals["accept"].artifact_id, EpistemicStatus.THEORY, actor=MODEL, reason="lower")
    assert verifier.requests == []
    OPERATIONS["classify"](system, w)
    assert [r.operation for r in verifier.requests] == ["classify"]


def test_a_human_operation_never_asks_the_machine_write_permission():
    """The owner's rule: human-only operations never ask write_permission, with or without a verifier."""
    asked = []

    def deny(request):
        asked.append(request.operation)
        return False

    w = _world()
    system = _guarded(w, Verifier(True), write_permission=deny)
    for operation, call in OPERATIONS.items():
        call(system, w)
    assert asked == []
    with pytest.raises(WritePermissionRefused):
        system.ingest("a machine-side write", actor=MODEL)


def test_a_verifier_must_be_callable():
    with pytest.raises(TypeError):
        CCCSystem(human_verifier="yes")  # type: ignore[arg-type]
