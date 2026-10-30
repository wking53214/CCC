"""What CCC shows a consumer that checks the handoff's stamp itself (CNS-013), and the stamp formula pinned to the
rows CNS tests against. tests/handoff_stamp_vectors.json is a byte copy of CNS's contracts/handoff-stamp-vectors.json;
a change to the formula must change both, or one of the two suites goes red."""
from __future__ import annotations

import json
import pathlib
from hashlib import sha256

import pytest

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.record_status import MachineRecords, attest

VECTORS = json.loads((pathlib.Path(__file__).with_name("handoff_stamp_vectors.json")).read_text(encoding="utf-8"))
SOURCE = "triad42"
KEY = b"k" * 32
TEXT = "Red finding: the retry path never re-reads the lease."


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _record(system, text=TEXT, *, candidate_id="c1", stamp=True, source=SOURCE):
    metadata = {"source": source, "candidate_id": candidate_id}
    if stamp:
        metadata["attestation"] = attest(KEY, source=source, candidate_id=candidate_id, text_digest=_digest(text))
    return system.ingest(text, actor=Actor.model(source), epistemic_status=EpistemicStatus.INFERENCE,
                         metadata=metadata)


@pytest.mark.parametrize("row", VECTORS["vectors"], ids=lambda r: r["candidate_id"])
def test_attest_matches_the_rows_cns_tests_against(row):
    assert attest(bytes.fromhex(row["key_hex"]), source=row["source"], candidate_id=row["candidate_id"],
                  text_digest=row["text_digest"]) == row["stamp"]


def test_the_stamp_of_a_stamped_handoff_is_shown():
    system = CCCSystem()
    _record(system)
    (stamp,) = MachineRecords(system).stamps(SOURCE, "c1", _digest(TEXT))
    assert stamp == attest(KEY, source=SOURCE, candidate_id="c1", text_digest=_digest(TEXT))


def test_an_unstamped_record_shows_nothing():
    system = CCCSystem()
    _record(system, stamp=False)
    assert MachineRecords(system).stamps(SOURCE, "c1", _digest(TEXT)) == ()


@pytest.mark.parametrize("ask", [
    dict(candidate_id="c2", text=TEXT),
    dict(candidate_id="c1", text="other text"),
])
def test_only_the_records_of_exactly_this_item_are_shown(ask):
    system = CCCSystem()
    _record(system)
    assert MachineRecords(system).stamps(SOURCE, ask["candidate_id"], _digest(ask["text"])) == ()


def test_an_erased_record_shows_no_stamp():
    system = CCCSystem()
    artifact = _record(system)
    system.erase(artifact.artifact_id, actor=Actor.human(), reason="withdrawn", authorization_basis="owner request")
    assert MachineRecords(system).stamps(SOURCE, "c1", _digest(TEXT)) == ()


def test_another_sources_record_is_not_shown():
    system = CCCSystem()
    _record(system, source="other-model")
    assert MachineRecords(system).stamps(SOURCE, "c1", _digest(TEXT)) == ()


@pytest.mark.parametrize("field", ["source", "candidate_id", "text_digest"])
def test_a_malformed_question_raises(field):
    args = dict(source=SOURCE, candidate_id="c1", text_digest=_digest(TEXT))
    args[field] = ""
    with pytest.raises(ValueError):
        MachineRecords(CCCSystem()).stamps(**args)
