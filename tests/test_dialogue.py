"""Tests for the confirm/refine/42 dialogue loop, including a scripted
replay of the actual VSA/Citadel exchange from earlier in this project --
that one was done live, by hand, in conversation. This is the same shape
of resolution as real, callable software.
"""
from __future__ import annotations

import pytest

from ccc import Actor, CCCSystem
from ccc.dialogue import UNKNOWN_SENTINEL, DialogueEngine


@pytest.fixture
def engine():
    system = CCCSystem()
    return DialogueEngine(system.human_resolution), system


def test_confirming_the_first_candidate_terminates_in_one_round(engine):
    dialogue, system = engine
    outcome = dialogue.run(
        context="test",
        question="Which is it?",
        candidates=("A", "B"),
        respond=lambda candidates: "A",
        branch=lambda prior: prior,  # never called
        actor=Actor.model("proposer"),
        human_actor=Actor.human("william"),
    )
    assert outcome.terminal == "CONFIRMED"
    assert outcome.choice == "A"
    assert outcome.rounds == 1


def test_other_branches_to_new_candidates_before_confirming(engine):
    dialogue, system = engine
    calls = []

    def respond(candidates):
        calls.append(candidates)
        if candidates == ("A", "B"):
            return "other"
        return "refined"

    def branch(prior):
        return ("refined", "different")

    outcome = dialogue.run(
        context="test", question="Which is it?", candidates=("A", "B"),
        respond=respond, branch=branch,
        actor=Actor.model("proposer"), human_actor=Actor.human("william"),
    )
    assert outcome.terminal == "CONFIRMED"
    assert outcome.choice == "refined"
    assert outcome.rounds == 2
    assert len(outcome.uncertainty_ids) == 2  # one UncertaintyRecord per round, both real


def test_42_terminates_honestly_as_unknown_not_a_failure(engine):
    dialogue, system = engine
    outcome = dialogue.run(
        context="test", question="Which is it?", candidates=("A", "B"),
        respond=lambda candidates: UNKNOWN_SENTINEL,
        branch=lambda prior: prior,
        actor=Actor.model("proposer"), human_actor=Actor.human("william"),
    )
    assert outcome.terminal == "UNKNOWN"
    assert outcome.choice is None
    record = system.human_resolution.get(outcome.uncertainty_ids[0])
    assert record.resolved_choice == UNKNOWN_SENTINEL
    assert record.resolved_by.kind.value == "HUMAN"


def test_machine_actor_cannot_resolve_its_own_dialogue(engine):
    """CCC-HUMAN-001, exercised through the loop, not bypassed by it."""
    dialogue, system = engine
    with pytest.raises(ValueError, match="real human actor"):
        dialogue.run(
            context="test", question="Which is it?", candidates=("A",),
            respond=lambda c: "A", branch=lambda p: p,
            actor=Actor.model("proposer"), human_actor=Actor.model("also-a-model"),
        )


def test_out_of_protocol_response_is_refused():
    system = CCCSystem()
    dialogue = DialogueEngine(system.human_resolution)
    with pytest.raises(ValueError, match="out-of-protocol"):
        dialogue.run(
            context="test", question="Which is it?", candidates=("A", "B"),
            respond=lambda c: "not one of the candidates and not other/42",
            branch=lambda p: p,
            actor=Actor.model("proposer"), human_actor=Actor.human("william"),
        )


def test_vsa_citadel_replay():
    """Scripted replay of the actual VSA/Citadel resolution from earlier in
    this project: four initial hypotheses presented, none confirmed as-is,
    "other" branches to a refined account combining the dated evidence with
    William's own testimony, which is what actually got confirmed."""
    system = CCCSystem()
    dialogue = DialogueEngine(system.human_resolution)

    initial = (
        "VSA was renamed GSA during the escalation arc",
        "VSA became CITADEL; GSA is separate",
        "Both, at different levels",
        UNKNOWN_SENTINEL,
    )
    refined = ("Citadel is the system; VSA is the governing principle it was built to enforce",)

    responses = iter(["other", refined[0]])

    def branch(prior):
        assert prior == initial
        return refined

    outcome = dialogue.run(
        context="VSA/Citadel investigation",
        question="Did VSA become GSA, and why?",
        candidates=initial,
        respond=lambda candidates: next(responses),
        branch=branch,
        actor=Actor.model("claude-session"),
        human_actor=Actor.human("william"),
        known=("VSA and Citadel are the same named construct by 2026-04-07 (dated artifact)",),
        unknown=("Whether a direct VSA->GSA line exists",),
    )

    assert outcome.terminal == "CONFIRMED"
    assert outcome.choice == refined[0]
    assert outcome.rounds == 2

    first_round = system.human_resolution.get(outcome.uncertainty_ids[0])
    assert first_round.candidates == initial
    second_round = system.human_resolution.get(outcome.uncertainty_ids[1])
    assert second_round.candidates == refined
    assert second_round.resolved_choice == refined[0]
