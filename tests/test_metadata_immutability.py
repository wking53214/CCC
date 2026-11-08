"""An Artifact's metadata is read-only all the way down, not just at its top level."""

import datetime

import pytest

from ccc.models import (
    MAX_METADATA_DEPTH,
    Actor,
    Artifact,
    EpistemicStatus,
    ProvenanceStatus,
)


def _artifact(metadata):
    return Artifact(
        artifact_id="a1", content="text", origin=Actor.human("h"),
        provenance_status=ProvenanceStatus.USER_ESTABLISHED,
        epistemic_status=EpistemicStatus.HISTORICAL_RECORD, metadata=metadata,
    )


def test_nested_mappings_cannot_be_changed():
    a = _artifact({"outer": {"inner": {"value": 1}}})
    with pytest.raises(TypeError):
        a.metadata["outer"]["inner"]["value"] = 2
    with pytest.raises(TypeError):
        a.metadata["outer"]["new"] = 3
    assert a.metadata["outer"]["inner"]["value"] == 1


def test_nested_lists_become_tuples_that_cannot_be_changed():
    a = _artifact({"stamp": {"ids": ["x", "y"]}})
    ids = a.metadata["stamp"]["ids"]
    assert ids == ("x", "y")
    with pytest.raises(AttributeError):
        ids.append("z")


def test_the_caller_keeps_no_handle_on_the_frozen_copy():
    source = {"outer": {"inner": ["x"]}}
    a = _artifact(source)
    source["outer"]["inner"].append("y")
    source["outer"]["added"] = 1
    assert a.metadata["outer"]["inner"] == ("x",)
    assert "added" not in a.metadata["outer"]


def test_metadata_nested_past_the_limit_is_refused():
    value: object = "leaf"
    for _ in range(MAX_METADATA_DEPTH + 1):
        value = {"k": value}
    with pytest.raises(ValueError, match="nested more than"):
        _artifact({"deep": value})


def test_a_cycle_in_metadata_is_refused_not_looped_on():
    cycle: dict = {}
    cycle["self"] = cycle
    with pytest.raises(ValueError, match="nested more than"):
        _artifact({"cycle": cycle})


def test_set_metadata_saves_and_loads_back(tmp_path):
    from ccc.system import CCCSystem

    system = CCCSystem()
    human = Actor.human("h")
    system.ingest("tagged", actor=human, metadata={"tags": {"x", "y"}})
    path = tmp_path / "store.json"
    system.store.save(path)
    loaded = CCCSystem.load(path)
    stored = next(a for a in loaded.store.artifacts.values() if a.content == "tagged")
    assert sorted(stored.metadata["tags"]) == ["x", "y"]


@pytest.mark.parametrize(
    "value",
    [bytearray(b"ab"), object(), datetime.datetime(2026, 1, 1)],
    ids=["bytearray", "custom object", "datetime"],
)
def test_metadata_of_an_unsupported_type_is_refused_at_intake(value):
    with pytest.raises(TypeError, match="not supported"):
        _artifact({"value": value})


def test_supported_scalars_and_enums_are_kept():
    a = _artifact({"text": "t", "count": 2, "ratio": 0.5, "flag": True, "none": None,
                   "status": ProvenanceStatus.USER_ESTABLISHED})
    assert a.metadata["status"] is ProvenanceStatus.USER_ESTABLISHED
    assert a.metadata["none"] is None
