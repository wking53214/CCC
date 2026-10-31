"""A reloaded system keeps the guards it is given.

Neither the write permission nor the human verifier is saved with the store, so a system reloaded from disk has none
unless ``CCCSystem.load`` is given them again. ``load`` takes both, and a reloaded guarded system refuses what the
original refused. With neither given, the loaded system is unguarded, as before. None of these tests needs CNS and
none skips.
"""

from __future__ import annotations

import pytest

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.errors import HumanVerificationRefused, WritePermissionRefused

HUMAN = Actor.human("william")
MODEL = Actor.model("model")
BASIS = "explicit human decision"


def _saved(tmp_path):
    system = CCCSystem()
    fact = system.ingest("a human fact", actor=HUMAN, epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
                         authorization_basis=BASIS)
    return system.save(tmp_path / "state.json"), fact


def test_load_takes_the_write_permission_and_the_human_verifier_and_the_reloaded_system_refuses(tmp_path):
    path, fact = _saved(tmp_path)
    reloaded = CCCSystem.load(path, write_permission=lambda request: False, human_verifier=lambda request: False)
    before = (len(reloaded.store.artifacts), len(reloaded.store.lineage_events))
    with pytest.raises(WritePermissionRefused):
        reloaded.ingest("a machine write", actor=MODEL)
    with pytest.raises(WritePermissionRefused):
        reloaded.relate(fact.artifact_id, fact.artifact_id, __import__("ccc").RelationshipType.RELATED_TO,
                        actor=MODEL, reason="r")
    with pytest.raises(HumanVerificationRefused):
        reloaded.decide("let it ship", actor=Actor.human("anyone"), reason="r", authorization_basis=BASIS)
    with pytest.raises(HumanVerificationRefused):
        reloaded.supersede(fact.artifact_id, content="replaced", actor=HUMAN, reason="r", authorization_basis=BASIS)
    assert (len(reloaded.store.artifacts), len(reloaded.store.lineage_events)) == before


def test_a_reloaded_system_is_guarded_by_the_verifier_alone_and_by_the_permission_alone(tmp_path):
    path, fact = _saved(tmp_path)
    only_verifier = CCCSystem.load(path, human_verifier=lambda request: False)
    assert only_verifier.ingest("machine writes are not this guard's business", actor=MODEL)
    with pytest.raises(HumanVerificationRefused):
        only_verifier.decide("d", actor=HUMAN, reason="r", authorization_basis=BASIS)
    only_permission = CCCSystem.load(path, write_permission=lambda request: False)
    assert only_permission.decide("human acts are not this guard's business", actor=HUMAN, reason="r",
                                  authorization_basis=BASIS)
    with pytest.raises(WritePermissionRefused):
        only_permission.ingest("x", actor=MODEL)


def test_a_yes_from_both_lets_a_reloaded_system_write(tmp_path):
    path, _fact = _saved(tmp_path)
    reloaded = CCCSystem.load(path, write_permission=lambda request: True, human_verifier=lambda request: True)
    assert reloaded.ingest("a machine write", actor=MODEL)
    assert reloaded.decide("a human decision", actor=HUMAN, reason="r", authorization_basis=BASIS)


def test_with_neither_given_the_loaded_system_is_unguarded_as_before(tmp_path):
    path, fact = _saved(tmp_path)
    reloaded = CCCSystem.load(path)
    assert reloaded.ingest("a machine write", actor=MODEL)
    assert reloaded.decide("a human decision", actor=HUMAN, reason="r", authorization_basis=BASIS)


def test_the_guards_are_not_saved_so_saving_a_guarded_system_and_loading_plainly_drops_them(tmp_path):
    guarded = CCCSystem(write_permission=lambda request: False, human_verifier=lambda request: False)
    path = guarded.save(tmp_path / "guarded.json")
    plain = CCCSystem.load(path)
    assert plain.ingest("unguarded after a plain load", actor=MODEL)


def test_a_persistence_path_system_takes_the_guards_when_it_resumes(tmp_path):
    path, _fact = _saved(tmp_path)
    resumed = CCCSystem(persistence_path=path, write_permission=lambda request: False,
                        human_verifier=lambda request: False)
    assert len(resumed.store.artifacts) == 1  # it resumed the saved state, and kept the guards
    with pytest.raises(WritePermissionRefused):
        resumed.ingest("x", actor=MODEL)
    with pytest.raises(HumanVerificationRefused):
        resumed.decide("d", actor=HUMAN, reason="r", authorization_basis=BASIS)


def test_load_rejects_a_guard_that_is_not_callable(tmp_path):
    path, _fact = _saved(tmp_path)
    with pytest.raises(TypeError):
        CCCSystem.load(path, human_verifier="yes")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        CCCSystem.load(path, write_permission="yes")  # type: ignore[arg-type]
