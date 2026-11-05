"""Evidence integrity and persistence, attacked.

Two questions. Can a record be silently overwritten, promoted or inflated on the
way in? And what does a state file promise once it is on disk? The second is
answered narrowly: the file is plain JSON with no digest, so the tests prove what
the write path does guarantee (a failed save leaves the previous complete file)
and state, as strict expected failures, what it does not (a tampered file is not
detected).
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from typing import Optional, Tuple

import pytest

from ccc import Actor, AnalysisStage, CCCSystem, EpistemicStatus, ProvenanceStatus
from ccc.errors import ConstitutionViolation, DuplicateId
from cccb import TextMatcher

MODEL, HUMAN = Actor.model("ecology"), Actor.human("reviewer")
BASIS = "explicit human record"


@dataclass(frozen=True)
class _Finding:
    conclusion: str
    method: str = "ecology.search"
    source_material: Tuple[str, ...] = ("notes.md",)
    confidence: Optional[float] = 0.6
    verified: bool = True
    evidence: Tuple[Tuple[str, str], ...] = ()


TEXT = ("The governance terminology inflated again into grandiose jargon across every revision "
        "of the planning notes, and the same inflation reappeared in the audit summary written afterwards.")
RECURRING = [
    "ledger hashing digest chain rolling block audit trail verification alpha",
    "verification audit trail block rolling chain digest hashing ledger bravo",
]


def _world():
    """One of each kind of record, so a table-by-table check has something to find."""
    system = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())
    w = type("W", (), {})()
    w.system = system
    w.fact = system.ingest("A human fact.", actor=HUMAN, epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
                           authorization_basis=BASIS)
    w.fact2 = system.ingest("A second human fact.", actor=HUMAN, epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
                            authorization_basis=BASIS)
    w.proposal = system.derive("A machine inference.", actor=MODEL, evidence_ids=(w.fact.artifact_id,))
    w.finding = system.record_external_finding(_Finding(TEXT, evidence=(("notes.md", TEXT),)), actor=MODEL)
    w.conflict = system.detect_conflict(
        material_ids=(w.fact.artifact_id, w.fact2.artifact_id), why_material="they disagree",
        choices=("a", "b"), downstream_consequences=("x",), remaining_uncertainty=("which",), actor=MODEL)
    w.uncertainty = system.ask(context="c", question="which one?", actor=MODEL)
    return w


def _state(system) -> str:
    return json.dumps(system.store.snapshot(), sort_keys=True)


# --- duplicate ids: every record table, on the way in and on reload ---------------------

TABLES = ["artifacts", "evidence_links", "discoveries", "uncertainties", "conflicts"]


@pytest.mark.parametrize("table", TABLES)
def test_a_state_file_with_a_repeated_id_is_refused_for_every_table(tmp_path, table):
    w = _world()
    path = w.system.save(tmp_path / "state.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[table], f"the world has no {table}"
    data[table].append(copy.deepcopy(data[table][0]))
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DuplicateId):
        CCCSystem.load(path)


def test_duplicate_protection_is_still_active_after_a_reload(tmp_path):
    w = _world()
    path = w.system.save(tmp_path / "state.json")
    reloaded = CCCSystem.load(path, text_matcher=TextMatcher(), private_source_markers=())
    original = reloaded.store.require_artifact(w.fact.artifact_id)
    with pytest.raises(DuplicateId):
        reloaded.store.add_artifact(original)
    assert reloaded.store.require_artifact(w.fact.artifact_id) == original
    with pytest.raises(DuplicateId):
        reloaded.store.add_discovery(reloaded.store.discoveries[w.finding.discovery_id])


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN LIMIT (finding F-08): the append-only event lists (audit, provenance, epistemic, "
    "lineage) do not check for a repeated event id, on append or on load, unlike every keyed "
    "table. Event ids come from uuid4, so the public API cannot collide them; a hand-edited "
    "state file can. Closing it is small (an id set per list) but changes what loads, so it "
    "is left for a decision."))
def test_known_limit_a_repeated_audit_event_id_is_not_refused():
    w = _world()
    event = w.system.store.audit_events[0]
    with pytest.raises(DuplicateId):
        w.system.store.append_audit(event)


# --- a record cannot be quietly replaced, and a replacement is visible ----------------------

def test_superseding_adds_a_record_and_leaves_the_original_in_place():
    w = _world()
    system = w.system
    before = system.store.require_artifact(w.proposal.artifact_id)
    replacement = system.supersede(w.proposal.artifact_id, content="A corrected machine inference.", actor=HUMAN,
                                   reason="corrected", authorization_basis=BASIS)
    assert replacement.artifact_id != w.proposal.artifact_id
    assert system.store.require_artifact(w.proposal.artifact_id).content == before.content
    assert "SUPERSEDE" in [e.operation for e in system.audit()]


def test_a_conflict_survives_supersession_and_a_reload_with_its_material(tmp_path):
    w = _world()
    system = w.system
    system.supersede(w.fact.artifact_id, content="A corrected first fact.", actor=HUMAN, reason="corrected",
                     authorization_basis=BASIS)
    path = system.save(tmp_path / "state.json")
    reloaded = CCCSystem.load(path)
    conflict = reloaded.store.conflicts[w.conflict.conflict_id]
    assert set(conflict.material_ids) == {w.fact.artifact_id, w.fact2.artifact_id}
    assert reloaded.store.require_artifact(w.fact.artifact_id).content == "A human fact."


# --- nothing promotes itself -----------------------------------------------------------------

def test_a_machine_cannot_create_a_mandate_directly():
    """Finding F-04. discover() used to accept stage=MANDATE from anyone, stamped with the
    human-established attribution, skipping CCC-123-001 (human, human_event, basis, evidence)."""
    system = CCCSystem()
    for actor in (MODEL, Actor.system("job"), HUMAN, Actor.external("feed")):
        with pytest.raises(ConstitutionViolation, match="CCC-123-001"):
            system.discover(source_material=("a",), method="m", conclusion="c", confidence=0.5,
                            supporting_evidence=(), actor=actor, stage=AnalysisStage.MANDATE)
    assert not system.store.discoveries


@pytest.mark.parametrize("stage", [None, AnalysisStage.ANOMALY, AnalysisStage.PATTERN])
def test_discover_still_creates_records_at_the_other_stages(stage):
    system = CCCSystem()
    record = system.discover(source_material=("a",), method="m", conclusion="c", confidence=0.5,
                             supporting_evidence=(), actor=MODEL, stage=stage)
    assert record.stage is stage


def test_the_only_road_to_a_mandate_is_a_human_advancing_a_pattern_with_evidence():
    w = _world()
    system = w.system
    pattern = system.discover(source_material=(w.fact.artifact_id,), method="m", conclusion="c", confidence=0.5,
                              supporting_evidence=(), actor=MODEL, stage=AnalysisStage.PATTERN)
    with pytest.raises(ConstitutionViolation, match="CCC-123-001"):
        system.advance_discovery(pattern.discovery_id, stage=AnalysisStage.MANDATE, actor=MODEL, reason="r",
                                 evidence_ids=(w.fact.artifact_id,), human_event=True, authorization_basis=BASIS)
    mandate = system.advance_discovery(pattern.discovery_id, stage=AnalysisStage.MANDATE, actor=HUMAN, reason="r",
                                       evidence_ids=(w.fact.artifact_id,), human_event=True, authorization_basis=BASIS)
    assert mandate.stage is AnalysisStage.MANDATE


def test_repeated_machine_submissions_never_reach_a_mandate_or_a_human_status():
    system = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())
    for text in RECURRING * 4 + [TEXT] * 4:
        system.record_external_finding(_Finding(text), actor=MODEL)
    records = list(system.store.discoveries.values())
    assert all(r.stage is not AnalysisStage.MANDATE for r in records)
    assert all(r.provenance_status is ProvenanceStatus.ASSISTANT_PROPOSED for r in records)
    assert all(r.epistemic_status is EpistemicStatus.INFERENCE for r in records)


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN LIMIT (finding F-01, a CCCb measurement gap): CCCb needs a 40-character shared "
    "span before it calls two texts duplicates (a shorter match can be coincidence), so an "
    "identical short finding is measured as a recurrence, which CCC counts as an independent "
    "occurrence. Three identical 31-character resubmissions lift the first to PATTERN and "
    "raise a REPEATED_RETURN sign. An identity check is a duplicate measurement, so it "
    "belongs in CCCb and needs separate authorization; CCC does not paper over it. When the "
    "matcher treats identical text as a duplicate this test XPASSes and the marker must go."))
def test_known_limit_resubmitting_an_identical_short_finding_is_not_independent_corroboration():
    system = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())
    for _ in range(3):
        system.record_external_finding(_Finding("The ledger hash chain is broken."), actor=MODEL)
    (group,) = system.recurring_groups()
    assert group.occurrence_count == 1


def test_uncertainty_and_conflict_are_kept_through_a_reload(tmp_path):
    w = _world()
    path = w.system.save(tmp_path / "state.json")
    reloaded = CCCSystem.load(path)
    assert w.uncertainty.uncertainty_id in reloaded.store.uncertainties
    assert w.conflict.conflict_id in reloaded.store.conflicts
    assert reloaded.store.discoveries[w.finding.discovery_id].confidence == 0.6
    none_confidence = reloaded.discover(source_material=("a",), method="m", conclusion="c", confidence=None,
                                        supporting_evidence=(), actor=MODEL)
    reloaded.save(path)
    assert CCCSystem.load(path).store.discoveries[none_confidence.discovery_id].confidence is None


# --- persistence: what a save guarantees ------------------------------------------------------

def test_a_save_and_reload_keeps_provenance_and_meaning(tmp_path):
    w = _world()
    path = w.system.save(tmp_path / "state.json")
    reloaded = CCCSystem.load(path, text_matcher=TextMatcher(), private_source_markers=())
    assert reloaded.store.snapshot() == w.system.store.snapshot()
    for artifact in w.system.store.artifacts.values():
        again = reloaded.store.require_artifact(artifact.artifact_id)
        assert (again.origin, again.provenance_status, again.epistemic_status, again.content_digest) == (
            artifact.origin, artifact.provenance_status, artifact.epistemic_status, artifact.content_digest)
    assert reloaded.validate_constitution()["valid"] is True


def test_a_reloaded_system_still_recognises_a_resubmission_as_a_duplicate(tmp_path):
    system = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())
    first = system.record_external_finding(_Finding(TEXT), actor=MODEL)
    path = system.save(tmp_path / "state.json")
    reloaded = CCCSystem.load(path, text_matcher=TextMatcher(), private_source_markers=())
    again = reloaded.record_external_finding(_Finding(TEXT), actor=MODEL)
    assert again.relationships == (first.discovery_id,) and "duplicate detection" in again.method
    (group,) = reloaded.recurring_groups()
    assert group.occurrence_count == 1


def _no_temp_files(directory):
    return [p.name for p in directory.iterdir() if p.name.endswith(".tmp")]


def test_a_save_leaves_no_temporary_file_behind(tmp_path):
    w = _world()
    w.system.save(tmp_path / "state.json")
    w.system.save(tmp_path / "state.json")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]


@pytest.mark.parametrize("failing", ["fsync", "replace"])
def test_a_save_that_fails_midway_leaves_the_previous_complete_file(tmp_path, monkeypatch, failing):
    w = _world()
    path = w.system.save(tmp_path / "state.json")
    good = path.read_bytes()
    w.system.ingest("A note written after the last good save.", actor=HUMAN)

    def boom(*_a, **_k):
        raise OSError(f"{failing} failed")

    monkeypatch.setattr(os, failing, boom)
    with pytest.raises(OSError, match=failing):
        w.system.save(path)
    monkeypatch.undo()
    assert path.read_bytes() == good
    assert _no_temp_files(tmp_path) == []
    reloaded = CCCSystem.load(path)
    assert len(reloaded.store.artifacts) == len(w.system.store.artifacts) - 1


def test_a_save_that_cannot_serialize_does_not_touch_the_existing_file(tmp_path):
    w = _world()
    path = w.system.save(tmp_path / "state.json")
    good = path.read_bytes()
    w.system.store.discovery_match_texts["poison"] = {1, 2}      # not JSON
    with pytest.raises(TypeError):
        w.system.save(path)
    assert path.read_bytes() == good and _no_temp_files(tmp_path) == []


def test_saving_through_a_symlink_keeps_the_link(tmp_path):
    w = _world()
    real = tmp_path / "real.json"
    link = tmp_path / "link.json"
    link.symlink_to(real)
    w.system.save(link)
    assert link.is_symlink() and real.is_file()
    assert CCCSystem.load(real).store.snapshot() == w.system.store.snapshot()


# --- persistence: what a damaged file does ---------------------------------------------------

def test_a_truncated_state_file_fails_closed_and_is_never_read_as_a_fresh_store(tmp_path):
    w = _world()
    path = w.system.save(tmp_path / "state.json")
    full = path.read_bytes()
    for cut in (len(full) // 2, len(full) - 3, 1):
        path.write_bytes(full[:cut])
        with pytest.raises(json.JSONDecodeError):
            CCCSystem.load(path)
        with pytest.raises(json.JSONDecodeError):
            CCCSystem(persistence_path=path)


@pytest.mark.parametrize("garbage", ["[]", "null", "42", '"text"', "not json at all", "{"])
def test_a_state_file_that_is_not_a_state_object_is_refused(tmp_path, garbage):
    path = tmp_path / "state.json"
    path.write_text(garbage, encoding="utf-8")
    with pytest.raises(Exception):
        CCCSystem.load(path)


def test_an_empty_state_file_is_a_fresh_store_by_design_and_a_save_replaces_it(tmp_path):
    path = tmp_path / "state.json"
    path.write_bytes(b"")
    system = CCCSystem(persistence_path=path)
    assert not system.store.artifacts
    system.ingest("A note.", actor=HUMAN)
    system.save()
    assert len(CCCSystem.load(path).store.artifacts) == 1


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN LIMIT (finding F-06): the state file carries no digest, MAC or version, so an edited "
    "file loads as valid. Flipping a machine record's origin to HUMAN and its status to "
    "USER_ESTABLISHED is accepted and validate_constitution() still reports valid. CCC makes no "
    "tamper-evidence claim for the file; a README sentence already says anyone who can write "
    "the store can write anything. Fixing it needs a key and a format decision, not a patch."))
def test_known_limit_a_tampered_state_file_is_not_detected(tmp_path):
    w = _world()
    path = w.system.save(tmp_path / "state.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    target = next(a for a in data["artifacts"] if a["origin"]["kind"] == "MODEL")
    target["origin"]["kind"] = "HUMAN"
    target["provenance_status"] = "USER_ESTABLISHED"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(Exception):
        CCCSystem.load(path)
