"""A removed record whose fingerprint cannot be used to confirm a guess at its text (A16).

An erased record kept the plain SHA-256 of its text, so anyone holding the store or the saved file could confirm a
guess at erased text by hashing it. With a ``tombstone_key`` (the caller's) an erased or redacted record keeps a keyed
fingerprint instead, in ``content_digest`` and in a ``text_digest`` it carries, and ``record_status`` still finds the
same text under any id (CCC-002) because it computes the same keyed form.
"""
from __future__ import annotations

from hashlib import sha256

import pytest

from ccc import Actor, CCCSystem
from ccc.errors import UnguardedSystemError
from ccc.models import TOMBSTONE_PREFIX
from ccc.store import CCCStore
from ccc.record_status import ERASED, HELD, REDACTED, record_status

KEY = b"t" * 32
OPEN = dict(allow_unguarded_writes=True, allow_unverified_humans=True)
SOURCE = "triad42"
TEXT = "The supplier's bank account changed on 3 March."
HUMAN = dict(actor=Actor.human(), reason="withdrawn", authorization_basis="owner request")


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _record(system, text=TEXT, candidate_id="c1"):
    return system.ingest(text, actor=Actor.model(SOURCE),
                         metadata={"source": SOURCE, "candidate_id": candidate_id, "text_digest": _digest(text)})


def _ask(system, candidate_id, text=TEXT):
    return record_status(system, source=SOURCE, candidate_id=candidate_id, text_digest=_digest(text))


def _removed_and_saved(tmp_path, key, remove="erase"):
    path = tmp_path / "state.json"
    system = CCCSystem(persistence_path=path, tombstone_key=key, **OPEN)
    getattr(system, remove)(_record(system).artifact_id, **HUMAN)
    system.save()
    return path, system


@pytest.mark.parametrize("remove", ["erase", "redact"])
def test_with_a_key_a_guess_at_removed_text_cannot_be_confirmed_from_the_saved_file(tmp_path, remove):
    path, system = _removed_and_saved(tmp_path, KEY, remove)
    saved = path.read_text(encoding="utf-8")
    assert _digest(TEXT) not in saved
    (artifact,) = system.store.artifacts.values()
    assert artifact.content_digest.startswith(TOMBSTONE_PREFIX)
    assert artifact.metadata["text_digest"].startswith(TOMBSTONE_PREFIX)


def test_without_a_key_the_plain_fingerprint_is_kept_and_a_guess_can_be_confirmed(tmp_path):
    """A recorded gap, stated as an assertion: with no key the removed record keeps its plain fingerprint."""
    path, _ = _removed_and_saved(tmp_path, None)
    assert _digest(TEXT) in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("remove,answer", [("erase", ERASED), ("redact", REDACTED)])
def test_removed_text_handed_in_again_under_a_new_id_stays_removed_with_a_key(remove, answer):
    system = CCCSystem(tombstone_key=KEY, **OPEN)
    getattr(system, remove)(_record(system, candidate_id="c1").artifact_id, **HUMAN)
    _record(system, candidate_id="c2")
    assert _ask(system, "c2") == answer


def test_a_different_text_is_untouched_by_a_keyed_tombstone():
    system = CCCSystem(tombstone_key=KEY, **OPEN)
    system.erase(_record(system, candidate_id="c1").artifact_id, **HUMAN)
    _record(system, "Another finding entirely.", candidate_id="c2")
    assert _ask(system, "c2", "Another finding entirely.") == HELD


def test_the_keyed_tombstone_survives_a_save_and_a_load_with_the_same_key(tmp_path):
    path, _ = _removed_and_saved(tmp_path, KEY)
    reopened = CCCSystem(persistence_path=path, tombstone_key=KEY, **OPEN)
    _record(reopened, candidate_id="c2")
    assert _ask(reopened, "c2") == ERASED


def test_a_store_holding_keyed_tombstones_refuses_to_open_without_the_key(tmp_path):
    """Without the key a keyed tombstone matches nothing, so removed text would answer held again under a new id.
    The system refuses to start instead; the store itself can still be read for inspection."""
    path, _ = _removed_and_saved(tmp_path, KEY)
    with pytest.raises(UnguardedSystemError, match="tombstone_key"):
        CCCSystem(persistence_path=path, **OPEN)
    with pytest.raises(UnguardedSystemError, match="tombstone_key"):
        CCCSystem.load(path, **OPEN)
    assert len(CCCStore.load(path).artifacts) == 1


def test_a_record_removed_before_the_key_was_set_keeps_matching_by_its_plain_fingerprint(tmp_path):
    path, _ = _removed_and_saved(tmp_path, None)
    reopened = CCCSystem(persistence_path=path, tombstone_key=KEY, **OPEN)
    _record(reopened, candidate_id="c2")
    assert _ask(reopened, "c2") == ERASED


@pytest.mark.parametrize("bad", [b"", b"short", "t" * 32, 5])
def test_a_key_that_is_not_long_enough_bytes_is_refused(bad):
    with pytest.raises(ValueError):
        CCCSystem(tombstone_key=bad, **OPEN)
