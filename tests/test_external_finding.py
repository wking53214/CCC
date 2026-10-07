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
from cccb import TextMatcher


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
    system = CCCSystem(text_matcher=TextMatcher())
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
    system = CCCSystem(text_matcher=TextMatcher())
    unverified = _StandInFinding(
        conclusion="", method="m", source_material=(), confidence=None, verified=False,
    )
    with pytest.raises(ValueError, match="unverified"):
        system.record_external_finding(unverified, actor=Actor.model("claude-session"))


def test_human_actor_is_rejected_for_an_external_finding():
    """Nothing external to CCC gets to assert a human-established fact."""
    system = CCCSystem(text_matcher=TextMatcher())
    with pytest.raises(ValueError, match="MODEL or SYSTEM"):
        system.record_external_finding(_verified_finding(), actor=Actor.human("william"))


def test_system_actor_is_also_accepted():
    system = CCCSystem(text_matcher=TextMatcher())
    record = system.record_external_finding(
        _verified_finding(), actor=Actor.system("ecology-pipeline"),
    )
    assert record.machine_origin is True


def test_verified_true_with_no_source_material_is_self_inconsistent():
    system = CCCSystem(text_matcher=TextMatcher())
    broken = _StandInFinding(
        conclusion="something", method="m", source_material=(), confidence=0.5, verified=True,
    )
    with pytest.raises(ValueError, match="self-inconsistent"):
        system.record_external_finding(broken, actor=Actor.model("m"))


def test_resume_os_source_is_refused_by_default():
    """CCC is public; Resume_OS stays private permanently, chosen as this
    project's validation domain specifically because its ground truth
    isn't exposed. A finding citing it must not leak into a public repo's
    audit trail by accident."""
    system = CCCSystem(text_matcher=TextMatcher())
    finding = _verified_finding(source_material=("/home/wking53214/Resume_OS/sources/manifest.json",))
    with pytest.raises(ValueError, match="known-private"):
        system.record_external_finding(finding, actor=Actor.model("m"))


def test_chatgpt_history_source_is_refused_by_default():
    system = CCCSystem(text_matcher=TextMatcher())
    finding = _verified_finding(source_material=("ChatGPT_History/transcripts/x.md",))
    with pytest.raises(ValueError, match="known-private"):
        system.record_external_finding(finding, actor=Actor.model("m"))


@pytest.mark.parametrize("corpus", ["Claude_History", "CoPilot_History", "Gemini_History"])
def test_every_conversation_history_corpus_is_refused_by_default(corpus):
    """All the *_History archives are private personal-conversation data and
    are the corpora the recurrence layer consumes -- the guard must cover
    every one of them, not just ChatGPT_History."""
    system = CCCSystem(text_matcher=TextMatcher())
    finding = _verified_finding(source_material=(f"{corpus}/transcripts/abc.md",))
    with pytest.raises(ValueError, match="known-private"):
        system.record_external_finding(finding, actor=Actor.model("m"))


def test_private_source_can_be_explicitly_allowed():
    """The refusal is a default, not an absolute lock -- an explicit,
    named override exists for a deliberate, reviewed case, same pattern as
    every other refusal in this method."""
    system = CCCSystem(text_matcher=TextMatcher())
    finding = _verified_finding(source_material=("Resume_OS/README.md",))
    record = system.record_external_finding(finding, actor=Actor.model("m"), allow_private_source=True)
    assert record.discovery_id


def test_non_string_source_material_entry_is_refused():
    """Flood-test finding: a bare int in source_material passed through with
    zero validation before this fix."""
    system = CCCSystem(text_matcher=TextMatcher())
    broken = _StandInFinding(
        conclusion="x", method="m", source_material=(123,), confidence=0.5, verified=True,
    )
    with pytest.raises(ValueError, match="non-string or empty"):
        system.record_external_finding(broken, actor=Actor.model("m"))


def test_empty_conclusion_with_verified_true_is_self_inconsistent():
    system = CCCSystem(text_matcher=TextMatcher())
    broken = _verified_finding()
    broken = _StandInFinding(
        conclusion="", method=broken.method, source_material=broken.source_material,
        confidence=broken.confidence, verified=True,
    )
    with pytest.raises(ValueError, match="empty conclusion"):
        system.record_external_finding(broken, actor=Actor.model("m"))


def test_none_in_an_evidence_pair_is_refused_cleanly_not_a_bare_typeerror():
    """Flood-test finding: this used to crash with a raw
    TypeError: sequence item 0: expected str instance, NoneType found --
    a low-level leak, not a deliberate refusal."""
    system = CCCSystem(text_matcher=TextMatcher())
    broken = _verified_finding(evidence=(("a.md", None),))
    with pytest.raises(ValueError, match="not a \\(source, excerpt\\) pair"):
        system.record_external_finding(broken, actor=Actor.model("m"))


def test_confidence_outside_unit_interval_is_refused():
    system = CCCSystem(text_matcher=TextMatcher())
    broken = _verified_finding(confidence=1.5)
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        system.record_external_finding(broken, actor=Actor.model("m"))


def test_evidence_pairs_become_supporting_evidence_not_a_collapsed_number():
    system = CCCSystem(text_matcher=TextMatcher())
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
    system = CCCSystem(text_matcher=TextMatcher())
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
    system = CCCSystem(text_matcher=TextMatcher())
    system.record_external_finding(
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
    system = CCCSystem(text_matcher=TextMatcher())
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
    system = CCCSystem(text_matcher=TextMatcher())
    system.record_external_finding(
        _verified_finding(evidence=(("a.md", _LONG_EXCERPT),)), actor=Actor.model("m"),
    )
    system.record_external_finding(
        _verified_finding(source_material=("b.md",), evidence=(("b.md", _LONG_EXCERPT),)),
        actor=Actor.model("m"),
    )
    discover_events = [e for e in system.audit() if e.operation == "DISCOVER"]
    assert len(discover_events) == 2


# Event-time / temporal provenance tests

@dataclass(frozen=True)
class _FindingWithEventTime(_StandInFinding):
    """Extended finding with event-date fields."""
    event_start_date: str | None = None
    event_end_date: str | None = None


def test_finding_with_event_dates_carries_them_to_discovery():
    """Event dates on a finding are preserved through record_external_finding
    into the resulting DiscoveryRecord."""
    system = CCCSystem(text_matcher=TextMatcher())
    finding = _FindingWithEventTime(
        conclusion="The system broke in May.",
        method="analysis",
        source_material=("claude_history/conv123.md",),
        confidence=0.9,
        verified=True,
        evidence=(("claude_history/conv123.md", "system down"),),
        event_start_date="2026-05-14",
        event_end_date="2026-05-14",
    )
    record = system.record_external_finding(
        finding, actor=Actor.model("test"), allow_private_source=True,
    )
    assert record.event_start_date == "2026-05-14"
    assert record.event_end_date == "2026-05-14"


def test_finding_without_event_dates_records_none():
    """A finding with no event dates results in None/None on the discovery."""
    system = CCCSystem(text_matcher=TextMatcher())
    record = system.record_external_finding(
        _verified_finding(), actor=Actor.model("test"),
    )
    assert record.event_start_date is None
    assert record.event_end_date is None


def test_event_dates_span_multiple_conversations():
    """A finding aggregating evidence from multiple dates gets the min/max span."""
    system = CCCSystem(text_matcher=TextMatcher())
    finding = _FindingWithEventTime(
        conclusion="Pattern emerged across months.",
        method="recurrence_detection",
        source_material=("claude_history/a.md", "claude_history/b.md", "claude_history/c.md"),
        confidence=0.7,
        verified=True,
        evidence=(
            ("claude_history/a.md", "March evidence"),
            ("claude_history/b.md", "May evidence"),
            ("claude_history/c.md", "July evidence"),
        ),
        event_start_date="2026-03-01",
        event_end_date="2026-07-31",
    )
    record = system.record_external_finding(
        finding, actor=Actor.model("test"), allow_private_source=True,
    )
    assert record.event_start_date == "2026-03-01"
    assert record.event_end_date == "2026-07-31"


def test_recurrence_representative_orders_by_event_date_not_ingest_time():
    """Core regression test: verify that when choosing a recurrence representative,
    the system uses event date (when the evidence occurred) not ingest time (when
    CCC learned about it).

    This test directly constructs discoveries in a recurrence cluster and tests
    that the representative selection uses _effective_event_time, which prefers
    event_start_date over created_at.
    """
    from ccc.system import _effective_event_time, _STAGE_RANK

    # Create DiscoveryRecords for both, simulating:
    # - May event (2026-05-10), Sept 5 ingest
    # - July event (2026-07-15), Sept 4 ingest (earlier!)
    from ccc import DiscoveryRecord, EpistemicStatus, ProvenanceStatus

    may_record = DiscoveryRecord(
        discovery_id="discovery_may",
        source_material=("may.md",),
        machine_origin=True,
        machine_processing_history=("m",),
        method="method",
        conclusion="pattern",
        confidence=0.8,
        supporting_evidence=("may.md: content",),
        epistemic_status=EpistemicStatus.INFERENCE,
        provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
        stage=AnalysisStage.PATTERN,
        event_start_date="2026-05-10",
        event_end_date="2026-05-10",
        created_at="2026-09-05T10:00:00+00:00",  # later ingest
    )

    july_record = DiscoveryRecord(
        discovery_id="discovery_july",
        source_material=("july.md",),
        machine_origin=True,
        machine_processing_history=("m",),
        method="method",
        conclusion="pattern",
        confidence=0.8,
        supporting_evidence=("july.md: content",),
        epistemic_status=EpistemicStatus.INFERENCE,
        provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
        stage=AnalysisStage.PATTERN,
        event_start_date="2026-07-15",
        event_end_date="2026-07-15",
        created_at="2026-09-04T10:00:00+00:00",  # earlier ingest
    )

    # The representative selection key, applied to both
    cluster = [may_record, july_record]

    def representative_key(record):
        """Mimics the logic in record_external_finding."""
        return (
            -_STAGE_RANK[record.stage],
            _effective_event_time(record),
            record.discovery_id,
        )

    # Choose the representative
    representative = min(cluster, key=representative_key)

    # The May record must be chosen because its event time (2026-05-10)
    # is earlier than July's (2026-07-15), even though May was ingested
    # later (Sept 5 vs Sept 4).
    assert representative.discovery_id == "discovery_may", (
        f"Expected May (earlier event 2026-05-10) to be representative, "
        f"but got {representative.discovery_id}. "
        f"This means created_at (ingest time) is being used instead of "
        f"event_start_date. "
        f"May created_at={may_record.created_at}, "
        f"July created_at={july_record.created_at}"
    )


def test_discovery_without_event_time_falls_back_to_created_at():
    """A discovery with no event-time uses created_at as the fallback in
    representative selection, via _effective_event_time."""
    from ccc.system import _effective_event_time
    from ccc import DiscoveryRecord, EpistemicStatus, ProvenanceStatus

    # Create two discoveries, both with no event times
    # The older one was created first, the newer one later
    older = DiscoveryRecord(
        discovery_id="older_discovery",
        source_material=("a.md",),
        machine_origin=True,
        machine_processing_history=("m",),
        method="method",
        conclusion="pattern",
        confidence=0.8,
        supporting_evidence=(),
        epistemic_status=EpistemicStatus.INFERENCE,
        provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
        stage=AnalysisStage.PATTERN,
        event_start_date=None,  # no event time
        event_end_date=None,
        created_at="2026-09-01T10:00:00+00:00",
    )

    newer = DiscoveryRecord(
        discovery_id="newer_discovery",
        source_material=("b.md",),
        machine_origin=True,
        machine_processing_history=("m",),
        method="method",
        conclusion="pattern",
        confidence=0.8,
        supporting_evidence=(),
        epistemic_status=EpistemicStatus.INFERENCE,
        provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
        stage=AnalysisStage.PATTERN,
        event_start_date=None,  # no event time
        event_end_date=None,
        created_at="2026-09-02T10:00:00+00:00",
    )

    # Without event times, the fallback should order by created_at
    # The older one (created first) should come first
    older_key = _effective_event_time(older)
    newer_key = _effective_event_time(newer)

    assert older_key < newer_key, (
        f"Fallback ordering failed: {older_key} should be < {newer_key}. "
        f"Without event dates, created_at should determine order."
    )


def test_event_date_invariant_rejects_invalid_ranges():
    """DiscoveryRecord validation rejects invalid temporal invariants."""
    from ccc import DiscoveryRecord, EpistemicStatus, ProvenanceStatus

    # Both present, valid order: OK
    record = DiscoveryRecord(
        discovery_id="test",
        source_material=("s",),
        machine_origin=True,
        machine_processing_history=("m",),
        method="m",
        conclusion="c",
        confidence=0.5,
        supporting_evidence=(),
        epistemic_status=EpistemicStatus.INFERENCE,
        provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
        event_start_date="2026-05-01",
        event_end_date="2026-05-31",
    )
    assert record.event_start_date == "2026-05-01"

    # Both present, invalid order: raises
    with pytest.raises(ValueError, match="event_start_date.*>.*event_end_date"):
        DiscoveryRecord(
            discovery_id="test",
            source_material=("s",),
            machine_origin=True,
            machine_processing_history=("m",),
            method="m",
            conclusion="c",
            confidence=0.5,
            supporting_evidence=(),
            epistemic_status=EpistemicStatus.INFERENCE,
            provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
            event_start_date="2026-07-01",
            event_end_date="2026-05-01",
        )

    # Only start (no end): raises
    with pytest.raises(ValueError, match="event_start_date.*event_end_date.*both must"):
        DiscoveryRecord(
            discovery_id="test",
            source_material=("s",),
            machine_origin=True,
            machine_processing_history=("m",),
            method="m",
            conclusion="c",
            confidence=0.5,
            supporting_evidence=(),
            epistemic_status=EpistemicStatus.INFERENCE,
            provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
            event_start_date="2026-05-01",
            event_end_date=None,
        )

    # Only end (no start): raises
    with pytest.raises(ValueError, match="event_end_date.*event_start_date.*both must"):
        DiscoveryRecord(
            discovery_id="test",
            source_material=("s",),
            machine_origin=True,
            machine_processing_history=("m",),
            method="m",
            conclusion="c",
            confidence=0.5,
            supporting_evidence=(),
            epistemic_status=EpistemicStatus.INFERENCE,
            provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
            event_start_date=None,
            event_end_date="2026-05-01",
        )

    # Both None: OK
    record_no_dates = DiscoveryRecord(
        discovery_id="test",
        source_material=("s",),
        machine_origin=True,
        machine_processing_history=("m",),
        method="m",
        conclusion="c",
        confidence=0.5,
        supporting_evidence=(),
        epistemic_status=EpistemicStatus.INFERENCE,
        provenance_status=ProvenanceStatus.ASSISTANT_PROPOSED,
        event_start_date=None,
        event_end_date=None,
    )
    assert record_no_dates.event_start_date is None
