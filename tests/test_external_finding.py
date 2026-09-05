"""Recording a finding from an external evidence-search system (Ecology's
FindingRecord, or anything structurally shaped like it) as a CCC anomaly.

No import of Ecology anywhere here -- the contract is structural (any object
with .conclusion, .method, .source_material, .confidence, .verified), and
that's proven by using a plain stand-in class below instead of the real one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pytest

from ccc import Actor, AnalysisStage, CCCSystem, EpistemicStatus, ProvenanceStatus


@dataclass(frozen=True)
class _StandInFinding:
    """Structurally identical to ecology.finding.FindingRecord, deliberately
    not imported from there -- this is what "no dependency, just a shared
    shape" actually looks like."""
    conclusion: str
    method: str
    source_material: Tuple[str, ...]
    confidence: Optional[float]
    verified: bool
    evidence: Tuple[Tuple[str, str], ...] = ()


def _verified_finding(confidence=0.6, source_material=("ecology/README.md", "ecology/ecology.py"),
                       evidence=()):
    return _StandInFinding(
        conclusion="Ecology's README oversells what its code does.",
        method="ecology.rag_engine.generate_response(model=llama3.2, n_results=5)",
        source_material=source_material,
        confidence=confidence,
        verified=True,
        evidence=evidence,
    )


def test_verified_finding_is_recorded_as_an_anomaly():
    system = CCCSystem()
    record = system.record_external_finding(
        _verified_finding(), actor=Actor.model("claude-session"),
    )
    assert record.stage is AnalysisStage.ANOMALY
    assert record.provenance_status is ProvenanceStatus.ASSISTANT_PROPOSED
    assert record.epistemic_status is EpistemicStatus.INFERENCE
    assert record.machine_origin is True
    assert record.confidence == 0.6
    assert record.source_material == ("ecology/README.md", "ecology/ecology.py")


def test_unverified_finding_is_refused_not_recorded_at_lower_confidence():
    system = CCCSystem()
    unverified = _StandInFinding(
        conclusion="", method="m", source_material=(), confidence=None, verified=False,
    )
    with pytest.raises(ValueError, match="unverified"):
        system.record_external_finding(unverified, actor=Actor.model("claude-session"))


def test_human_actor_is_rejected_for_an_external_finding():
    """Nothing external to CCC gets to assert a human-established fact."""
    system = CCCSystem()
    with pytest.raises(ValueError, match="MODEL or SYSTEM"):
        system.record_external_finding(_verified_finding(), actor=Actor.human("william"))


def test_system_actor_is_also_accepted():
    system = CCCSystem()
    record = system.record_external_finding(
        _verified_finding(), actor=Actor.system("ecology-pipeline"),
    )
    assert record.machine_origin is True


def test_verified_true_with_no_source_material_is_self_inconsistent():
    system = CCCSystem()
    broken = _StandInFinding(
        conclusion="something", method="m", source_material=(), confidence=0.5, verified=True,
    )
    with pytest.raises(ValueError, match="self-inconsistent"):
        system.record_external_finding(broken, actor=Actor.model("m"))


def test_confidence_outside_unit_interval_is_refused():
    system = CCCSystem()
    broken = _verified_finding(confidence=1.5)
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        system.record_external_finding(broken, actor=Actor.model("m"))


def test_evidence_pairs_become_supporting_evidence_not_a_collapsed_number():
    system = CCCSystem()
    record = system.record_external_finding(
        _verified_finding(evidence=(
            ("ecology/README.md", "no persisted identity, provenance, or temporal model yet"),
            ("ecology/ecology.py", "ActiveKnowledgeObject"),
        )),
        actor=Actor.model("m"),
    )
    assert record.supporting_evidence == (
        "ecology/README.md: no persisted identity, provenance, or temporal model yet",
        "ecology/ecology.py: ActiveKnowledgeObject",
    )


_LONG_EXCERPT = (
    "Ecology's README describes a living, branching, converging memory "
    "model; its actual code is a retrieval pipeline with no identity, "
    "provenance, or temporal model of any kind whatsoever."
)  # 160 chars -- long enough that an accidental match is not plausible


def test_identical_long_content_is_recorded_and_tagged_as_a_duplicate():
    """A duplicate is still recorded -- not silently absorbed -- so the
    re-observation is itself an auditable fact. It's tagged via
    relationships pointing at what it matches, not returned as the same
    record, and never let it look like an independent second occurrence."""
    system = CCCSystem()
    first = system.record_external_finding(
        _verified_finding(evidence=(("a.md", _LONG_EXCERPT),)), actor=Actor.model("m"),
    )
    second = system.record_external_finding(
        _verified_finding(source_material=("b.md",), evidence=(("b.md", _LONG_EXCERPT),)),
        actor=Actor.model("m"),
    )
    assert second.discovery_id != first.discovery_id
    assert second.relationships == (first.discovery_id,)
    assert "anti-probability" in second.method
    assert len(system.store.discoveries) == 2  # both on the record, neither absorbed


def test_unrelated_long_content_is_not_flagged_as_a_duplicate():
    system = CCCSystem()
    first = system.record_external_finding(
        _verified_finding(evidence=(("a.md", _LONG_EXCERPT),)), actor=Actor.model("m"),
    )
    second = system.record_external_finding(
        _verified_finding(
            source_material=("b.md",),
            evidence=(("b.md", "Something entirely different about a completely unrelated topic."),),
        ),
        actor=Actor.model("m"),
    )
    assert second.relationships == ()
    assert "anti-probability" not in second.method


def test_short_shared_phrase_is_not_falsely_flagged_as_a_duplicate():
    """A short common phrase matching is unremarkable, not evidence of
    duplication -- the floor exists so the entropy formula isn't misapplied
    to noise-length overlaps."""
    system = CCCSystem()
    system.record_external_finding(
        _verified_finding(evidence=(("a.md", "the system works well"),)), actor=Actor.model("m"),
    )
    second = system.record_external_finding(
        _verified_finding(source_material=("b.md",),
                           evidence=(("b.md", "everyone agrees the system works well today"),)),
        actor=Actor.model("m"),
    )
    assert second.relationships == ()


def test_duplicates_are_audited_not_silently_absorbed():
    """The earlier version of this fix returned the existing record with no
    audit trail at all -- a duplicate submission left zero trace. Every
    finding, duplicate or not, now goes through discover() and is audited."""
    system = CCCSystem()
    system.record_external_finding(
        _verified_finding(evidence=(("a.md", _LONG_EXCERPT),)), actor=Actor.model("m"),
    )
    system.record_external_finding(
        _verified_finding(source_material=("b.md",), evidence=(("b.md", _LONG_EXCERPT),)),
        actor=Actor.model("m"),
    )
    discover_events = [e for e in system.audit() if e.operation == "DISCOVER"]
    assert len(discover_events) == 2
