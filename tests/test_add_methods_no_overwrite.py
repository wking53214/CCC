"""The add_* store methods must not silently replace a record with the same id.

Same rule as add_artifact: adding an existing id raises DuplicateId and keeps
the original. Updates go through the replace_* methods, which are unchanged.
"""
from __future__ import annotations

import dataclasses

import pytest

from ccc import Actor
from ccc.errors import DuplicateId
from ccc.models import (
    ConflictClass,
    ConflictRecord,
    DiscoveryRecord,
    EpistemicStatus,
    EvidenceLink,
    ProvenanceStatus,
    RoadSign,
    RoadSignCategory,
    UncertaintyRecord,
)
from ccc.store import CCCStore


def _road_sign():
    return RoadSign(
        road_sign_id="sign_test",
        category=RoadSignCategory.REPEATED_RETURN,
        observation="original",
        source_material=(),
        detected_by=Actor.system(),
    )


def _uncertainty():
    return UncertaintyRecord(
        uncertainty_id="uncertainty_test",
        context="c",
        known=(),
        unknown=(),
        inferred=(),
        conflicted=(),
        candidates=(),
        requires_human_resolution=True,
        question="original",
        created_by=Actor.system(),
    )


def _conflict():
    return ConflictRecord(
        conflict_id="conflict_test",
        material_ids=("artifact_a", "artifact_b"),
        classification=ConflictClass.EVIDENCE_VS_EVIDENCE,
        why_material="original",
        choices=("a", "b"),
        downstream_consequences=(),
        remaining_uncertainty=(),
        detected_by=Actor.system(),
    )


def _discovery():
    return DiscoveryRecord(
        discovery_id="discovery_test",
        source_material=(),
        machine_origin=True,
        machine_processing_history=(),
        method="test",
        conclusion="original",
        confidence=None,
        supporting_evidence=(),
        epistemic_status=EpistemicStatus.INFERENCE,
        provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
    )


def _evidence_link():
    return EvidenceLink(
        link_id="link_test",
        evidence_id="evidence_test",
        claim_id="claim_test",
        rationale="original",
    )


# (add method, table name, record factory, id attr, field to change, kind label)
CASES = [
    ("add_road_sign", "road_signs", _road_sign, "road_sign_id", "observation"),
    ("add_uncertainty", "uncertainties", _uncertainty, "uncertainty_id", "question"),
    ("add_conflict", "conflicts", _conflict, "conflict_id", "why_material"),
    ("add_discovery", "discoveries", _discovery, "discovery_id", "conclusion"),
    ("add_evidence_link", "evidence_links", _evidence_link, "link_id", "rationale"),
]


@pytest.mark.parametrize("method, table, factory, id_attr, field", CASES)
def test_adding_a_new_record_still_works(method, table, factory, id_attr, field):
    store = CCCStore()
    record = factory()

    getattr(store, method)(record)

    assert getattr(store, table)[getattr(record, id_attr)] == record


@pytest.mark.parametrize("method, table, factory, id_attr, field", CASES)
def test_adding_an_existing_id_is_refused_and_the_original_is_kept(
    method, table, factory, id_attr, field
):
    store = CCCStore()
    original = factory()
    getattr(store, method)(original)
    impostor = dataclasses.replace(original, **{field: "an impostor"})

    with pytest.raises(DuplicateId):
        getattr(store, method)(impostor)

    kept = getattr(store, table)[getattr(original, id_attr)]
    assert getattr(kept, field) == "original"


@pytest.mark.parametrize("method, table, factory, id_attr, field", CASES)
def test_updating_still_goes_through_replace(method, table, factory, id_attr, field):
    store = CCCStore()
    original = factory()
    getattr(store, method)(original)
    updated = dataclasses.replace(original, **{field: "updated"})

    replace_method = method.replace("add_", "replace_", 1)
    getattr(store, replace_method)(updated)

    kept = getattr(store, table)[getattr(original, id_attr)]
    assert getattr(kept, field) == "updated"
