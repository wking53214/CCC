"""CCC resume packet: built on demand from open items, read-only.

Covers which items become pins, which road sign categories become concepts,
that building a packet changes nothing in the system, and the packet shape
shared with Synapsis.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ccc import Actor, CCCSystem, RoadSignCategory
from ccc.models import ConflictClass, ConflictRecord, ConflictStatus
from ccc.resume_packet import build_resume_packet


def _build(system, **overrides):
    values = {
        "packet_id": "STATE-0001",
        "title": "Example thread",
        "current_problem": "Preserve and continue the analysis",
        "next_action": "Re-run the scan",
        "created": datetime(2026, 10, 9, 12, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return build_resume_packet(system, **values)


def _ask(system, question="Which reading holds?"):
    return system.ask(
        context="test context",
        question=question,
        actor=Actor.system(),
    )


def _conflict(conflict_id="conflict_test"):
    return ConflictRecord(
        conflict_id=conflict_id,
        material_ids=("artifact_a", "artifact_b"),
        classification=ConflictClass.EVIDENCE_VS_EVIDENCE,
        why_material="two sources disagree",
        choices=("keep a", "keep b"),
        downstream_consequences=(),
        remaining_uncertainty=(),
        detected_by=Actor.system(),
    )


def test_empty_system_has_no_pins_or_concepts():
    packet = _build(CCCSystem())

    assert packet["state"]["active_pins"] == []
    assert packet["state"]["active_concepts"] == []


def test_open_uncertainty_is_a_pin():
    system = CCCSystem()
    record = _ask(system)

    packet = _build(system)

    assert packet["state"]["active_pins"] == [record.uncertainty_id]


def test_resolved_uncertainty_is_not_a_pin():
    system = CCCSystem()
    record = _ask(system)
    system.resolve_uncertainty(
        record.uncertainty_id,
        choice="keep the first reading",
        actor=Actor.human(),
        reason="human chose",
        authorization_basis="test",
    )

    packet = _build(system)

    assert packet["state"]["active_pins"] == []


def test_unresolved_conflict_is_a_pin_and_resolved_one_is_not():
    system = CCCSystem()
    open_conflict = _conflict("conflict_open")
    system.store.add_conflict(open_conflict)
    system.store.add_conflict(
        replace(_conflict("conflict_done"), status=ConflictStatus.RESOLVED)
    )

    packet = _build(system)

    assert packet["state"]["active_pins"] == ["conflict_open"]


def test_road_sign_linked_to_open_pin_contributes_its_category():
    system = CCCSystem()
    record = _ask(system)
    system.detect_road_sign(
        observation="the same question came back",
        category=RoadSignCategory.REPEATED_RETURN,
        actor=Actor.system(),
        linked_ids=(record.uncertainty_id,),
    )

    packet = _build(system)

    assert packet["state"]["active_concepts"] == ["repeated_return"]


def test_road_sign_linked_to_nothing_open_is_left_out():
    system = CCCSystem()
    _ask(system)
    system.detect_road_sign(
        observation="an unrelated shift",
        category=RoadSignCategory.BREAKTHROUGH,
        actor=Actor.system(),
        linked_ids=("uncertainty_already_closed",),
    )

    packet = _build(system)

    assert packet["state"]["active_concepts"] == []


def test_building_a_packet_changes_nothing():
    system = CCCSystem()
    record = _ask(system)
    system.detect_road_sign(
        observation="the same question came back",
        category=RoadSignCategory.REPEATED_RETURN,
        actor=Actor.system(),
        linked_ids=(record.uncertainty_id,),
    )
    system.store.add_conflict(_conflict())

    audit_before = len(system.audit_trail.all())
    counts_before = (
        len(system.store.uncertainties),
        len(system.store.road_signs),
        len(system.store.conflicts),
    )

    _build(system)
    _build(system)

    assert len(system.audit_trail.all()) == audit_before
    assert counts_before == (
        len(system.store.uncertainties),
        len(system.store.road_signs),
        len(system.store.conflicts),
    )


def test_packet_has_the_shared_shape():
    packet = _build(CCCSystem())

    assert packet["packet_type"] == "synapsis_resume_packet"
    assert packet["version"] == "1.0"
    assert set(packet["state"]) == {
        "id",
        "title",
        "current_problem",
        "next_action",
        "active_concepts",
        "active_pins",
        "created",
    }
    assert packet["state"]["id"] == "STATE-0001"
    assert packet["state"]["created"] == "2026-10-09T12:00:00+00:00"


def test_created_defaults_to_now_in_utc():
    packet = build_resume_packet(
        CCCSystem(),
        packet_id="STATE-0002",
        title="t",
        current_problem="p",
        next_action="n",
    )

    created = datetime.fromisoformat(packet["state"]["created"])
    assert created.tzinfo is not None


@pytest.mark.parametrize(
    "field", ["packet_id", "title", "current_problem", "next_action"]
)
def test_rejects_a_non_string_field(field):
    values = {
        "packet_id": "STATE-0001",
        "title": "t",
        "current_problem": "p",
        "next_action": "n",
    }
    values[field] = None

    with pytest.raises(TypeError, match=field):
        build_resume_packet(CCCSystem(), **values)
