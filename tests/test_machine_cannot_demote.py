"""A machine cannot demote a record a human holds.

Moving a record off HISTORICAL_RECORD or EVIDENCE (epistemic), or off USER_ESTABLISHED or USER_ACCEPTED (provenance),
is a human act. Before, ``classify(human_root, THEORY)`` by a model and a provenance move to UNRESOLVED by any actor
both went through, and every claim resting on the root lost it. A machine may still flag a record, through a conflict
or a road sign, which change nothing about it. With a human verifier configured, a human's demotion asks it too. None
of these tests needs CNS and none skips.
"""

from __future__ import annotations

import pytest

from ccc import Actor, CCCSystem, EpistemicStatus, ProvenanceStatus, RoadSignCategory
from ccc.errors import ConstitutionViolation, HumanVerificationRefused

HUMAN = Actor.human("william")
MODEL = Actor.model("model")
BASIS = "explicit human decision"

MACHINES = [Actor.model("model"), Actor.system("system"), Actor.external("tool")]
LOWER = [EpistemicStatus.THEORY, EpistemicStatus.CONFLICTED, EpistemicStatus.INFERENCE, EpistemicStatus.UNKNOWN,
         EpistemicStatus.SIMULATION, EpistemicStatus.INTERPRETATION]


class Verifier:
    def __init__(self, verdict=True):
        self.verdict = verdict
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.verdict


def _root(system: CCCSystem, status=EpistemicStatus.HISTORICAL_RECORD):
    """A human-held root with a machine claim resting on it."""
    root = system.ingest("a human-held root", actor=HUMAN, epistemic_status=status, authorization_basis=BASIS)
    claim = system.derive("a claim resting on the root", actor=MODEL, evidence_ids=(root.artifact_id,))
    return root, claim


def _links_active(system: CCCSystem, claim_id: str) -> bool:
    links = system.store.links_for_claim(claim_id)
    return bool(links) and all(link.active for link in links)


@pytest.mark.parametrize("held", [EpistemicStatus.HISTORICAL_RECORD, EpistemicStatus.EVIDENCE])
@pytest.mark.parametrize("target", LOWER)
@pytest.mark.parametrize("machine", MACHINES, ids=lambda actor: actor.kind.value)
def test_a_machine_cannot_move_a_record_off_historical_record_or_evidence(held, target, machine):
    system = CCCSystem()
    root, claim = _root(system, held)
    events = len(system.store.epistemic_events)
    with pytest.raises(ConstitutionViolation):
        system.classify(root.artifact_id, target, actor=machine, reason="a model disagrees")
    assert system.store.require_artifact(root.artifact_id).epistemic_status is held
    assert len(system.store.epistemic_events) == events
    assert _links_active(system, claim.artifact_id)
    assert system.validate_evidence_chain(claim.artifact_id).valid


def test_the_defect_a_model_classifying_a_human_root_as_theory_is_refused_and_its_links_stay_active():
    system = CCCSystem()
    root, claim = _root(system)
    with pytest.raises(ConstitutionViolation) as refused:
        system.classify(root.artifact_id, EpistemicStatus.THEORY, actor=MODEL, reason="a model disagrees")
    assert "human" in str(refused.value).lower()
    assert _links_active(system, claim.artifact_id)


def test_a_human_can_still_demote_and_the_dependents_follow():
    system = CCCSystem()
    root, claim = _root(system)
    system.classify(root.artifact_id, EpistemicStatus.THEORY, actor=HUMAN, reason="I was wrong")
    assert system.store.require_artifact(root.artifact_id).epistemic_status is EpistemicStatus.THEORY
    assert not _links_active(system, claim.artifact_id)


@pytest.mark.parametrize("held", [ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.USER_ACCEPTED])
@pytest.mark.parametrize("machine", MACHINES, ids=lambda actor: actor.kind.value)
@pytest.mark.parametrize("route", ["transition", "resolve"])
def test_a_machine_cannot_move_a_record_off_user_established_or_user_accepted(held, machine, route):
    system = CCCSystem()
    root, claim = _root(system)
    if held is ProvenanceStatus.USER_ACCEPTED:
        system.accept(root.artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS)
    assert system.store.require_artifact(root.artifact_id).provenance_status is held
    events = len(system.store.provenance_events)
    with pytest.raises(ConstitutionViolation):
        if route == "transition":
            system.provenance.transition(root.artifact_id, ProvenanceStatus.UNRESOLVED, actor=machine,
                                         reason="a model doubts it", authorization_basis="machine doubt",
                                         human_event=True)
        else:
            system.provenance.resolve(root.artifact_id, actor=machine, status=ProvenanceStatus.UNRESOLVED,
                                      reason="a model doubts it", authorization_basis="machine doubt")
    assert system.store.require_artifact(root.artifact_id).provenance_status is held
    assert len(system.store.provenance_events) == events
    assert _links_active(system, claim.artifact_id)
    assert system.validate_evidence_chain(claim.artifact_id).valid


def test_a_human_can_still_move_a_record_to_unresolved():
    system = CCCSystem()
    root, _claim = _root(system)
    system.provenance.resolve(root.artifact_id, actor=HUMAN, status=ProvenanceStatus.UNRESOLVED, reason="doubt",
                              authorization_basis=BASIS)
    assert system.store.require_artifact(root.artifact_id).provenance_status is ProvenanceStatus.UNRESOLVED


def test_a_machine_may_still_flag_a_human_record_through_a_conflict_or_a_road_sign():
    system = CCCSystem()
    root, claim = _root(system)
    other = system.ingest("a second human fact", actor=HUMAN, epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
                          authorization_basis=BASIS)
    conflict = system.detect_conflict(
        material_ids=(root.artifact_id, other.artifact_id), why_material="the model sees a disagreement",
        choices=("a", "b"), downstream_consequences=("an effect",), remaining_uncertainty=("which holds",),
        actor=MODEL)
    sign = system.detect_road_sign(observation="the root may not hold", category=RoadSignCategory.CONTRADICTION,
                                   actor=MODEL, linked_ids=(root.artifact_id,))
    assert conflict.conflict_id and sign.road_sign_id
    held = system.store.require_artifact(root.artifact_id)
    assert held.epistemic_status is EpistemicStatus.HISTORICAL_RECORD
    assert held.provenance_status is ProvenanceStatus.USER_ESTABLISHED
    assert _links_active(system, claim.artifact_id)


def test_a_machine_can_still_reclassify_its_own_records():
    system = CCCSystem()
    _root_artifact, claim = _root(system)
    system.classify(claim.artifact_id, EpistemicStatus.THEORY, actor=MODEL, reason="a lower status for its own claim")
    assert system.store.require_artifact(claim.artifact_id).epistemic_status is EpistemicStatus.THEORY


def test_with_a_verifier_a_humans_epistemic_demotion_asks_it_once_and_a_no_writes_nothing(tmp_path):
    plain = CCCSystem()
    root, claim = _root(plain)
    yes = Verifier(True)
    CCCSystem(store=plain.store, human_verifier=yes).classify(
        root.artifact_id, EpistemicStatus.THEORY, actor=HUMAN, reason="I was wrong")
    assert [r.operation for r in yes.requests] == ["classify"]

    plain = CCCSystem()
    root, claim = _root(plain)
    before = plain.store.save(tmp_path / "before.json").read_bytes()
    with pytest.raises(HumanVerificationRefused):
        CCCSystem(store=plain.store, human_verifier=Verifier(False)).classify(
            root.artifact_id, EpistemicStatus.THEORY, actor=HUMAN, reason="I was wrong")
    assert plain.store.save(tmp_path / "after.json").read_bytes() == before


def test_with_a_verifier_a_humans_provenance_demotion_asks_it_once_and_a_no_writes_nothing(tmp_path):
    plain = CCCSystem()
    root, claim = _root(plain)
    yes = Verifier(True)
    CCCSystem(store=plain.store, human_verifier=yes).provenance.resolve(
        root.artifact_id, actor=HUMAN, status=ProvenanceStatus.UNRESOLVED, reason="doubt", authorization_basis=BASIS)
    assert [r.operation for r in yes.requests] == ["transition_provenance"]
    assert yes.requests[0].actor_id == "william" and yes.requests[0].target_ids == (root.artifact_id,)

    plain = CCCSystem()
    root, claim = _root(plain)
    before = plain.store.save(tmp_path / "before.json").read_bytes()
    with pytest.raises(HumanVerificationRefused):
        CCCSystem(store=plain.store, human_verifier=Verifier(False)).provenance.resolve(
            root.artifact_id, actor=HUMAN, status=ProvenanceStatus.UNRESOLVED, reason="doubt",
            authorization_basis=BASIS)
    assert plain.store.save(tmp_path / "after.json").read_bytes() == before


def test_a_facade_call_that_moves_between_user_statuses_asks_the_verifier_once_not_twice():
    """establish_provenance on a USER_ACCEPTED record moves it off USER_ACCEPTED; the facade has asked, so the move
    beneath it does not ask again."""
    plain = CCCSystem()
    root, _claim = _root(plain)
    plain.accept(root.artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS)
    verifier = Verifier(True)
    CCCSystem(store=plain.store, human_verifier=verifier).establish_provenance(
        root.artifact_id, actor=HUMAN, reason="r", authorization_basis=BASIS)
    assert [r.operation for r in verifier.requests] == ["establish_provenance"]


def test_a_machine_demotion_is_refused_by_the_rule_even_when_the_verifier_would_say_yes():
    plain = CCCSystem()
    root, claim = _root(plain)
    system = CCCSystem(store=plain.store, human_verifier=lambda request: True)
    with pytest.raises(ConstitutionViolation):
        system.classify(root.artifact_id, EpistemicStatus.THEORY, actor=MODEL, reason="a model disagrees")
    assert _links_active(system, claim.artifact_id)
