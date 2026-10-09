"""add_artifact must not silently replace an artifact that already has the id.

Replacing an existing record is what replace_artifact is for. add_artifact
used to overwrite without a word, so a state file with a repeated id lost
the earlier record on load and nothing reported it.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from ccc import Actor, CCCSystem
from ccc.errors import DuplicateId
from ccc.store import CCCStore


def test_adding_a_new_artifact_still_works():
    system = CCCSystem()
    art = system.ingest("a new fact", actor=Actor.human("william"))

    assert system.store.artifacts[art.artifact_id].content == "a new fact"


def test_adding_an_existing_id_is_refused_and_the_original_is_kept():
    system = CCCSystem()
    art = system.ingest("the original", actor=Actor.human("william"))
    impostor = dataclasses.replace(art, content="an impostor")

    with pytest.raises(DuplicateId):
        system.store.add_artifact(impostor)

    assert system.store.artifacts[art.artifact_id].content == "the original"


def test_loading_a_state_file_with_a_repeated_id_is_refused(tmp_path):
    path = tmp_path / "state.json"
    system = CCCSystem(persistence_path=path)
    system.ingest("the original", actor=Actor.human("william"))
    system.save()

    raw = json.loads(path.read_text(encoding="utf-8"))
    copy = dict(raw["artifacts"][0])
    copy["content"] = "a repeated record with the same id"
    raw["artifacts"].append(copy)
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(DuplicateId):
        CCCStore.load(path)
