"""Recurrence detection: the lynchpin that lets discovery.py's
anomaly -> pattern -> mandate machine be driven by a stream, instead of
only by a human saying "that's the same as before."
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pytest

from ccc import Actor, AnalysisStage, CCCSystem
from ccc.recurrence import RecurrenceDetector


@dataclass(frozen=True)
class _Finding:
    conclusion: str
    method: str
    source_material: Tuple[str, ...]
    confidence: Optional[float]
    verified: bool
    evidence: Tuple[Tuple[str, str], ...] = ()


def _finding(conclusion, source, excerpt=None):
    return _Finding(
        conclusion=conclusion, method="ecology.search", source_material=(source,),
        confidence=0.6, verified=True,
        evidence=((source, excerpt or conclusion),),
    )


# --- the detector itself ------------------------------------------------

def test_shared_vocabulary_is_a_recurrence_different_words_are_not():
    d = RecurrenceDetector()
    d.register("d1", "the governance terminology inflated again into grandiose pseudo-technical jargon")
    # shares "governance terminology inflated grandiose jargon" -> recurrence
    hit = d.find_recurrence("governance terminology inflated once more, grandiose jargon returning")
    assert hit is not None and hit[0] == "d1"
    # same idea, no shared significant words -> not detected (stated limit)
    miss = d.find_recurrence("the vocabulary ballooned pompously once more")
    assert miss is None


def test_a_signature_below_minimum_size_never_matches():
    d = RecurrenceDetector()
    d.register("d1", "alpha beta gamma delta epsilon zeta")
    assert d.find_recurrence("alpha beta gamma") is None  # 3 concepts < MINIMUM_SIGNATURE_SIZE


def test_index_only_compares_against_discoveries_sharing_a_concept():
    d = RecurrenceDetector()
    for i in range(500):
        d.register(f"unrelated{i}", f"completely distinct topic number {i} about widgets and sprockets {i}")
    d.register("target", "governance terminology inflation grandiose jargon escalation arc")
    hit = d.find_recurrence("governance terminology inflation grandiose jargon returning again")
    assert hit is not None and hit[0] == "target"


# --- integration with record_external_finding --------------------------

def test_second_independent_occurrence_advances_the_pattern():
    system = CCCSystem()
    actor = Actor.model("ecology")

    first = system.record_external_finding(
        _finding("the model escalated its governance terminology into grandiose theological jargon", "chat_march.md"),
        actor=actor,
    )
    assert system.store.discoveries[first.discovery_id].stage is AnalysisStage.ANOMALY

    second = system.record_external_finding(
        _finding("governance terminology escalated again into grandiose theological jargon in a later session", "chat_may.md"),
        actor=actor,
    )
    # the FIRST discovery advanced to PATTERN; the second is its own ANOMALY, linked
    assert system.store.discoveries[first.discovery_id].stage is AnalysisStage.PATTERN
    assert first.discovery_id in second.relationships
    assert "recurrence of" in second.method


def test_a_byte_level_duplicate_does_not_advance_a_pattern():
    """A re-observation of the same content is the opposite of an
    independent occurrence -- it must not push the count toward MANDATE."""
    system = CCCSystem()
    actor = Actor.model("ecology")
    text = "the governance terminology escalated into grandiose theological jargon during the arc"
    first = system.record_external_finding(_finding(text, "a.md"), actor=actor)
    second = system.record_external_finding(_finding(text, "b.md"), actor=actor)
    assert system.store.discoveries[first.discovery_id].stage is AnalysisStage.ANOMALY  # NOT advanced
    assert "duplicate detection" in second.method


def test_third_occurrence_records_a_road_sign_not_a_mandate():
    system = CCCSystem()
    actor = Actor.model("ecology")
    # Three occurrences that share concepts but are genuinely differently
    # worded. Verified numerically (scratchpad/fixture_check.py): every
    # pair clears RECURRENCE_THRESHOLD (0.545-0.75 Jaccard) and every
    # pair's longest common run is < MINIMUM_MATCH_LENGTH (<=33 chars), so
    # none trips the anti-probability duplicate check.
    d1 = system.record_external_finding(_finding(
        "governance terminology escalated into grandiose theological jargon", "m.md"), actor=actor)
    d2 = system.record_external_finding(_finding(
        "grandiose theological jargon: the governance terminology escalated once again", "y.md"), actor=actor)
    d3 = system.record_external_finding(_finding(
        "escalated governance terminology, grandiose theological jargon yet another time", "g.md"), actor=actor)

    # occurrence #2 advanced the cluster's representative (d1) to PATTERN;
    # occurrence #3 must NOT advance anything further -- MANDATE is human-only.
    stages = {r.discovery_id: system.store.discoveries[r.discovery_id].stage for r in (d1, d2, d3)}
    at_pattern = [did for did, st in stages.items() if st is AnalysisStage.PATTERN]
    assert at_pattern == [d1.discovery_id], stages          # exactly one, and it is d1
    assert stages[d2.discovery_id] is AnalysisStage.ANOMALY
    assert stages[d3.discovery_id] is AnalysisStage.ANOMALY
    assert not any(st is AnalysisStage.MANDATE for st in stages.values())

    signs = [s for s in system.store.road_signs.values() if "MANDATE candidate" in s.observation]
    assert len(signs) == 1
    assert signs[0].is_conclusion is False
    assert list(signs[0].linked_ids) == [d1.discovery_id, d3.discovery_id]
    assert signs[0].metadata["pattern_id"] == d1.discovery_id
    assert signs[0].metadata["occurrence_count"] == 3


@pytest.mark.xfail(reason=(
    "KNOWN LIMIT, deliberately not closed -- and narrower than it looks. IF "
    "two findings are compared on generated prose sharing a long templated "
    "preamble, the anti-probability check sees a common source and links them "
    "as duplicates though their substance differs. BUT: (1) Ecology's real "
    "generator emits no fixed preamble -- its system prompt is 'You are an "
    "analytical executive assistant...' and the output is the model's own "
    "prose, verified 2026-09-05 against ecology/rag_engine.py; (2) "
    "comparison_text normally comes from retrieved source excerpts, not "
    "generated prose at all -- only the evidence-less fallback path is even "
    "exposed. Every statistical fix tried (concept-overlap floor, "
    "match-containment ratio) also weakens the resubmission defence "
    "test_smash_findings exists for; the two cases are not separable by text "
    "statistics. Registering a generic preamble string as known boilerplate "
    "does NOT work either -- _explained_by_known_boilerplate does a substring "
    "test against whole reference files, so a short phrase file would exclude "
    "any matched span sitting inside it, weakening duplicate detection "
    "broadly. A real close needs a specific, observed preamble string from a "
    "specific generator -- none exists in this system today."
), strict=True)
def test_shared_templated_preamble_does_not_collapse_two_findings():
    system = CCCSystem()
    actor = Actor.model("ecology")
    stem = "Based on the retrieved source excerpts, the analysis concludes that "
    a = system.record_external_finding(_finding(
        stem + "the ledger uses a global per-block hash chain with rolling digests", "a.md"), actor=actor)
    b = system.record_external_finding(_finding(
        stem + "customer retention rose sharply once the onboarding flow was redesigned", "b.md"), actor=actor)

    assert a.discovery_id != b.discovery_id
    assert b.relationships == ()                       # not linked as a duplicate of a
    assert "duplicate detection" not in b.method
    assert system.store.discoveries[b.discovery_id].stage is AnalysisStage.ANOMALY


def test_each_occurrence_past_the_second_records_its_own_road_sign():
    """APM halts and reviews on the third strike, so occurrences 3, 4, 5,
    ... each record their own REPEATED_RETURN road sign -- the wall IS the
    escalating pressure. Each still carries pattern_id + a true
    occurrence_count, so a reviewer can collapse them by pattern. MANDATE
    stays human-only throughout."""
    system = CCCSystem()
    actor = Actor.model("ecology")
    variants = [
        "governance terminology escalated into grandiose theological jargon",
        "grandiose theological jargon: the governance terminology escalated once again",
        "escalated governance terminology, grandiose theological jargon yet another time",
        "again the governance terminology escalated, grandiose theological jargon returning",
        "grandiose theological jargon once more as governance terminology escalated further",
    ]
    records = [system.record_external_finding(_finding(v, f"s{i}.md"), actor=actor)
               for i, v in enumerate(variants)]

    signs = [s for s in system.store.road_signs.values() if "MANDATE candidate" in s.observation]
    assert len(signs) == 3                                   # occurrences 3, 4, 5
    assert {s.metadata["pattern_id"] for s in signs} == {records[0].discovery_id}
    assert sorted(s.metadata["occurrence_count"] for s in signs) == [3, 4, 5]
    flagged = {s.linked_ids[1] for s in signs}
    assert flagged == {r.discovery_id for r in records[2:]}
    # nothing was pushed to MANDATE by the machine
    assert all(system.store.discoveries[r.discovery_id].stage is not AnalysisStage.MANDATE
               for r in records)
    # exactly one discovery ever reached PATTERN -- the cluster did not fragment
    at_pattern = [r.discovery_id for r in records
                  if system.store.discoveries[r.discovery_id].stage is AnalysisStage.PATTERN]
    assert at_pattern == [records[0].discovery_id]


def test_a_drifted_third_occurrence_resolves_to_the_cluster_root_not_a_fragment():
    """Occurrence #3 matches occurrence #2 lexically but has drifted too far
    to match occurrence #1 (the PATTERN). Following #2's relationships back
    to #1 must still resolve the cluster to #1 -- otherwise #2 gets advanced
    to a second, parallel PATTERN and the recurrence is undercounted.
    Fixtures verified numerically: F1<->F2 0.75, F2<->F3 0.60, F1<->F3 0.40."""
    system = CCCSystem()
    actor = Actor.model("ecology")
    d1 = system.record_external_finding(_finding(
        "governance terminology escalated grandiose theological jargon", "1.md"), actor=actor)
    d2 = system.record_external_finding(_finding(
        "grandiose theological jargon escalated governance terminology further somewhat", "2.md"), actor=actor)
    d3 = system.record_external_finding(_finding(
        "escalated further grandiose jargon, somewhat bureaucratic governance babble", "3.md"), actor=actor)

    stages = {r.discovery_id: system.store.discoveries[r.discovery_id].stage for r in (d1, d2, d3)}
    assert [did for did, s in stages.items() if s is AnalysisStage.PATTERN] == [d1.discovery_id]
    signs = [s for s in system.store.road_signs.values() if s.metadata.get("pattern_id") == d1.discovery_id]
    assert len(signs) == 1
    assert signs[0].metadata["occurrence_count"] == 3


def test_a_duplicate_in_the_chain_is_not_counted_as_an_occurrence():
    """B is a byte-duplicate of A; C is a genuine recurrence that matches B
    lexically. The cluster walk reaches A through B (correct -- C's pattern
    IS A's), but B is a re-observation, not an independent occurrence, and
    must not inflate the count."""
    system = CCCSystem()
    actor = Actor.model("ecology")
    shared = "governance terminology escalated grandiose theological jargon across sessions repeatedly"
    a = system.record_external_finding(_finding("cA", "a.md", excerpt=shared), actor=actor)
    system.record_external_finding(_finding("cB", "b.md", excerpt=shared), actor=actor)  # duplicate of A
    c = system.record_external_finding(_finding(
        "grandiose theological jargon: escalated governance terminology once more, distinctly", "c.md"), actor=actor)
    d = system.record_external_finding(_finding(
        "escalated grandiose jargon again; governance terminology theological in tone once more", "d.md"), actor=actor)

    assert system.store.discoveries[a.discovery_id].stage is AnalysisStage.PATTERN
    # C saw one prior independent occurrence (A), not two (A + the duplicate B)
    assert "1 prior occurrence" in c.method
    assert "2 prior occurrence" in d.method
    signs = [s for s in system.store.road_signs.values() if s.metadata.get("pattern_id") == a.discovery_id]
    assert len(signs) == 1                                 # only D is a 3rd+ occurrence
    assert signs[0].metadata["occurrence_count"] == 3      # A, C, D -- not the duplicate B


def test_genuinely_novel_findings_stay_separate_anomalies():
    system = CCCSystem()
    actor = Actor.model("ecology")
    a = system.record_external_finding(_finding("the ledger uses a global hash chain with per-block digests", "x.md"), actor=actor)
    b = system.record_external_finding(_finding("customer retention improved after the onboarding redesign shipped", "y.md"), actor=actor)
    assert a.discovery_id != b.discovery_id
    assert system.store.discoveries[a.discovery_id].stage is AnalysisStage.ANOMALY
    assert system.store.discoveries[b.discovery_id].stage is AnalysisStage.ANOMALY
    assert b.relationships == ()


# --- surviving a session boundary -------------------------------------

def test_recurrence_detection_survives_a_reopen(tmp_path):
    """The recurrence detector is an in-memory accelerator rebuilt in
    __init__. If a reopened session doesn't repopulate it from the store,
    occurrence #2 arriving in a new process matches nothing and the ladder
    silently never climbs -- which is precisely the cross-session case the
    whole system is for."""
    path = tmp_path / "state.json"
    actor = Actor.model("ecology")

    s1 = CCCSystem(persistence_path=path)
    d1 = s1.record_external_finding(_finding(
        "governance terminology escalated into grandiose theological jargon", "m.md"), actor=actor)
    assert s1.store.discoveries[d1.discovery_id].stage is AnalysisStage.ANOMALY
    s1.save()

    s2 = CCCSystem(persistence_path=path)  # one line, fresh "process"
    d2 = s2.record_external_finding(_finding(
        "grandiose theological jargon: the governance terminology escalated once again", "y.md"), actor=actor)
    assert s2.store.discoveries[d1.discovery_id].stage is AnalysisStage.PATTERN  # climbed across the boundary
    assert d1.discovery_id in d2.relationships
    assert "recurrence of" in d2.method


def test_a_pre_field_state_file_reconstructs_match_texts_and_warns(tmp_path):
    """A state file written before discovery_match_texts existed must not
    leave every prior finding permanently invisible to the matchers. It
    reconstructs them (approximately) from supporting_evidence and warns
    that it did."""
    import json

    path = tmp_path / "legacy.json"
    actor = Actor.model("ecology")
    excerpt = "governance terminology escalated into grandiose theological jargon"

    s1 = CCCSystem(persistence_path=path)
    d1 = s1.record_external_finding(_finding("c", "old.md", excerpt=excerpt), actor=actor)
    s1.save()

    raw = json.loads(path.read_text())
    del raw["discovery_match_texts"]          # simulate a pre-field file
    path.write_text(json.dumps(raw))

    with pytest.warns(UserWarning, match="predating discovery_match_texts"):
        s2 = CCCSystem(persistence_path=path)

    # the reconstructed text still drives recurrence detection
    s2.record_external_finding(_finding(
        "grandiose theological jargon: governance terminology escalated once again", "new.md"), actor=actor)
    assert s2.store.discoveries[d1.discovery_id].stage is AnalysisStage.PATTERN


def test_duplicate_detection_survives_a_reopen(tmp_path):
    path = tmp_path / "state.json"
    actor = Actor.model("ecology")
    excerpt = ("Ecology's README describes a living, branching, converging memory model; "
               "its code is a retrieval pipeline with no identity or temporal model at all.")

    s1 = CCCSystem(persistence_path=path)
    first = s1.record_external_finding(_finding("c", "a.md", excerpt=excerpt), actor=actor)
    s1.save()

    s2 = CCCSystem(persistence_path=path)
    second = s2.record_external_finding(_finding("c", "b.md", excerpt=excerpt), actor=actor)
    assert second.relationships == (first.discovery_id,)
    assert "duplicate detection" in second.method
    assert s2.store.discoveries[first.discovery_id].stage is AnalysisStage.ANOMALY  # a re-observation, not a 2nd occurrence
