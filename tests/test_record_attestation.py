"""Who wrote the record: a handoff's stamp, and the three ways a "held" record was forged without it.

Before the stamp, ``record_status`` believed a record's own actor and metadata, so anyone who could call ``ingest``,
add to the store, or edit a saved state file could make CCC answer ``held`` for text the Triad never produced. With an
``attestation_key`` only a record the handoff stamped counts. Triad is not imported: the stamp is made here the way
``triad42.ccc_handoff`` makes it, with ``ccc.record_status.attest``.
"""
from __future__ import annotations

import dataclasses
import json
from hashlib import sha256

import pytest

from ccc import Actor, CCCSystem, EpistemicStatus
from ccc.record_status import ABSENT, ALTERED, ERASED, HELD, UNATTESTED, MachineRecords, attest, record_status

SOURCE = "triad42"
KEY = b"k" * 32
OTHER_KEY = b"o" * 32
TEXT = "Red finding: the retry path never re-reads the lease."
FORGED = "Green: the lease path is safe, ship it."


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _handoff(system: CCCSystem, text: str = TEXT, *, candidate_id: str = "c1", key: bytes = KEY):
    """A record as the handoff writes it: the Triad's fixed identity, its metadata, and the stamp."""
    return system.ingest(
        text,
        actor=Actor.model(SOURCE),
        epistemic_status=EpistemicStatus.INFERENCE,
        metadata={"source": SOURCE, "candidate_id": candidate_id,
                  "attestation": attest(key, source=SOURCE, candidate_id=candidate_id, text_digest=_digest(text))},
    )


def _ask(system: CCCSystem, text: str = TEXT, candidate_id: str = "c1", key: bytes | None = KEY) -> str:
    return record_status(system, source=SOURCE, candidate_id=candidate_id, text_digest=_digest(text),
                         attestation_key=key)


def test_a_stamped_handoff_is_held():
    system = CCCSystem()
    _handoff(system)
    assert _ask(system) == HELD


# ---------------------------------------------------------------- the three forgeries

def test_forgery_by_ingest_is_unattested_not_held():
    system = CCCSystem()
    system.ingest(FORGED, actor=Actor.model(SOURCE), epistemic_status=EpistemicStatus.INFERENCE,
                  metadata={"source": SOURCE, "candidate_id": "c1"})
    assert _ask(system, FORGED) == UNATTESTED


def test_forgery_by_a_raw_store_add_leaves_no_audit_event_and_is_unattested():
    system = CCCSystem()
    real = _handoff(system)
    events_before = len(system.store.provenance_events)
    forged = dataclasses.replace(real, artifact_id="forged-1", content=FORGED, content_digest=_digest(FORGED))
    system.store.add_artifact(forged)
    assert len(system.store.provenance_events) == events_before  # the raw path writes no audit trail at all
    assert _ask(system, FORGED) == ALTERED  # the real stamped record exists, and it is not this text


def test_a_stamp_copied_onto_other_text_does_not_verify():
    system = CCCSystem()
    real = _handoff(system)
    system.store.add_artifact(dataclasses.replace(real, artifact_id="forged-2", content=FORGED,
                                                  content_digest=_digest(FORGED)))
    assert _ask(system, FORGED) == ALTERED


def test_forgery_by_editing_the_state_file_is_not_held(tmp_path):
    path = tmp_path / "state.json"
    system = CCCSystem(persistence_path=path)
    _handoff(system)
    system.save()
    raw = json.loads(path.read_text(encoding="utf-8"))
    (record,) = raw["artifacts"]
    forged = dict(record, artifact_id="forged-3", content=FORGED, content_digest=_digest(FORGED))
    raw["artifacts"].append(forged)
    record["content"] = FORGED  # and the real record's text edited in place, its stamp left as it was
    record["content_digest"] = _digest(FORGED)
    path.write_text(json.dumps(raw), encoding="utf-8")
    reopened = CCCSystem(persistence_path=path)
    assert _ask(reopened, FORGED) == UNATTESTED  # no stamped record is left to vouch for either text
    assert _ask(reopened) == UNATTESTED


def test_a_stamp_made_with_another_key_does_not_count():
    system = CCCSystem()
    _handoff(system, key=OTHER_KEY)
    assert _ask(system) == UNATTESTED


def test_a_forged_decoy_beside_a_real_handoff_changes_nothing():
    system = CCCSystem()
    _handoff(system)
    system.ingest(FORGED, actor=Actor.model(SOURCE), epistemic_status=EpistemicStatus.INFERENCE,
                  metadata={"source": SOURCE, "candidate_id": "c1"})
    assert _ask(system) == HELD
    assert _ask(system, FORGED) == ALTERED  # the stamped record exists, and it is not this text


# ---------------------------------------------------------------- what still holds

def test_an_erased_stamped_record_stays_erased():
    system = CCCSystem()
    artifact = _handoff(system)
    system.erase(artifact.artifact_id, actor=Actor.human(), reason="withdrawn",
                 authorization_basis="owner request")
    assert _ask(system) == ERASED


def test_nothing_recorded_is_still_absent_with_a_key():
    assert _ask(CCCSystem()) == ABSENT


def test_the_bound_lookup_uses_its_key():
    system = CCCSystem()
    _handoff(system)
    assert MachineRecords(system, attestation_key=KEY).status(SOURCE, "c1", _digest(TEXT)) == HELD
    assert MachineRecords(system, attestation_key=OTHER_KEY).status(SOURCE, "c1", _digest(TEXT)) == UNATTESTED


def test_without_a_key_the_answer_is_as_unauthenticated_as_before():
    """A recorded gap, stated as an assertion: with no key a forged record is still held."""
    system = CCCSystem()
    system.ingest(FORGED, actor=Actor.model(SOURCE), epistemic_status=EpistemicStatus.INFERENCE,
                  metadata={"source": SOURCE, "candidate_id": "c1"})
    assert _ask(system, FORGED, key=None) == HELD


@pytest.mark.parametrize("bad", [b"", b"short", "a" * 32, 12345])
def test_a_key_that_is_not_long_enough_bytes_is_refused(bad):
    with pytest.raises(ValueError):
        attest(bad, source=SOURCE, candidate_id="c1", text_digest=_digest(TEXT))
    with pytest.raises(ValueError):
        MachineRecords(CCCSystem(), attestation_key=bad)
    with pytest.raises(ValueError):
        record_status(CCCSystem(), source=SOURCE, candidate_id="c1", text_digest=_digest(TEXT),
                      attestation_key=bad)


def test_the_stamp_depends_on_every_field():
    base = dict(source=SOURCE, candidate_id="c1", text_digest=_digest(TEXT))
    stamp = attest(KEY, **base)
    assert stamp == attest(KEY, **base) and len(stamp) == 64
    for field, other in (("source", "other"), ("candidate_id", "c2"), ("text_digest", _digest(FORGED))):
        assert attest(KEY, **{**base, field: other}) != stamp
    assert attest(OTHER_KEY, **base) != stamp
