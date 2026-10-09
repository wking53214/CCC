"""A human ingest with no stated basis is recorded as such, not given an invented one."""
from __future__ import annotations

from ccc import Actor, CCCSystem
from ccc.models import ProvenanceStatus

NOT_STATED = "not stated by caller"


def _origin_basis(system: CCCSystem, artifact_id: str):
    return system.provenance.history(artifact_id)[0].authorization_basis


def test_human_without_basis_is_uncertain_and_records_the_gap():
    system = CCCSystem()
    item = system.ingest("a claim", actor=Actor.human("w"))
    assert item.provenance_status is ProvenanceStatus.PROVENANCE_UNCERTAIN
    assert item.metadata["authorization_basis_stated"] is False
    assert _origin_basis(system, item.artifact_id) == NOT_STATED


def test_human_with_basis_is_recorded_verbatim_and_not_flagged():
    system = CCCSystem()
    item = system.ingest("a claim", actor=Actor.human("w"), authorization_basis="I wrote it")
    assert item.provenance_status is ProvenanceStatus.USER_ESTABLISHED
    assert "authorization_basis_stated" not in item.metadata
    assert _origin_basis(system, item.artifact_id) == "I wrote it"


def test_the_invented_phrase_is_gone():
    system = CCCSystem()
    item = system.ingest("a claim", actor=Actor.human("w"))
    assert _origin_basis(system, item.artifact_id) != "human-originating ingestion"


def test_model_and_system_ingests_are_unchanged():
    system = CCCSystem()
    model = system.ingest("m", actor=Actor.model("m"))
    machine = system.ingest("s", actor=Actor.system())
    assert model.provenance_status is ProvenanceStatus.ASSISTANT_PROPOSED
    assert machine.provenance_status is ProvenanceStatus.PROVENANCE_UNCERTAIN
    for item in (model, machine):
        assert "authorization_basis_stated" not in item.metadata
        assert _origin_basis(system, item.artifact_id) is None


def test_human_over_machine_source_is_still_uncertain_and_not_flagged():
    system = CCCSystem()
    source = system.ingest("machine text", actor=Actor.model("m"))
    item = system.ingest("human on top", actor=Actor.human("w"), source_material=(source.artifact_id,))
    assert item.provenance_status is ProvenanceStatus.PROVENANCE_UNCERTAIN
    assert "authorization_basis_stated" not in item.metadata


def test_the_audit_entry_agrees_with_the_provenance_record():
    system = CCCSystem()
    item = system.ingest("a claim", actor=Actor.human("w"))
    entries = [e for e in system.audit_trail.for_object(item.artifact_id) if e.operation == "INGEST"]
    assert entries and entries[0].authorization_basis == NOT_STATED
