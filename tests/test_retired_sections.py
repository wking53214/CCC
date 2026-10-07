"""State files written before turning points, threads, branches, simulations and
official terms were buried (wking53214/Graveyard, ccc/2026-10-06-unused-record-types)
still load, and their sections come back out of a save exactly as they went in."""
from __future__ import annotations

import json

import pytest

import ccc
from ccc import CCCSystem
from ccc.store import RETIRED_SECTIONS

OLD_SECTIONS = {
    "inflection_points": [{"inflection_id": "inflection_1", "directions": ["up"], "divergence": 0.4}],
    "threads": [{"thread_id": "thread_1", "title": "primary", "branch_ids": ["branch_1"]}],
    "branches": [{"branch_id": "branch_1", "parent_thread_id": "thread_1", "deferred": True}],
    "simulations": [{"simulation_id": "simulation_1", "limitations": ["l"]}],
    "terms": [{"term_id": "term_1", "term": "continuity", "status": "proposed"}],
}


def _old_file(tmp_path):
    state = CCCSystem().store.snapshot()
    state.update(OLD_SECTIONS)
    path = tmp_path / "old.json"
    path.write_text(json.dumps(state))
    return path


def test_old_sections_load_and_save_back_unchanged(tmp_path):
    system = CCCSystem.load(_old_file(tmp_path))
    out = json.loads(system.save(tmp_path / "new.json").read_text())
    for key, value in OLD_SECTIONS.items():
        assert out[key] == value, key


def test_a_fresh_store_writes_no_retired_sections(tmp_path):
    out = json.loads(CCCSystem().save(tmp_path / "fresh.json").read_text())
    assert not set(RETIRED_SECTIONS) & set(out)


def test_retired_sections_are_not_interpreted(tmp_path):
    system = CCCSystem.load(_old_file(tmp_path))
    assert system.validate_constitution()["valid"]
    for attr in ("inflection_points", "threads", "branches", "simulations", "terms"):
        assert not hasattr(system.store, attr), attr


@pytest.mark.parametrize("method", [
    "detect_inflection", "resolve_inflection", "create_thread", "create_branch",
    "close_branch", "simulate", "propose_term", "canonicalize",
    "record_dialogue_conclusion",
])
def test_buried_operations_are_gone(method):
    assert not hasattr(CCCSystem, method)


@pytest.mark.parametrize("module", [
    "inflection", "simulation", "canonicalization", "threads", "branches", "dialogue",
])
def test_buried_modules_are_gone(module):
    with pytest.raises(ImportError):
        __import__(f"ccc.{module}")
    assert not hasattr(ccc, module)
