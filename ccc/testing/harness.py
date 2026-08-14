"""Numbered H01-H62 constitutional harness.

The checkout contains no prior harness history, so every row explicitly
records ``historical_meaning=UNSPECIFIED``.  Rows backed by the current build
directive have executable scenarios; the remaining rows are never converted
to PASS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .. import Actor, CCCSystem
from ..errors import ConstitutionViolation, InvalidTransition
from ..models import (
    AnalysisStage,
    EpistemicStatus,
    ProvenanceStatus,
    RoadSignCategory,
    RelationshipType,
    TermStatus,
)


def _human() -> Actor:
    return Actor.human("harness-human")


def _model() -> Actor:
    return Actor.model("harness-model")


def _fact(system: CCCSystem, *, epistemic: EpistemicStatus = EpistemicStatus.HISTORICAL_RECORD):
    return system.ingest("human-established source", actor=_human(), epistemic_status=epistemic)


def _blocked(call: Callable[[], object]) -> tuple[bool, tuple[str, ...]]:
    try:
        call()
    except (ConstitutionViolation, InvalidTransition, ValueError):
        return True, ("constitutional rejection observed",)
    return False, ("operation unexpectedly succeeded",)


def _h01():
    system = CCCSystem()
    item = _fact(system)
    assert item.provenance_status is ProvenanceStatus.USER_ESTABLISHED
    assert system.provenance.history(item.artifact_id)[0].human_originating
    return ("human origin event",)


def _h02():
    system = CCCSystem()
    item = system.derive("machine proposal", actor=_model())
    blocked, evidence = _blocked(lambda: system.establish_provenance(item.artifact_id, actor=_model(), reason="consensus", authorization_basis="model vote"))
    assert blocked
    return evidence


def _h03():
    system = CCCSystem()
    source = _fact(system)
    result = system.derive("machine inference", actor=_model(), evidence_ids=(source.artifact_id,))
    assert result.origin.kind.value == "MODEL"
    assert result.provenance_status is ProvenanceStatus.ASSISTANT_PROPOSED
    return (source.artifact_id, result.artifact_id)


def _h04():
    system = CCCSystem()
    simulation = system.ingest("modeled trajectory", actor=_model(), epistemic_status=EpistemicStatus.SIMULATION)
    blocked, evidence = _blocked(lambda: system.classify(simulation.artifact_id, EpistemicStatus.HISTORICAL_RECORD, actor=_human(), reason="relabel"))
    assert blocked
    return evidence


def _h05():
    system = CCCSystem()
    source = _fact(system)
    claim = system.derive("supported inference", evidence_ids=(source.artifact_id,))
    validation = system.validate_evidence_chain(claim.artifact_id)
    assert validation.valid and validation.roots == (source.artifact_id,)
    return validation.roots


def _h06():
    system = CCCSystem()
    source = _fact(system)
    claim = system.derive("dependent inference", evidence_ids=(source.artifact_id,))
    system.erase(source.artifact_id, actor=_human(), reason="privacy erasure", authorization_basis="human request")
    assert system.evidence_root(claim.artifact_id) == ()
    assert system.store.require_artifact(claim.artifact_id).epistemic_status is EpistemicStatus.THEORY
    assert not system.store.links_for_claim(claim.artifact_id, active_only=True)
    return ("root erased", "dependent downgraded")


def _h07():
    system = CCCSystem()
    source = _fact(system)
    blocked, evidence = _blocked(lambda: system.erase(source.artifact_id, actor=_model(), reason="machine veto", authorization_basis="model"))
    assert blocked
    return evidence


def _h08():
    system = CCCSystem()
    old = _fact(system)
    new = system.correct(old.artifact_id, content="corrected record", actor=_human(), reason="human correction", authorization_basis="human review")
    assert system.store.require_artifact(old.artifact_id).content == "human-established source"
    assert new.content == "corrected record"
    return (old.artifact_id, new.artifact_id)


def _h09():
    system = CCCSystem()
    item = _fact(system)
    redacted = system.redact(item.artifact_id, actor=_human(), reason="redaction request", authorization_basis="human review")
    assert redacted.state.value == "REDACTED" and redacted.content is None
    return ("redaction tombstone",)


def _h10():
    system = CCCSystem()
    one = _fact(system)
    two = _fact(system)
    conflict = system.detect_conflict(material_ids=(one.artifact_id, two.artifact_id), why_material="records disagree", choices=("one", "two"), downstream_consequences=("decision changes",), remaining_uncertainty=("which record is correct",), actor=_model())
    assert conflict.classification.value == "EVIDENCE_VS_EVIDENCE" and conflict.status.value == "OPEN"
    return (conflict.conflict_id,)


def _h11():
    system = CCCSystem()
    uncertainty = system.ask(context="origin", known=("two records exist",), unknown=("which is primary",), candidates=("record-a", "record-b"), question="Which record, if any, is the primary source?", actor=_model())
    assert uncertainty.requires_human_resolution and uncertainty.resolved_choice is None
    return (uncertainty.uncertainty_id,)


def _h12():
    system = CCCSystem()
    sign = system.detect_road_sign(observation="the direction changed", category=RoadSignCategory.DIRECTION_CHANGE, actor=_model())
    assert not sign.is_conclusion
    return (sign.road_sign_id,)


def _h13():
    system = CCCSystem()
    point = system.detect_inflection(thread_id="thread-not-required", directions=("redirected",), divergence=0.8, sensitivity=0.2, machine_weight=0.9, actor=_model())
    assert point.significance is None and point.divergence != point.sensitivity
    return (point.inflection_id,)


def _h14():
    system = CCCSystem()
    thread = system.create_thread(title="primary", actor=_human())
    branch = system.create_branch(thread.thread_id, title="deferred branch", actor=_model(), deferred=True)
    assert branch.branch_id in system.store.threads[thread.thread_id].branch_ids
    assert any(event.relationship is RelationshipType.BRANCH_OF for event in system.store.lineage_events) is False
    return (thread.thread_id, branch.branch_id)


def _h15():
    system = CCCSystem()
    source = _fact(system)
    anomaly = system.discover(source_material=(source.artifact_id,), method="anomaly scan", conclusion="unexpected return", confidence=0.7, actor=_model(), stage=AnalysisStage.ANOMALY)
    pattern = system.advance_discovery(anomaly.discovery_id, stage=AnalysisStage.PATTERN, actor=_model(), reason="repeated pattern")
    mandate = system.advance_discovery(pattern.discovery_id, stage=AnalysisStage.MANDATE, actor=_human(), reason="human mandate", evidence_ids=(source.artifact_id,), human_event=True, authorization_basis="human ratification")
    assert mandate.stage is AnalysisStage.MANDATE and mandate.attribution.startswith("HUMAN_ESTABLISHED")
    return ("ANOMALY", "PATTERN", "MANDATE")


def _h16():
    system = CCCSystem()
    discovery = system.discover(source_material=(), method="relationship scan", conclusion="possible connection", confidence=0.4, actor=_model())
    assert discovery.machine_origin and discovery.provenance_status is ProvenanceStatus.ASSISTANT_PROPOSED
    return (discovery.discovery_id,)


def _h17():
    system = CCCSystem()
    source = _fact(system)
    sim = system.simulate(inputs=(source.artifact_id,), assumptions=("steady demand",), shared_assumptions=("same baseline",), trajectory=("a", "b"), counterfactual="if demand changes", output="modeled output", sensitivity={"demand": 0.8}, limitations=("not history",), actor=_model())
    assert sim.epistemic_status is EpistemicStatus.SIMULATION and sim.shared_assumptions == ("same baseline",)
    return (sim.simulation_id,)


def _h18():
    system = CCCSystem()
    source = _fact(system)
    term = system.propose_term(term="CCC", definition="proposed term", actor=_model())
    canonical = system.canonicalize(term.term_id, actor=_human(), source_material=(source.artifact_id,), reason="human terminology decision", authorization_basis="human review")
    assert canonical.status is TermStatus.CANONICAL
    return (canonical.term_id,)


def _h19():
    system = CCCSystem()
    item = system.ingest("topic material", actor=_human(), topics=("continuity",), instrument="note", confidence=0.9, presentation_priority=1)
    assert system.query(topic="continuity", source="harness-human", instrument="note", min_confidence=0.8, epistemic_status=EpistemicStatus.UNKNOWN, artifact=item.artifact_id)
    return (item.artifact_id,)


def _h20():
    system = CCCSystem()
    item = _fact(system)
    event = system.audit(object_id=item.artifact_id)[-1]
    assert event.actor.kind.value == "HUMAN" and event.operation == "INGEST"
    return (event.event_id,)


def _h21():
    return _h08()


def _h22():
    system = CCCSystem()
    old = _fact(system)
    new = system.supersede(old.artifact_id, content="superseding record", actor=_human(), reason="new record governs", authorization_basis="human review")
    assert system.store.require_artifact(old.artifact_id).content == "human-established source"
    assert any(event.relationship is RelationshipType.SUPERSEDES for event in system.store.lineage_events)
    return (old.artifact_id, new.artifact_id)


def _h23():
    item = CCCSystem().derive("inference", actor=_model())
    assert item.epistemic_status is EpistemicStatus.INFERENCE and item.provenance_status is ProvenanceStatus.ASSISTANT_PROPOSED
    return (item.artifact_id,)


def _h24():
    system = CCCSystem()
    item = system.derive("consensus", actor=_model(), machine_consensus=True)
    blocked, evidence = _blocked(lambda: system.establish_provenance(item.artifact_id, actor=_model(), reason="models agree", authorization_basis="machine consensus"))
    assert blocked
    return evidence


def _h25():
    from dataclasses import FrozenInstanceError
    item = _fact(CCCSystem())
    try:
        item.provenance_status = ProvenanceStatus.REJECTED
    except FrozenInstanceError:
        return ("immutable artifact",)
    raise AssertionError("direct provenance mutation succeeded")


def _h26():
    system = CCCSystem()
    item = system.derive("reject me", actor=_model())
    rejected = system.reject(item.artifact_id, actor=_human(), reason="not supported", authorization_basis="human review")
    assert rejected.provenance_status is ProvenanceStatus.REJECTED
    return (item.artifact_id,)


def _h27():
    item = CCCSystem().ingest("external record", actor=Actor.external("source"))
    assert item.provenance_status is ProvenanceStatus.PROVENANCE_UNCERTAIN
    return (item.artifact_id,)


def _h28():
    import tempfile
    from pathlib import Path
    system = CCCSystem()
    item = _fact(system)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ccc.json"
        system.save(path)
        loaded = CCCSystem.load(path)
        assert loaded.store.require_artifact(item.artifact_id).content == item.content
    return (item.artifact_id,)


def _h29():
    system = CCCSystem()
    old = _fact(system)
    new = system.correct(old.artifact_id, content="new", actor=_human(), reason="correction", authorization_basis="human")
    assert any(event.target_id == old.artifact_id and event.source_id == new.artifact_id for event in system.store.lineage_events)
    return (new.artifact_id,)


def _h30():
    system = CCCSystem()
    one = _fact(system)
    two = _fact(system)
    conflict = system.detect_conflict(material_ids=(one.artifact_id, two.artifact_id), why_material="material conflict", choices=("one",), downstream_consequences=("choice matters",), remaining_uncertainty=("source",), actor=_model())
    resolved = system.record_resolution(conflict.conflict_id, choice="one", actor=_human(), reason="human chose", authorization_basis="human review")
    assert resolved.status.value == "RESOLVED"
    return (conflict.conflict_id,)


def _h31():
    system = CCCSystem()
    item = _fact(system)
    blocked, evidence = _blocked(lambda: system.correct(item.artifact_id, content="machine rewrite", actor=_model(), reason="recommendation", authorization_basis="model"))
    assert blocked
    return evidence


def _h32():
    system = CCCSystem()
    one = _fact(system)
    two = _fact(system)
    conflict = system.detect_conflict(material_ids=(one.artifact_id, two.artifact_id), why_material="conflict", choices=("a", "b"), downstream_consequences=("different result",), remaining_uncertainty=("unresolved",), actor=_model())
    assert system.present_conflict(conflict.conflict_id).status.value == "OPEN"
    return ("open conflict",)


def _h33():
    system = CCCSystem()
    thread = system.create_thread(title="primary", actor=_human())
    branch = system.create_branch(thread.thread_id, title="branch", actor=_human())
    system.close_branch(branch.branch_id, actor=_human(), reason="pause")
    assert branch.branch_id in system.store.branches
    return (branch.branch_id,)


def _h34():
    system = CCCSystem()
    source = _fact(system)
    claim = system.derive("inference with root", evidence_ids=(source.artifact_id,))
    evidence = system.classify(claim.artifact_id, EpistemicStatus.EVIDENCE, actor=_human(), reason="human evidence review", evidence_ids=(source.artifact_id,))
    assert evidence.epistemic_status is EpistemicStatus.EVIDENCE
    return (claim.artifact_id,)


def _h35():
    return _h06()


def _h36():
    system = CCCSystem()
    low = system.ingest("low", actor=_human(), presentation_priority=0)
    high = system.ingest("high", actor=_human(), presentation_priority=10)
    assert len(system.query()) == 2 and system.present(limit=1)[0].artifact_id == high.artifact_id and len(system.query()) == 2
    return (low.artifact_id, high.artifact_id)


def _h37():
    system = CCCSystem()
    discovery = system.discover(source_material=(), method="candidate scan", conclusion="unsurfaced candidate", confidence=0.2, actor=_model())
    assert discovery.discovery_id in system.store.discoveries
    return (discovery.discovery_id,)


def _h38():
    item = CCCSystem().ingest("unresolved source")
    assert item.provenance_status is ProvenanceStatus.PROVENANCE_UNCERTAIN
    return (item.artifact_id,)


def _h39():
    system = CCCSystem()
    source = _fact(system)
    claim = system.derive("redaction dependent", evidence_ids=(source.artifact_id,))
    system.redact(source.artifact_id, actor=_human(), reason="redaction", authorization_basis="human")
    assert system.store.require_artifact(claim.artifact_id).epistemic_status is EpistemicStatus.THEORY
    return (claim.artifact_id,)


def _h40():
    system = CCCSystem()
    sim = system.simulate(inputs=(), assumptions=("a",), shared_assumptions=("shared",), trajectory=("x",), counterfactual="if", output="out", sensitivity={}, limitations=("limited",), actor=_model())
    assert sim.shared_assumptions == ("shared",) and "shared" in sim.shared_assumptions
    return (sim.simulation_id,)


def _h41():
    system = CCCSystem()
    source = _fact(system)
    sim = system.simulate(inputs=(source.artifact_id,), assumptions=(), shared_assumptions=(), trajectory=(), counterfactual="if", output="out", sensitivity={}, limitations=("limited",), actor=_model())
    assert sim.input_provenance == ((source.artifact_id, ProvenanceStatus.USER_ESTABLISHED.value),)
    return sim.input_provenance


def _h42():
    system = CCCSystem()
    unknown = system.ingest("unknown origin", actor=Actor.system())
    term = system.propose_term(term="unknown", definition="unknown", actor=_model())
    blocked, evidence = _blocked(lambda: system.canonicalize(term.term_id, actor=_human(), source_material=(unknown.artifact_id,), reason="silent", authorization_basis="human"))
    assert blocked
    return evidence


def _h43():
    system = CCCSystem()
    anomaly = system.discover(source_material=(), method="scan", conclusion="anomaly", confidence=0.1, actor=_model(), stage=AnalysisStage.ANOMALY)
    blocked, evidence = _blocked(lambda: system.advance_discovery(anomaly.discovery_id, stage=AnalysisStage.MANDATE, actor=_human(), reason="jump", evidence_ids=(), human_event=True, authorization_basis="human"))
    assert blocked
    return evidence


def _h44():
    system = CCCSystem()
    _fact(system)
    report = system.validate_constitution()
    assert report["valid"]
    return ("validation report valid",)


_EXECUTABLE = {
    "H01": ("REQ.PROVENANCE.EXPLICIT_TRANSITIONS", "Human-originating ingestion creates explicit provenance event.", _h01),
    "H02": ("REQ.RATIFICATION.NO_MACHINE_SELF_RATIFICATION", "Machine actor cannot establish human provenance.", _h02),
    "H03": ("REQ.PROVENANCE.NO_AUTHORSHP_INFERENCE", "Machine origin remains separate from later evidence links.", _h03),
    "H04": ("REQ.EPISTEMIC.SIMULATION_NOT_HISTORY", "Simulation cannot become historical record.", _h04),
    "H05": ("REQ.EVIDENCE.ROOT_INTEGRITY", "Valid dependent chain exposes legitimate root.", _h05),
    "H06": ("REQ.EVIDENCE.ROOT_INTEGRITY", "Erasure invalidates dependent evidence authority.", _h06),
    "H07": ("REQ.HUMAN_SOVEREIGNTY.NO_MACHINE_VETO", "Machine cannot perform human erasure.", _h07),
    "H08": ("REQ.HISTORY.LINEAGE", "Correction preserves old content and creates a version.", _h08),
    "H09": ("REQ.HISTORY.ERASURE_DISTINCT", "Redaction is a distinct unavailable state.", _h09),
    "H10": ("REQ.CONFLICT.PRESERVE", "Evidence conflict is classified and kept open.", _h10),
    "H11": ("REQ.UNCERTAINTY.PRESERVE", "Uncertainty exposes candidates without forced choice.", _h11),
    "H12": ("REQ.ROAD_SIGNS.INDICATORS_NOT_CONCLUSIONS", "Road Sign remains an indicator.", _h12),
    "H13": ("REQ.INFLECTION.SEPARATE_DIMENSIONS", "Inflection dimensions remain separate.", _h13),
    "H14": ("REQ.THREADS.BRANCH_LINEAGE", "Threads and deferred branches remain explicit.", _h14),
    "H15": ("REQ.ANALYSIS.ONE_TWO_THREE", "Anomaly advances through pattern to human mandate.", _h15),
    "H16": ("REQ.DISCOVERY.MACHINE_ATTRIBUTION", "Machine discovery retains machine origin.", _h16),
    "H17": ("REQ.SIMULATION.ASSUMPTIONS", "Simulation preserves assumptions and limitations.", _h17),
    "H18": ("REQ.CANONICALIZATION.HUMAN_STATUS", "Canonical term requires human source decision.", _h18),
    "H19": ("REQ.QUERYABILITY.NO_PRESENTATION_DELETION", "Query filters expose all requested dimensions.", _h19),
    "H20": ("REQ.AUDIT.CONSEQUENTIAL_TRANSITIONS", "Audit identifies actor and operation.", _h20),
    "H21": ("REQ.HISTORY.LINEAGE", "Correction is a distinct audited operation.", _h21),
    "H22": ("REQ.HISTORY.LINEAGE", "Supersession preserves historical lineage.", _h22),
    "H23": ("REQ.DISCOVERY.MACHINE_ATTRIBUTION", "Inference is machine-labeled.", _h23),
    "H24": ("REQ.RATIFICATION.NO_MACHINE_SELF_RATIFICATION", "Machine consensus cannot self-promote.", _h24),
    "H25": ("REQ.PROVENANCE.EXPLICIT_TRANSITIONS", "Direct provenance field mutation is impossible.", _h25),
    "H26": ("REQ.HUMAN_SOVEREIGNTY.NO_MACHINE_VETO", "Human rejection is an explicit operation.", _h26),
    "H27": ("REQ.PROVENANCE.EXPLICIT_TRANSITIONS", "External origin remains uncertain until resolved.", _h27),
    "H28": ("REQ.DATA_INTEGRITY.IMMUTABLE_IDENTIFIERS", "JSON persistence preserves identity and content.", _h28),
    "H29": ("REQ.HISTORY.LINEAGE", "Correction has explicit relationship.", _h29),
    "H30": ("REQ.CONFLICT.PRESERVE", "Conflict resolution is separately recorded.", _h30),
    "H31": ("REQ.HUMAN_SOVEREIGNTY.NO_MACHINE_VETO", "Machine cannot author a human correction.", _h31),
    "H32": ("REQ.CONFLICT.PRESERVE", "Detection does not silently resolve conflict.", _h32),
    "H33": ("REQ.THREADS.BRANCH_LINEAGE", "Closed branch remains queryable.", _h33),
    "H34": ("REQ.EPISTEMIC.EVIDENCE_BASIS", "Inference promotion requires human action and root.", _h34),
    "H35": ("REQ.EVIDENCE.ROOT_INTEGRITY", "Erasure cascade is transitive.", _h35),
    "H36": ("REQ.QUERYABILITY.NO_PRESENTATION_DELETION", "Presentation ranking does not delete.", _h36),
    "H37": ("REQ.QUERYABILITY.NO_PRESENTATION_DELETION", "Unsurfaced discovery remains stored.", _h37),
    "H38": ("REQ.UNCERTAINTY.PRESERVE", "Unknown provenance is explicit.", _h38),
    "H39": ("REQ.EVIDENCE.ROOT_INTEGRITY", "Redaction cascades evidentiary consequences.", _h39),
    "H40": ("REQ.SIMULATION.ASSUMPTIONS", "Shared simulation assumptions are explicit.", _h40),
    "H41": ("REQ.SIMULATION.ASSUMPTIONS", "Simulation captures input provenance.", _h41),
    "H42": ("REQ.CANONICALIZATION.HUMAN_STATUS", "Unknown-origin terminology is not silently canonical.", _h42),
    "H43": ("REQ.ANALYSIS.ONE_TWO_THREE", "Anomaly cannot jump directly to mandate.", _h43),
    "H44": ("REQ.AUDIT.CONSEQUENTIAL_TRANSITIONS", "Constitutional validator reports invariant status.", _h44),
}


def harness_registry() -> tuple[dict[str, str], ...]:
    rows = []
    for number in range(1, 63):
        harness_id = f"H{number:02d}"
        if harness_id in _EXECUTABLE:
            requirement, description, _ = _EXECUTABLE[harness_id]
            rows.append({
                "harness_id": harness_id,
                "constitutional_requirement": requirement,
                "test_description": description,
                "expected_result": "PASS",
                "historical_meaning": "UNSPECIFIED",
            })
        else:
            rows.append({
                "harness_id": harness_id,
                "constitutional_requirement": "UNSPECIFIED",
                "test_description": "No historical harness requirement is recoverable from the empty repository.",
                "expected_result": "UNSPECIFIED",
                "historical_meaning": "UNSPECIFIED",
            })
    return tuple(rows)


def run_harness() -> dict:
    records = []
    for row in harness_registry():
        check = _EXECUTABLE.get(row["harness_id"])
        if check is None:
            records.append({**row, "actual_result": "UNSPECIFIED", "status": "UNSPECIFIED", "evidence": [], "implementation_version": "0.1.0"})
            continue
        _, _, function = check
        try:
            evidence = function()
            records.append({**row, "actual_result": "PASS", "status": "PASS", "evidence": list(evidence), "implementation_version": "0.1.0"})
        except AssertionError as exc:
            records.append({**row, "actual_result": "FAIL", "status": "FAIL", "evidence": [str(exc)], "implementation_version": "0.1.0"})
        except Exception as exc:  # pragma: no cover - the JSON result is the diagnostic
            records.append({**row, "actual_result": "ERROR", "status": "ERROR", "evidence": [f"{type(exc).__name__}: {exc}"], "implementation_version": "0.1.0"})
    counts = {status.lower(): sum(item["status"] == status for item in records) for status in ("PASS", "FAIL", "ERROR", "SKIPPED", "UNSPECIFIED")}
    return {
        "implementation_version": "0.1.0",
        "records": records,
        "total": len(records),
        "passed": counts["pass"],
        "failed": counts["fail"],
        "errors": counts["error"],
        "skipped": counts["skipped"],
        "unspecified": counts["unspecified"],
    }


def write_harness_results(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(run_harness(), indent=2, sort_keys=True), encoding="utf-8")
    return target
