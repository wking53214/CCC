"""Ingest cannot create conclusions.

``ingest`` (and ``record``, the same act under another name) takes material in. A conclusion is made by ``derive``,
``infer`` or ``interpret``, which keep the evidence it rests on and ask the permission under their own names. Before,
``ingest(epistemic_status=INFERENCE)`` made an inference, so a write permission that allowed only ``ingest`` allowed
inferences. None of these tests needs CNS and none skips.
"""

from __future__ import annotations

import pytest

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.errors import ConstitutionViolation, WritePermissionRefused

HUMAN = Actor.human("william")
MODEL = Actor.model("model")
BASIS = "explicit human decision"
CONCLUSIONS = [EpistemicStatus.INFERENCE, EpistemicStatus.INTERPRETATION]
ACTORS = [Actor.model("model"), Actor.system("system"), Actor.human("william"), Actor.external("tool")]


def _only(*operations):
    """A write permission that says yes to the named operations and no to everything else."""
    return lambda request: request.operation in operations


def _written(system: CCCSystem):
    store = system.store
    return (len(store.artifacts), len(store.evidence_links), len(store.lineage_events), len(store.provenance_events),
            len(store.epistemic_events), len(store.audit_events))


@pytest.mark.parametrize("status", CONCLUSIONS)
@pytest.mark.parametrize("actor", ACTORS, ids=lambda actor: actor.kind.value)
def test_the_defect_an_ingest_only_permission_no_longer_produces_a_conclusion(status, actor):
    system = CCCSystem(write_permission=_only("ingest"))
    before = _written(system)
    with pytest.raises(ConstitutionViolation) as refused:
        system.ingest("a conclusion dressed as material", actor=actor, epistemic_status=status)
    assert "derive" in str(refused.value) or "interpret" in str(refused.value)
    assert _written(system) == before and not system.store.artifacts


@pytest.mark.parametrize("status", CONCLUSIONS)
def test_record_and_the_private_ingest_are_the_same_door_and_refuse_the_same_way(status):
    for call, operation in (
        (lambda s: s.record("text", actor=MODEL, epistemic_status=status), "record"),
        (lambda s: s._ingest("text", actor=MODEL, epistemic_status=status), "ingest"),
    ):
        system = CCCSystem(write_permission=_only(operation))
        with pytest.raises(ConstitutionViolation):
            call(system)
        assert not system.store.artifacts


@pytest.mark.parametrize("status", CONCLUSIONS)
def test_without_a_permission_the_refusal_stands_too(status):
    system = CCCSystem()
    with pytest.raises(ConstitutionViolation):
        system.ingest("text", actor=MODEL, epistemic_status=status)
    assert not system.store.artifacts


def test_the_permission_is_asked_first_so_a_no_beats_the_refusal():
    system = CCCSystem(write_permission=_only())
    with pytest.raises(WritePermissionRefused):
        system.ingest("text", actor=MODEL, epistemic_status=EpistemicStatus.INFERENCE)


@pytest.mark.parametrize("status", [EpistemicStatus.UNKNOWN, EpistemicStatus.THEORY, EpistemicStatus.SIMULATION,
                                    EpistemicStatus.CONFLICTED])
def test_ingest_still_takes_in_material_of_every_other_status(status):
    system = CCCSystem(write_permission=_only("ingest"))
    assert system.ingest("material", actor=MODEL, epistemic_status=status).epistemic_status is status


def test_a_human_can_still_ingest_a_historical_record_or_evidence():
    system = CCCSystem(write_permission=_only("ingest"))
    for status in (EpistemicStatus.HISTORICAL_RECORD, EpistemicStatus.EVIDENCE):
        assert system.ingest("a fact", actor=HUMAN, epistemic_status=status,
                             authorization_basis=BASIS).epistemic_status is status


def test_derive_infer_and_interpret_are_the_routes_and_ask_under_their_own_names():
    system = CCCSystem(write_permission=_only("derive", "infer", "interpret"))
    assert system.derive("a conclusion", actor=MODEL).epistemic_status is EpistemicStatus.INFERENCE
    assert system.infer("another", actor=MODEL).epistemic_status is EpistemicStatus.INFERENCE
    assert system.interpret("a reading", actor=MODEL).epistemic_status is EpistemicStatus.INTERPRETATION
    with pytest.raises(WritePermissionRefused):
        system.ingest("material", actor=MODEL)


def test_a_human_version_of_a_conclusion_keeps_its_status_because_it_is_not_an_ingest():
    plain = CCCSystem()
    inference = plain.derive("a model inference", actor=MODEL)
    system = CCCSystem(store=plain.store, write_permission=_only())
    corrected = system.correct(inference.artifact_id, content="a corrected inference", actor=HUMAN, reason="r",
                               authorization_basis=BASIS)
    assert corrected.epistemic_status is EpistemicStatus.INFERENCE
