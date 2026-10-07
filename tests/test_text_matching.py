"""The plugged-in text matcher (ccc.text_matching): CCC's guard, CCCb's measurement.

CCC owns what a match means; the matcher owns the measurement. These tests pin
the boundary: no matcher means no machine findings (loudly), a malformed answer
is refused rather than recorded, and CCC itself never imports CCCb.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pytest

import ccc
from ccc import Actor, AnalysisStage, CCCSystem
from ccc.text_matching import TextMatcher as MatcherShape
from ccc.text_matching import TextMatcherMissing
from cccb import TextMatcher


@dataclass(frozen=True)
class _Finding:
    conclusion: str
    method: str
    source_material: Tuple[str, ...]
    confidence: Optional[float]
    verified: bool
    evidence: Tuple[Tuple[str, str], ...] = ()


FINDING = _Finding(
    conclusion="The governance terminology inflated again into grandiose jargon.",
    method="ecology.search", source_material=("notes.md",), confidence=0.6, verified=True,
)
MODEL = Actor.model("ecology")


def test_no_matcher_means_no_machine_findings_and_nothing_is_written():
    system = CCCSystem()
    with pytest.raises(TextMatcherMissing, match="cccb.TextMatcher"):
        system.record_external_finding(FINDING, actor=MODEL)
    assert not system.store.discoveries
    assert not system.store.audit_events


def test_everything_else_works_without_a_matcher():
    system = CCCSystem()
    artifact = system.ingest("A human note.", actor=Actor.human())
    assert system.store.require_artifact(artifact.artifact_id).available


def test_with_cccb_attached_findings_record():
    system = CCCSystem(text_matcher=TextMatcher())
    record = system.record_external_finding(FINDING, actor=MODEL)
    assert record.stage is AnalysisStage.ANOMALY


def test_cccb_matcher_has_the_shape_ccc_needs():
    assert isinstance(TextMatcher(), MatcherShape)


@pytest.mark.parametrize("bad", [object(), "cccb", {"add": None}])
def test_a_matcher_without_the_shape_is_refused_at_construction(bad):
    with pytest.raises(TypeError):
        CCCSystem(text_matcher=bad)


class _Lying:
    """A matcher whose answers name things CCC never gave it, or are malformed."""

    def __init__(self, duplicate=None, recurrence=None):
        self.duplicate, self.recurrence = duplicate, recurrence

    def add(self, item_id, text):
        pass

    def duplicate_of(self, text):
        return self.duplicate

    def recurrence_of(self, text):
        return self.recurrence


@pytest.mark.parametrize("matcher", [
    _Lying(duplicate=("never-seen", 1e-12, 80)),
    _Lying(duplicate=("x", 1e-12)),
    _Lying(duplicate=["x", 1e-12, 80]),
    _Lying(recurrence=("never-seen", 0.9, (("never-seen", 0.9),))),
    _Lying(recurrence=("x", 0.9, ())),
    _Lying(recurrence=("x", "high", (("x", 0.9),))),
])
def test_a_malformed_or_invented_answer_is_refused_not_recorded(matcher):
    system = CCCSystem(text_matcher=matcher)
    with pytest.raises(ValueError, match="text matcher"):
        system.record_external_finding(FINDING, actor=MODEL)
    assert not system.store.discoveries


def test_reopened_store_feeds_the_new_matcher(tmp_path):
    path = tmp_path / "state.json"
    first = CCCSystem(text_matcher=TextMatcher(), persistence_path=path)
    original = first.record_external_finding(FINDING, actor=MODEL)
    first.save()
    reopened = CCCSystem.load(path, text_matcher=TextMatcher())
    again = reopened.record_external_finding(FINDING, actor=MODEL)
    assert original.discovery_id in again.relationships


def test_ccc_never_imports_cccb():
    for path in Path(ccc.__file__).parent.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                assert name.split(".")[0] != "cccb", f"{path} imports {name}"
