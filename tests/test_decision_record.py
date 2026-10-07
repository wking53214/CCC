"""How a decision was reached: options, disposition of each, assumptions.

`CCCSystem.decide` optionally records the shape of the decision records in
decisions/ (options considered, the one selected, each other option rejected
with a reason or deferred, and the assumptions it rests on). Carried over from
innovation_os's decision records ahead of that repository's retirement.
"""

from __future__ import annotations

import pytest

from ccc import Actor, CCCSystem
from ccc.errors import ConstitutionViolation

HUMAN = Actor.human("william")
BASIS = "explicit human decision"


def _decide(system: CCCSystem, **how):
    return system.decide("split disposition", actor=HUMAN, reason="DEC-0002", authorization_basis=BASIS, **how)


def test_a_plain_decision_is_recorded_exactly_as_before():
    decision = _decide(CCCSystem())
    assert set(decision.metadata) == {"decision", "recommendation_id"}


def test_full_record_is_stored_with_the_decision_and_in_the_audit():
    system = CCCSystem()
    decision = _decide(
        system,
        options=("all-or-nothing", "split", "leave open"),
        selected_option="split",
        rejected={"all-or-nothing": "would discard tested code over one provision"},
        deferred=("leave open",),
        assumptions=("the six-category taxonomy stays closed",),
    )
    meta = decision.metadata
    assert meta["options"] == ("all-or-nothing", "split", "leave open")
    assert meta["selected_option"] == "split"
    assert meta["rejected"] == (("all-or-nothing", "would discard tested code over one provision"),)
    assert meta["deferred"] == ("leave open",)
    assert meta["assumptions"] == ("the six-category taxonomy stays closed",)
    entry = [e for e in system.audit_trail.all() if e.operation == "DECIDE"][-1]
    assert entry.new_state["selected_option"] == "split"
    assert entry.new_state["deferred"] == ("leave open",)


def test_assumptions_alone_are_allowed():
    decision = _decide(CCCSystem(), assumptions=("traffic stays below 10k calls a day",))
    assert decision.metadata["assumptions"] == ("traffic stays below 10k calls a day",)
    assert "options" not in decision.metadata


def test_an_option_dismissed_without_a_disposition_is_refused():
    with pytest.raises(ValueError, match="needs a disposition"):
        _decide(CCCSystem(), options=("a", "b", "c"), selected_option="a", rejected={"b": "too slow"})


def test_deferred_is_not_rejection_and_counts_as_a_disposition():
    decision = _decide(CCCSystem(), options=("a", "b"), selected_option="a", deferred=("b",))
    assert decision.metadata["rejected"] == ()
    assert decision.metadata["deferred"] == ("b",)


@pytest.mark.parametrize("how,match", [
    ({"options": ("a", "b"), "selected_option": "c", "rejected": {"b": "x"}}, "one of the options"),
    ({"options": ("a", "b"), "rejected": {"b": "x"}}, "one of the options"),
    ({"options": ("a", "b"), "selected_option": "a", "rejected": {"z": "x"}, "deferred": ("b",)}, "among the options"),
    ({"options": ("a", "b"), "selected_option": "a", "rejected": {"a": "x"}, "deferred": ("b",)}, "cannot also be"),
    ({"options": ("a", "b"), "selected_option": "a", "rejected": {"b": "x"}, "deferred": ("b",)}, "not both"),
    ({"options": ("a", "b"), "selected_option": "a", "rejected": {"b": " "}}, "non-empty reason"),
    ({"selected_option": "a"}, "need the options"),
    ({"deferred": ("b",)}, "need the options"),
    ({"options": ("a", "a"), "selected_option": "a"}, "may not repeat"),
    ({"options": "ab", "selected_option": "a"}, "not a string"),
    ({"assumptions": ("",)}, "non-empty strings"),
])
def test_incomplete_or_contradictory_records_are_refused(how, match):
    with pytest.raises(ValueError, match=match):
        _decide(CCCSystem(), **how)


def test_a_refused_record_writes_nothing():
    system = CCCSystem()
    before = len(system.store.artifacts)
    with pytest.raises(ValueError):
        _decide(system, options=("a", "b"), selected_option="a")
    assert len(system.store.artifacts) == before
    assert not [e for e in system.audit_trail.all() if e.operation == "DECIDE"]


def test_a_model_still_cannot_decide_even_with_a_full_record():
    with pytest.raises(ConstitutionViolation):
        CCCSystem().decide("x", actor=Actor.model("m"), reason="r", authorization_basis="model",
                           options=("a", "b"), selected_option="a", deferred=("b",))


def test_the_record_survives_save_and_reopen(tmp_path):
    path = tmp_path / "ccc.json"
    system = CCCSystem(persistence_path=path)
    decision = _decide(system, options=("a", "b"), selected_option="a",
                       rejected={"b": "costs more"}, assumptions=("budget fixed",))
    system.save()
    reopened = CCCSystem(persistence_path=path).store.require_artifact(decision.artifact_id).metadata
    assert reopened["selected_option"] == "a"
    assert [list(pair) for pair in reopened["rejected"]] == [["b", "costs more"]]
    assert list(reopened["assumptions"]) == ["budget fixed"]
