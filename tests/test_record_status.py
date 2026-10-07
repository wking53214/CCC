"""CCC's answer to "do you hold this machine output?" (ccc.record_status).

Records are written here the way a machine handoff writes them
(triad42.ccc_handoff): model actor named after the source, with ``source`` and
``candidate_id`` in metadata. Triad is not imported; the contract is the
record's shape, and CCC must not depend on the Triad.
"""
from __future__ import annotations

from hashlib import sha256

import pytest

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.record_status import (
    ABSENT,
    ALTERED,
    ERASED,
    HELD,
    REDACTED,
    STATUSES,
    MachineRecords,
    record_status,
)

SOURCE = "triad42"
TEXT = "Red finding: the retry path never re-reads the lease."


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _record(system: CCCSystem, text: str = TEXT, *, candidate_id: str = "c1",
            actor: Actor | None = None, source: str = SOURCE):
    return system.ingest(
        text,
        actor=actor or Actor.model(SOURCE),
        epistemic_status=EpistemicStatus.INFERENCE,
        metadata={"source": source, "candidate_id": candidate_id},
    )


def _ask(system: CCCSystem, text: str = TEXT, candidate_id: str = "c1") -> str:
    return record_status(system, source=SOURCE, candidate_id=candidate_id, text_digest=_digest(text))


def test_recorded_output_is_held():
    system = CCCSystem()
    _record(system)
    assert _ask(system) == HELD


def test_nothing_recorded_is_absent():
    assert _ask(CCCSystem()) == ABSENT


def test_other_candidate_is_absent():
    system = CCCSystem()
    _record(system, candidate_id="c1")
    assert _ask(system, candidate_id="c2") == ABSENT


def test_changed_text_is_altered():
    system = CCCSystem()
    _record(system)
    assert _ask(system, text=TEXT + " (edited)") == ALTERED


def test_erased_record_is_erased_even_if_text_matches():
    system = CCCSystem()
    artifact = _record(system)
    system.erase(artifact.artifact_id, actor=Actor.human(), reason="withdrawn",
                 authorization_basis="owner request")
    assert _ask(system) == ERASED


def test_redacted_record_is_redacted():
    system = CCCSystem()
    artifact = _record(system)
    system.redact(artifact.artifact_id, actor=Actor.human(), reason="sensitive",
                  authorization_basis="owner request")
    assert _ask(system) == REDACTED


def test_erasure_wins_over_a_second_active_copy():
    system = CCCSystem()
    first = _record(system)
    _record(system)
    system.erase(first.artifact_id, actor=Actor.human(), reason="withdrawn",
                 authorization_basis="owner request")
    assert _ask(system) == ERASED


@pytest.mark.parametrize("actor", [Actor.human(SOURCE), Actor.model("other-model"),
                                   Actor.system(SOURCE), Actor.external(SOURCE)])
def test_look_alike_record_from_another_actor_does_not_count(actor):
    system = CCCSystem()
    _record(system, actor=actor)
    assert _ask(system) == ABSENT


def test_metadata_naming_another_source_does_not_count():
    system = CCCSystem()
    _record(system, source="someone-else")
    assert _ask(system) == ABSENT


def test_fingerprint_is_taken_from_stored_text_not_metadata():
    system = CCCSystem()
    system.ingest(TEXT, actor=Actor.model(SOURCE), metadata={
        "source": SOURCE, "candidate_id": "c1", "text_digest": _digest("something else")})
    assert _ask(system) == HELD
    assert _ask(system, text="something else") == ALTERED


def test_lookup_changes_nothing():
    system = CCCSystem()
    _record(system)
    audit_before = len(system.store.audit_events)
    artifacts_before = dict(system.store.artifacts)
    decisions_before = len(system.store.rule_decisions)
    _ask(system)
    _ask(system, candidate_id="missing")
    assert len(system.store.audit_events) == audit_before
    assert system.store.artifacts == artifacts_before
    assert len(system.store.rule_decisions) == decisions_before


@pytest.mark.parametrize("field", ["source", "candidate_id", "text_digest"])
@pytest.mark.parametrize("bad", ["", None, 7])
def test_malformed_question_raises_rather_than_answers(field, bad):
    kwargs = {"source": SOURCE, "candidate_id": "c1", "text_digest": _digest(TEXT)}
    kwargs[field] = bad
    with pytest.raises(ValueError):
        record_status(CCCSystem(), **kwargs)


def test_non_ccc_target_is_refused():
    with pytest.raises(TypeError):
        record_status(object(), source=SOURCE, candidate_id="c1", text_digest=_digest(TEXT))
    with pytest.raises(TypeError):
        MachineRecords(object())


def test_bound_lookup_gives_the_same_answers():
    system = CCCSystem()
    _record(system)
    records = MachineRecords(system)
    assert records.status(SOURCE, "c1", _digest(TEXT)) == HELD
    assert records.status(SOURCE, "c2", _digest(TEXT)) == ABSENT


def test_every_answer_is_listed():
    assert set(STATUSES) == {HELD, ABSENT, ALTERED, ERASED, REDACTED}
