"""CCCSystem(persistence_path=p) should resume from p if p holds a prior
state -- not silently start empty and require CCCStore.load(p) +
CCCSystem(store=...) as two separate steps (which is easy to get wrong;
it was gotten wrong the first time it was used for real).
"""
from __future__ import annotations

from ccc import Actor, CCCSystem, EpistemicStatus


def test_fresh_path_starts_empty(tmp_path):
    system = CCCSystem(persistence_path=tmp_path / "state.json")
    assert len(system.store.artifacts) == 0


def test_save_then_reopen_the_same_path_resumes_the_state(tmp_path):
    path = tmp_path / "state.json"

    first = CCCSystem(persistence_path=path)
    art = first.ingest(
        "a fact worth remembering across sessions",
        actor=Actor.human("william"),
        epistemic_status=EpistemicStatus.INTERPRETATION,
    )
    first.save()

    # one line, no CCCStore.load() dance
    second = CCCSystem(persistence_path=path)
    assert art.artifact_id in second.store.artifacts
    assert second.store.artifacts[art.artifact_id].content == "a fact worth remembering across sessions"


def test_dialogue_conclusion_survives_a_reopen(tmp_path):
    """The exact scenario from the GSA dialogue: ask() a round, save, come
    back in a fresh process, resolve it -- now one line to reopen."""
    path = tmp_path / "dlg.json"

    s1 = CCCSystem(persistence_path=path)
    rec = s1.human_resolution.ask(
        context="c", question="which?", candidates=("A", "B"), actor=Actor.model("m"),
    )
    s1.save()

    s2 = CCCSystem(persistence_path=path)
    resolved = s2.human_resolution.resolve(
        rec.uncertainty_id, choice="A", actor=Actor.human("william"),
        reason="resumed and resolved", authorization_basis="explicit",
    )
    assert resolved.resolved_choice == "A"
    assert resolved.resolved_by.kind.value == "HUMAN"


def test_empty_file_is_treated_as_fresh_not_a_corrupt_json_error(tmp_path):
    path = tmp_path / "empty.json"
    path.touch()  # 0 bytes
    system = CCCSystem(persistence_path=path)  # must not raise
    assert len(system.store.artifacts) == 0


def test_explicit_store_still_wins_over_persistence_path(tmp_path):
    path = tmp_path / "state.json"
    seeded = CCCSystem(persistence_path=path)
    seeded.ingest("seeded", actor=Actor.human("w"), epistemic_status=EpistemicStatus.INTERPRETATION)
    seeded.save()

    from ccc.store import CCCStore
    explicit = CCCStore()  # deliberately empty
    system = CCCSystem(store=explicit, persistence_path=path)
    assert len(system.store.artifacts) == 0  # explicit store used, path ignored for loading
