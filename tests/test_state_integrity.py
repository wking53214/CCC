"""A saved state that proves it was not edited after it was saved (A14).

CCC's state file had no integrity protection: a record added or changed in the file by hand loaded like any other.
With an ``integrity_key`` (the caller's; CCC keeps none) every save carries an HMAC over exactly the state written,
and a load with the key refuses a file that does not verify. Without a key nothing changes.
"""
from __future__ import annotations

import json

import pytest

from ccc import Actor, CCCSystem
from ccc.errors import StateIntegrityError
from ccc.store import INTEGRITY_FIELD, CCCStore

KEY = b"k" * 32
OTHER = b"o" * 32
OPEN = dict(allow_unguarded_writes=True, allow_unverified_humans=True)


def _saved(tmp_path, key=KEY):
    path = tmp_path / "state.json"
    system = CCCSystem(persistence_path=path, integrity_key=key, **OPEN)
    system.ingest("The lease is renewed monthly.", actor=Actor.model("triad42"),
                  metadata={"source": "triad42", "candidate_id": "c1"})
    system.save()
    return path, system


def _edit(path, change):
    raw = json.loads(path.read_text(encoding="utf-8"))
    change(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_a_state_saved_with_the_key_loads_with_it_and_keeps_its_records(tmp_path):
    path, system = _saved(tmp_path)
    reopened = CCCSystem(persistence_path=path, integrity_key=KEY, **OPEN)
    assert set(reopened.store.artifacts) == set(system.store.artifacts)
    assert CCCSystem.load(path, integrity_key=KEY, **OPEN).store.artifacts.keys() == system.store.artifacts.keys()


@pytest.mark.parametrize("change", [
    lambda raw: raw["artifacts"][0].__setitem__("content", "The lease is cancelled."),
    lambda raw: raw["artifacts"].append(dict(raw["artifacts"][0], artifact_id="forged-1")),
    lambda raw: raw["artifacts"][0]["metadata"].__setitem__("candidate_id", "c9"),
    lambda raw: raw.__setitem__("audit_events", []),
], ids=["edited-text", "added-record", "edited-metadata", "dropped-audit"])
def test_a_file_changed_after_it_was_saved_is_refused_and_nothing_loads(tmp_path, change):
    path, _ = _saved(tmp_path)
    _edit(path, change)
    with pytest.raises(StateIntegrityError, match="does not verify"):
        CCCSystem(persistence_path=path, integrity_key=KEY, **OPEN)
    with pytest.raises(StateIntegrityError):
        CCCStore.load(path, integrity_key=KEY)


def test_a_removed_integrity_record_is_refused(tmp_path):
    path, _ = _saved(tmp_path)
    _edit(path, lambda raw: raw.pop(INTEGRITY_FIELD))
    with pytest.raises(StateIntegrityError, match="no ccc-state-hmac/1"):
        CCCStore.load(path, integrity_key=KEY)


def test_another_key_does_not_verify(tmp_path):
    path, _ = _saved(tmp_path)
    with pytest.raises(StateIntegrityError, match="does not verify"):
        CCCStore.load(path, integrity_key=OTHER)


def test_a_state_saved_without_a_key_is_refused_by_a_load_that_asks_for_one(tmp_path):
    path, _ = _saved(tmp_path, key=None)
    assert INTEGRITY_FIELD not in json.loads(path.read_text(encoding="utf-8"))
    with pytest.raises(StateIntegrityError):
        CCCStore.load(path, integrity_key=KEY)


def test_without_a_key_a_signed_file_loads_as_before_and_an_edit_goes_unnoticed(tmp_path):
    """A recorded gap, stated as an assertion: without a key there is nothing to check against."""
    path, _ = _saved(tmp_path)
    _edit(path, lambda raw: raw["artifacts"][0].__setitem__("content", "The lease is cancelled."))
    reopened = CCCSystem(persistence_path=path, **OPEN)
    (artifact,) = reopened.store.artifacts.values()
    assert artifact.content == "The lease is cancelled."


def test_the_integrity_record_is_never_kept_as_part_of_the_state(tmp_path):
    path, _ = _saved(tmp_path)
    store = CCCStore.load(path, integrity_key=KEY)
    assert INTEGRITY_FIELD not in store.snapshot() and INTEGRITY_FIELD not in store.retired_sections
    store.save(tmp_path / "plain.json")
    assert INTEGRITY_FIELD not in json.loads((tmp_path / "plain.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("bad", [b"", b"short", "k" * 32, 5])
def test_a_key_that_is_not_long_enough_bytes_is_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        CCCSystem(integrity_key=bad, **OPEN)
    with pytest.raises(ValueError):
        CCCStore(tmp_path / "s.json").save(integrity_key=bad)
