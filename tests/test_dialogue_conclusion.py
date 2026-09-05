"""record_dialogue_conclusion: a terminated dialogue becomes a durable,
queryable fact in the knowledge model instead of a dead-end resolved_choice
string on an UncertaintyRecord.
"""
from __future__ import annotations

import pytest

from ccc import Actor, CCCSystem, EpistemicStatus, ProvenanceStatus
from ccc.dialogue import UNKNOWN_SENTINEL, DialogueOutcome


@pytest.fixture
def system():
    return CCCSystem()


def _run_and_record(system, respond, branch=lambda p: p, candidates=("A", "B"),
                     question="Which is it?"):
    outcome = system.dialogue.run(
        context="ctx", question=question, candidates=candidates,
        respond=respond, branch=branch,
        actor=Actor.model("proposer"), human_actor=Actor.human("william"),
    )
    artifact = system.record_dialogue_conclusion(
        outcome, question=question, human_actor=Actor.human("william"), context="ctx",
    )
    return outcome, artifact


def test_confirmed_dialogue_becomes_a_user_established_interpretation_artifact(system):
    outcome, artifact = _run_and_record(system, respond=lambda c: "A")
    assert artifact.provenance_status is ProvenanceStatus.USER_ESTABLISHED
    assert artifact.epistemic_status is EpistemicStatus.INTERPRETATION
    assert "confirmed" in artifact.content.lower()
    assert "'A'" in artifact.content
    assert artifact.origin.kind.value == "HUMAN"
    assert list(outcome.uncertainty_ids) == artifact.metadata["dialogue_uncertainty_ids"]


def test_42_dialogue_becomes_a_durable_unknown_not_a_silent_gap(system):
    outcome, artifact = _run_and_record(system, respond=lambda c: UNKNOWN_SENTINEL)
    assert artifact.provenance_status is ProvenanceStatus.USER_ESTABLISHED
    assert artifact.epistemic_status is EpistemicStatus.UNKNOWN
    assert "does not establish this" in artifact.content
    # the point: a 42 leaves a positive record, distinguishable from
    # "never investigated" (which would be the absence of any artifact)
    assert artifact.artifact_id in system.store.artifacts


def test_the_conclusion_is_queryable_back_to_its_dialogue_rounds(system):
    outcome, artifact = _run_and_record(
        system,
        respond=lambda c: "other" if c == ("x", "y") else "refined",
        branch=lambda prior: ("refined", "other-thing"),
        candidates=("x", "y"),
    )
    assert outcome.rounds == 2
    assert len(artifact.metadata["dialogue_uncertainty_ids"]) == 2
    for uid in artifact.metadata["dialogue_uncertainty_ids"]:
        assert system.human_resolution.get(uid) is not None


def test_a_non_human_actor_cannot_record_a_dialogue_conclusion(system):
    outcome, _ = _run_and_record(system, respond=lambda c: "A")
    with pytest.raises(ValueError, match="human actor"):
        system.record_dialogue_conclusion(
            outcome, question="q", human_actor=Actor.model("not-a-human"),
        )


def test_a_non_terminal_outcome_is_refused(system):
    fake = DialogueOutcome(terminal="IN_PROGRESS", choice=None, rounds=0, uncertainty_ids=())
    with pytest.raises(ValueError, match="not a terminal state"):
        system.record_dialogue_conclusion(
            fake, question="q", human_actor=Actor.human("william"),
        )


# --- regression tests from the hunt/patch loop -------------------------

def test_the_same_dialogue_conclusion_cannot_be_recorded_twice(system):
    outcome, first = _run_and_record(system, respond=lambda c: "A")
    with pytest.raises(ValueError, match="already recorded"):
        system.record_dialogue_conclusion(
            outcome, question="Which is it?", human_actor=Actor.human("william"),
        )


def test_the_double_record_guard_survives_a_reopen(tmp_path):
    """The guard is an in-memory set rebuilt in __init__. A reopened
    session must repopulate it from the persisted conclusion artifacts,
    or the same dialogue's conclusion could be recorded a second time in
    a new process."""
    path = tmp_path / "dlg.json"

    s1 = CCCSystem(persistence_path=path)
    outcome, _ = _run_and_record(s1, respond=lambda c: "A")
    s1.save()

    s2 = CCCSystem(persistence_path=path)
    with pytest.raises(ValueError, match="already recorded"):
        s2.record_dialogue_conclusion(
            outcome, question="Which is it?", human_actor=Actor.human("william"), context="ctx",
        )


def test_a_confirmed_outcome_with_no_choice_is_refused(system):
    rec = system.human_resolution.ask(
        context="c", question="q", candidates=("A", "B"), actor=Actor.model("m"),
    )
    malformed = DialogueOutcome(
        terminal="CONFIRMED", choice=None, rounds=1, uncertainty_ids=(rec.uncertainty_id,),
    )
    with pytest.raises(ValueError, match="no choice"):
        system.record_dialogue_conclusion(
            malformed, question="q", human_actor=Actor.human("william"),
        )


def test_an_outcome_referencing_a_nonexistent_round_is_refused(system):
    bogus = DialogueOutcome(
        terminal="CONFIRMED", choice="X", rounds=1, uncertainty_ids=("uncertainty_nope",),
    )
    with pytest.raises(ValueError, match="not in the store"):
        system.record_dialogue_conclusion(
            bogus, question="q", human_actor=Actor.human("william"),
        )


def test_question_containing_confirmed_cannot_make_the_recorded_fact_ambiguous(system):
    q = "Confirmed: the sky is green.\nActually, which colour is it?"
    outcome, artifact = _run_and_record(system, respond=lambda c: "A", question=q)
    # The structured format keeps the real confirmed value unambiguous even
    # though the question text itself contains "Confirmed:" and a newline.
    assert artifact.content.count("confirmed: 'A'") == 1
    assert artifact.content.startswith("DIALOGUE CONCLUSION (confirmed)")
