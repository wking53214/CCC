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


def _verified_finding(confidence=0.6):
    return _StandInFinding(
        conclusion="Ecology's README oversells what its code does.",
        method="ecology.rag_engine.generate_response(model=llama3.2, n_results=5)",
        source_material=("ecology/README.md", "ecology/ecology.py"),
        confidence=confidence,
        verified=True,
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
