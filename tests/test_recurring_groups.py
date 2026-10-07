"""CCCSystem.recurring_groups: listing the groups CCC already built.

Read-only. Built from the same links record_external_finding writes, so the
listing cannot disagree with CCC's own anomaly -> pattern decisions.
Fixture texts are the verified ones from tests/test_recurrence.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pytest

from ccc import Actor, AnalysisStage, CCCSystem, RecurringGroup
from ccc import recurring as recurring_module
from ccc import system as system_module
from cccb import TextMatcher

GOV_1 = "governance terminology escalated into grandiose theological jargon"
GOV_2 = "grandiose theological jargon: the governance terminology escalated once again"
GOV_3 = "escalated governance terminology, grandiose theological jargon yet another time"
OTHER = "queue wait times exceeded the friction threshold on the billing line"


@dataclass(frozen=True)
class _Finding:
    conclusion: str
    method: str
    source_material: Tuple[str, ...]
    confidence: Optional[float]
    verified: bool
    evidence: Tuple[Tuple[str, str], ...] = ()
    event_start_date: Optional[str] = None
    event_end_date: Optional[str] = None


def _finding(text, source, date=None):
    return _Finding(conclusion=text, method="test.search", source_material=(source,),
                    confidence=0.6, verified=True, evidence=((source, text),), event_start_date=date,
                    event_end_date=date)


@pytest.fixture
def system():
    return CCCSystem(text_matcher=TextMatcher(), private_source_markers=())


ACTOR = Actor.model("observer")


def test_empty_store_has_no_groups(system):
    assert system.recurring_groups() == ()


def test_three_occurrences_form_one_pattern_group_that_needs_review(system):
    d1 = system.record_external_finding(_finding(GOV_1, "m.md", "2026-03-01"), actor=ACTOR)
    d2 = system.record_external_finding(_finding(GOV_2, "y.md", "2026-05-01"), actor=ACTOR)
    d3 = system.record_external_finding(_finding(GOV_3, "g.md", "2026-07-01"), actor=ACTOR)
    (group,) = system.recurring_groups()
    assert isinstance(group, RecurringGroup)
    assert group.representative_id == d1.discovery_id
    assert group.stage is AnalysisStage.PATTERN
    assert set(group.occurrences) == {d1.discovery_id, d2.discovery_id, d3.discovery_id}
    assert group.occurrence_count == 3
    assert group.needs_human_review
    assert (group.first_seen, group.last_seen) == ("2026-03-01", "2026-07-01")
    assert group.conclusion == GOV_1


def test_two_occurrences_are_a_pattern_not_yet_flagged_for_review(system):
    system.record_external_finding(_finding(GOV_1, "m.md"), actor=ACTOR)
    system.record_external_finding(_finding(GOV_2, "y.md"), actor=ACTOR)
    (group,) = system.recurring_groups()
    assert group.stage is AnalysisStage.PATTERN
    assert group.occurrence_count == 2
    assert not group.needs_human_review


def test_unrelated_findings_are_separate_groups_most_serious_first(system):
    system.record_external_finding(_finding(OTHER, "q.md"), actor=ACTOR)
    system.record_external_finding(_finding(GOV_1, "m.md"), actor=ACTOR)
    system.record_external_finding(_finding(GOV_2, "y.md"), actor=ACTOR)
    groups = system.recurring_groups()
    assert [g.stage for g in groups] == [AnalysisStage.PATTERN, AnalysisStage.ANOMALY]
    assert groups[1].conclusion == OTHER
    assert groups[1].occurrence_count == 1
    assert len(system.recurring_groups(min_occurrences=2)) == 1


def test_duplicates_are_listed_but_never_counted(system):
    first = system.record_external_finding(_finding(GOV_1 + " during the arc", "a.md"), actor=ACTOR)
    again = system.record_external_finding(_finding(GOV_1 + " during the arc", "b.md"), actor=ACTOR)
    (group,) = system.recurring_groups()
    assert group.occurrences == (first.discovery_id,)
    assert group.duplicates == (again.discovery_id,)
    assert group.stage is AnalysisStage.ANOMALY


def test_listing_writes_nothing(system):
    system.record_external_finding(_finding(GOV_1, "m.md"), actor=ACTOR)
    before = (dict(system.store.discoveries), len(system.audit_trail.all()), dict(system.store.road_signs))
    system.recurring_groups()
    system.recurring_groups(min_occurrences=2)
    after = (dict(system.store.discoveries), len(system.audit_trail.all()), dict(system.store.road_signs))
    assert before == after


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_min_occurrences_must_be_a_positive_integer(system, bad):
    with pytest.raises(ValueError):
        system.recurring_groups(min_occurrences=bad)


def test_constants_match_the_recording_path():
    assert recurring_module._DUPLICATE_METHOD_MARKER == system_module._DUPLICATE_METHOD_MARKER
    for stage, rank in system_module._STAGE_RANK.items():
        assert recurring_module._STAGE_RANK[stage] == rank
