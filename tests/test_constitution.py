from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ccc import (
    Actor,
    AnalysisStage,
    CCCSystem,
    EpistemicStatus,
    ProvenanceStatus,
    RelationshipType,
    RoadSignCategory,
)
from ccc.errors import ConstitutionViolation


@pytest.fixture
def actors():
    return Actor.human("human"), Actor.model("model"), Actor.system("system")


@pytest.fixture
def fact():
    system = CCCSystem()
    item = system.ingest(
        "human record",
        actor=Actor.human("human"),
        epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
        topics=("continuity",),
        instrument="note",
    )
    return system, item


def test_chain_a_keeps_machine_origin_after_human_adoption(fact):
    system, source = fact
    proposal = system.derive("machine inference", actor=Actor.model("model"), evidence_ids=(source.artifact_id,))

    with pytest.raises(ConstitutionViolation):
        system.accept(
            proposal.artifact_id,
            actor=Actor.model("model"),
            reason="models agreed",
            authorization_basis="machine consensus",
        )

    adopted = system.accept(
        proposal.artifact_id,
        actor=Actor.human("human"),
        reason="human reviewed proposal",
        authorization_basis="explicit human adoption",
        evidence_ids=(source.artifact_id,),
    )
    assert adopted.origin.kind.value == "MODEL"
    assert adopted.provenance_status is ProvenanceStatus.USER_ACCEPTED
    assert any(event.human_originating for event in system.provenance.history(adopted.artifact_id))


def test_human_container_does_not_silently_turn_machine_source_into_evidence(fact):
    system, source = fact
    machine = system.derive("machine concept", actor=Actor.model("model"), evidence_ids=(source.artifact_id,))
    container = system.ingest(
        "human document containing the machine concept",
        actor=Actor.human("human"),
        source_material=(machine.artifact_id,),
        epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
    )
    assert container.machine_influenced
    assert container.provenance_status is ProvenanceStatus.PROVENANCE_UNCERTAIN
    assert system.evidence_root(container.artifact_id) == ()


def test_direct_provenance_mutation_is_not_possible(fact):
    _, source = fact
    with pytest.raises(FrozenInstanceError):
        source.provenance_status = ProvenanceStatus.REJECTED


def test_machine_cannot_ingest_historical_record_or_evidence():
    system = CCCSystem()
    with pytest.raises(ConstitutionViolation):
        system.ingest("machine history", actor=Actor.model("model"), epistemic_status=EpistemicStatus.HISTORICAL_RECORD)
    with pytest.raises(ConstitutionViolation):
        system.ingest("machine evidence", actor=Actor.system("system"), epistemic_status=EpistemicStatus.EVIDENCE)


def test_epistemic_promotions_need_evidence_and_human_action(fact):
    system, source = fact
    inference = system.derive("inference", actor=Actor.model("model"))
    with pytest.raises(ConstitutionViolation):
        system.classify(inference.artifact_id, EpistemicStatus.EVIDENCE, actor=Actor.human("human"), reason="unsupported")
    with pytest.raises(ConstitutionViolation):
        system.classify(inference.artifact_id, EpistemicStatus.EVIDENCE, actor=Actor.model("model"), reason="model says evidence", evidence_ids=(source.artifact_id,))

    system.attach_evidence(inference.artifact_id, source.artifact_id, actor=Actor.system("system"), rationale="source supports inference")
    evidence = system.classify(
        inference.artifact_id,
        EpistemicStatus.EVIDENCE,
        actor=Actor.human("human"),
        reason="human reviewed source",
        evidence_ids=(source.artifact_id,),
    )
    assert evidence.epistemic_status is EpistemicStatus.EVIDENCE


def test_simulation_cannot_be_promoted_to_history():
    system = CCCSystem()
    simulation = system.ingest("trajectory", actor=Actor.model("model"), epistemic_status=EpistemicStatus.SIMULATION)
    with pytest.raises(ConstitutionViolation):
        system.classify(simulation.artifact_id, EpistemicStatus.HISTORICAL_RECORD, actor=Actor.human("human"), reason="pretend history")


def test_evidence_root_and_transitive_erasure_cascade(fact):
    system, root = fact
    first = system.derive("first inference", actor=Actor.model("model"), evidence_ids=(root.artifact_id,))
    second = system.derive("second inference", actor=Actor.model("model"), evidence_ids=(first.artifact_id,))
    assert system.evidence_root(second.artifact_id) == (root.artifact_id,)

    system.erase(root.artifact_id, actor=Actor.human("human"), reason="erase root", authorization_basis="human request")

    assert system.evidence_root(second.artifact_id) == ()
    assert system.store.require_artifact(first.artifact_id).epistemic_status is EpistemicStatus.THEORY
    assert system.store.require_artifact(second.artifact_id).epistemic_status is EpistemicStatus.THEORY
    assert not system.store.links_for_evidence(root.artifact_id, active_only=True)


def test_rejecting_an_evidence_root_cascades_to_dependents(fact):
    system, root = fact
    claim = system.derive("dependent claim", actor=Actor.model("model"), evidence_ids=(root.artifact_id,))
    system.reject(root.artifact_id, actor=Actor.human("human"), reason="source rejected", authorization_basis="human review")
    assert system.evidence_root(claim.artifact_id) == ()
    assert system.store.require_artifact(claim.artifact_id).epistemic_status is EpistemicStatus.THEORY


def test_redaction_is_not_correction_or_supersession(fact):
    system, source = fact
    redacted = system.redact(source.artifact_id, actor=Actor.human("human"), reason="redact", authorization_basis="human request")
    assert redacted.state.value == "REDACTED"
    assert any(event.relationship is RelationshipType.REDACTS for event in system.store.lineage_events)
    assert not any(event.relationship is RelationshipType.CORRECTS for event in system.store.lineage_events)
    assert not any(event.relationship is RelationshipType.SUPERSEDES for event in system.store.lineage_events)


def test_correction_and_supersession_preserve_old_identity(fact):
    system, source = fact
    corrected = system.correct(source.artifact_id, content="corrected", actor=Actor.human("human"), reason="fix typo", authorization_basis="human review")
    superseding = system.supersede(corrected.artifact_id, content="superseding", actor=Actor.human("human"), reason="new record", authorization_basis="human review")
    assert system.store.require_artifact(source.artifact_id).content == "human record"
    assert system.store.require_artifact(corrected.artifact_id).content == "corrected"
    assert superseding.content == "superseding"
    relationships = {event.relationship for event in system.store.lineage_events}
    assert RelationshipType.CORRECTS in relationships
    assert RelationshipType.SUPERSEDES in relationships


def test_machine_cannot_veto_human_erasure(fact):
    system, source = fact
    with pytest.raises(ConstitutionViolation):
        system.erase(source.artifact_id, actor=Actor.model("model"), reason="machine recommendation", authorization_basis="model")
    erased = system.erase(source.artifact_id, actor=Actor.human("human"), reason="human decision", authorization_basis="human request")
    assert erased.state.value == "ERASED"


def test_decision_requires_human_actor_even_when_recommendation_exists(fact):
    system, source = fact
    recommendation = system.derive("recommendation", actor=Actor.model("model"), evidence_ids=(source.artifact_id,))
    with pytest.raises(ConstitutionViolation):
        system.decide("machine decision", actor=Actor.model("model"), reason="recommendation", authorization_basis="model", recommendation_id=recommendation.artifact_id)
    decision = system.decide("human decision", actor=Actor.human("human"), reason="human selected option", authorization_basis="human decision event", recommendation_id=recommendation.artifact_id)
    assert decision.origin.kind.value == "HUMAN"
    assert decision.provenance_status is ProvenanceStatus.USER_ESTABLISHED


def test_uncertainty_is_nonleading_and_resolution_is_explicit():
    system = CCCSystem()
    uncertainty = system.ask(
        context="conflicting origin",
        known=("two records",),
        unknown=("which is primary",),
        candidates=("A", "B"),
        question="Which record, if any, should be treated as primary?",
        actor=Actor.model("model"),
    )
    assert uncertainty.requires_human_resolution
    assert uncertainty.resolved_choice is None
    resolved = system.resolve_uncertainty(uncertainty.uncertainty_id, choice="B", actor=Actor.human("human"), reason="human clarified", authorization_basis="human response")
    assert resolved.resolved_choice == "B"


def test_road_sign_is_observation_not_conclusion():
    system = CCCSystem()
    sign = system.detect_road_sign(observation="a reversal occurred", category=RoadSignCategory.REVERSAL, actor=Actor.model("model"))
    assert not sign.is_conclusion
    system.link_road_sign(sign.road_sign_id, "candidate-1", actor=Actor.system("system"), reason="link for examination")
    assert system.query_road_signs(linked_id="candidate-1")[0].road_sign_id == sign.road_sign_id


def test_inflection_keeps_detection_divergence_sensitivity_significance_separate():
    system = CCCSystem()
    point = system.detect_inflection(directions=("branched",), divergence=0.9, sensitivity=0.1, machine_weight=0.99, actor=Actor.model("model"))
    assert point.significance is None
    resolved = system.resolve_inflection(point.inflection_id, significance="material redirection", actor=Actor.human("human"), reason="human assessed significance", authorization_basis="human review")
    assert resolved.significance == "material redirection"


def test_threads_and_branches_preserve_lineage():
    system = CCCSystem()
    thread = system.create_thread(title="primary", actor=Actor.human("human"))
    branch = system.create_branch(thread.thread_id, title="deferred", actor=Actor.human("human"), deferred=True)
    assert branch.parent_thread_id == thread.thread_id
    assert branch.branch_id in system.store.threads[thread.thread_id].branch_ids
    system.return_to_branch(branch.branch_id, actor=Actor.human("human"), reason="resume deferred work")
    system.resolve_branch(branch.branch_id, actor=Actor.human("human"), reason="branch resolved")
    assert system.store.branches[branch.branch_id].status.value == "RESOLVED"


def test_anomaly_pattern_mandate_requires_human_adoption(fact):
    system, source = fact
    anomaly = system.discover(source_material=(source.artifact_id,), method="scan", conclusion="anomaly", confidence=0.5, actor=Actor.model("model"), stage=AnalysisStage.ANOMALY)
    pattern = system.advance_discovery(anomaly.discovery_id, stage=AnalysisStage.PATTERN, actor=Actor.model("model"), reason="pattern observed")
    with pytest.raises(ConstitutionViolation):
        system.advance_discovery(pattern.discovery_id, stage=AnalysisStage.MANDATE, actor=Actor.model("model"), reason="model mandate", evidence_ids=(source.artifact_id,), human_event=False, authorization_basis="model")
    mandate = system.advance_discovery(pattern.discovery_id, stage=AnalysisStage.MANDATE, actor=Actor.human("human"), reason="human mandate", evidence_ids=(source.artifact_id,), human_event=True, authorization_basis="human mandate event")
    assert mandate.stage is AnalysisStage.MANDATE
    assert mandate.attribution.startswith("HUMAN_ESTABLISHED")


def test_discovery_remains_machine_generated_until_adopted():
    system = CCCSystem()
    discovery = system.discover(source_material=(), method="model scan", conclusion="candidate", confidence=0.3, actor=Actor.model("model"))
    assert discovery.machine_origin
    assert discovery.provenance_status is ProvenanceStatus.ASSISTANT_PROPOSED
    adopted = system.adopt_discovery(discovery.discovery_id, actor=Actor.human("human"), reason="human adopted candidate", authorization_basis="human adoption")
    assert adopted.provenance_status is ProvenanceStatus.USER_ACCEPTED
    assert adopted.machine_origin


def test_simulation_preserves_input_provenance_and_shared_assumptions(fact):
    system, source = fact
    simulation = system.simulate(inputs=(source.artifact_id,), assumptions=("a",), shared_assumptions=("baseline",), trajectory=("x", "y"), counterfactual="if", output="modeled", sensitivity={"a": 0.5}, limitations=("not history",), actor=Actor.model("model"))
    assert simulation.input_provenance == ((source.artifact_id, ProvenanceStatus.USER_ESTABLISHED.value),)
    assert simulation.shared_assumptions == ("baseline",)
    with pytest.raises(ConstitutionViolation):
        system.simulation.promote_to_historical(simulation.simulation_id, actor=Actor.human("human"), reason="invalid")


def test_conflict_presentation_does_not_silently_adjudicate(fact):
    system, first = fact
    second = system.ingest("second human record", actor=Actor.human("human"), epistemic_status=EpistemicStatus.HISTORICAL_RECORD)
    conflict = system.detect_conflict(material_ids=(first.artifact_id, second.artifact_id), why_material="records conflict", choices=("first", "second"), downstream_consequences=("different conclusion",), remaining_uncertainty=("which record",), actor=Actor.model("model"))
    presented = system.present_conflict(conflict.conflict_id)
    assert presented.status.value == "OPEN"
    assert presented.classification.value == "EVIDENCE_VS_EVIDENCE"
    system.request_human_resolution(conflict.conflict_id, actor=Actor.system("system"))
    assert system.store.conflicts[conflict.conflict_id].status.value == "AWAITING_HUMAN"


def test_unknown_origin_term_cannot_be_canonical(fact):
    system, _ = fact
    unknown = system.ingest("unknown source", actor=Actor.system("system"))
    term = system.propose_term(term="unknown", definition="not canonical", actor=Actor.model("model"))
    with pytest.raises(ConstitutionViolation):
        system.canonicalize(term.term_id, actor=Actor.human("human"), source_material=(unknown.artifact_id,), reason="silent promotion", authorization_basis="human")

    canonical = system.propose_term(term="known", definition="canonical", actor=Actor.human("human"), source_material=(unknown.artifact_id,))
    with pytest.raises(ConstitutionViolation):
        system.canonicalize(canonical.term_id, actor=Actor.human("human"), source_material=(unknown.artifact_id,), reason="bad source", authorization_basis="human")


def test_query_presentation_does_not_delete_unsurfaced_records(fact):
    system, _ = fact
    low = system.ingest("low priority", actor=Actor.human("human"), presentation_priority=0)
    high = system.ingest("high priority", actor=Actor.human("human"), presentation_priority=10)
    assert system.present(limit=1) == (high,)
    assert {item.artifact_id for item in system.query()} == {low.artifact_id, high.artifact_id, system.query()[0].artifact_id}


def test_audit_distinguishes_human_system_model_and_rule_explanation(fact):
    system, source = fact
    proposal = system.derive("proposal", actor=Actor.model("model"), evidence_ids=(source.artifact_id,))
    system.detect_road_sign(observation="system observed a signal", category=RoadSignCategory.BREAKTHROUGH, actor=Actor.system("system"))
    system.accept(proposal.artifact_id, actor=Actor.human("human"), reason="adopt", authorization_basis="human event")
    actors = {event.actor.kind.value for event in system.audit()}
    assert {"HUMAN", "MODEL", "SYSTEM"}.issubset(actors)
    trace = system.rules.trace("CCC-RATIFICATION-001")
    assert trace["article"] is None
    assert trace["source"] == "BUILD_DIRECTIVE"


def test_json_persistence_preserves_lineage_and_audit(fact, tmp_path):
    system, source = fact
    replacement = system.correct(source.artifact_id, content="corrected", actor=Actor.human("human"), reason="fix", authorization_basis="human")
    path = system.save(tmp_path / "ccc.json")
    loaded = CCCSystem.load(path)
    assert loaded.store.require_artifact(source.artifact_id).content == source.content
    assert loaded.store.require_artifact(replacement.artifact_id).content == "corrected"
    assert any(event.relationship is RelationshipType.CORRECTS for event in loaded.store.lineage_events)
    assert loaded.audit()
