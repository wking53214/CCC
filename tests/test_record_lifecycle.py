"""What a human did to a record holds whatever id the text comes back under (ccc.record_status, CCC-002).

Erasure used to be matched by candidate id only, so the same text handed in again under a new id answered ``held``;
and a record a human rejected, or one replaced by a successor, still answered ``held``. Records are written the way
a machine handoff writes them (triad42.ccc_handoff); Triad is not imported.
"""
from __future__ import annotations

from hashlib import sha256

import pytest

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.record_status import (
    ABSENT, ERASED, HELD, REDACTED, REJECTED, SUPERSEDED, attest, record_status,
)

SOURCE = "triad42"
TEXT = "Red finding: the retry path never re-reads the lease."
OTHER = "Amber: the lease timeout is not configurable."
KEY = b"k" * 32
HUMAN = dict(actor=Actor.human(), reason="reviewed", authorization_basis="owner request")


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _record(system: CCCSystem, text: str = TEXT, *, candidate_id: str = "c1", source: str = SOURCE, key=None):
    metadata = {"source": source, "candidate_id": candidate_id}
    if key is not None:
        metadata["attestation"] = attest(key, source=source, candidate_id=candidate_id, text_digest=_digest(text))
    return system.ingest(text, actor=Actor.model(source), epistemic_status=EpistemicStatus.THEORY,
                         metadata=metadata)


def _ask(system, text=TEXT, candidate_id="c1", key=None):
    return record_status(system, source=SOURCE, candidate_id=candidate_id, text_digest=_digest(text),
                         attestation_key=key)


# ---------------------------------------------------------------- removal follows the text, not the id

@pytest.mark.parametrize("remove,answer", [("erase", ERASED), ("redact", REDACTED)])
def test_removed_text_handed_in_again_under_a_new_id_stays_removed(remove, answer):
    system = CCCSystem()
    original = _record(system, candidate_id="c1")
    getattr(system, remove)(original.artifact_id, **HUMAN)
    _record(system, candidate_id="c2")  # the same text, a new id
    assert _ask(system, candidate_id="c2") == answer


def test_removal_of_one_text_does_not_touch_a_different_text_under_another_id():
    system = CCCSystem()
    system.erase(_record(system, candidate_id="c1").artifact_id, **HUMAN)
    _record(system, OTHER, candidate_id="c2")
    assert _ask(system, OTHER, candidate_id="c2") == HELD


def test_a_removed_record_from_another_source_does_not_block_this_one():
    system = CCCSystem()
    system.erase(_record(system, source="other-model", candidate_id="x1").artifact_id, **HUMAN)
    _record(system, candidate_id="c1")
    assert _ask(system) == HELD


def test_removal_still_wins_when_the_caller_checks_stamps():
    system = CCCSystem()
    system.erase(_record(system, candidate_id="c1", key=KEY).artifact_id, **HUMAN)
    _record(system, candidate_id="c2", key=KEY)
    assert _ask(system, candidate_id="c2", key=KEY) == ERASED


# ---------------------------------------------------------------- rejected and superseded are not held

def test_a_rejected_record_is_rejected_not_held():
    system = CCCSystem()
    system.reject(_record(system).artifact_id, **HUMAN)
    assert _ask(system) == REJECTED


def test_rejected_text_under_a_new_id_is_still_rejected():
    system = CCCSystem()
    system.reject(_record(system, candidate_id="c1").artifact_id, **HUMAN)
    _record(system, candidate_id="c2")
    assert _ask(system, candidate_id="c2") == REJECTED


def test_a_superseded_record_is_superseded_not_held():
    system = CCCSystem()
    system.supersede(_record(system).artifact_id, content="The corrected finding.", **HUMAN)
    assert _ask(system) == SUPERSEDED


def test_superseded_text_under_a_new_id_is_still_superseded():
    system = CCCSystem()
    system.supersede(_record(system, candidate_id="c1").artifact_id, content="The corrected finding.", **HUMAN)
    _record(system, candidate_id="c2")
    assert _ask(system, candidate_id="c2") == SUPERSEDED


def test_an_untouched_record_is_still_held_and_an_unknown_one_still_absent():
    system = CCCSystem()
    _record(system)
    assert _ask(system) == HELD
    assert _ask(system, OTHER, candidate_id="c9") == ABSENT
