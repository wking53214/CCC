"""CCC -> CCCb -> CNS, with the real packages at their pinned versions.

One evidence item travels the whole boundary: CCC receives it, asks the
plugged-in CCCb matcher to measure it, validates the measurement, applies its
own rules, and a CNS verdict is bound to the measurement and to CCC's attempted
transitions. The point of the file is what each layer is *not* allowed to do:

* CCCb measures. It cannot admit, corroborate or escalate anything by itself.
* CNS binds. A valid binding proves a verdict was issued about exactly this
  content. It does not prove the content is true or that anyone is authorized.
* CCC decides. Its rules still say no when both of the others say yes.

The CCCb half of the real path uses ``cccb.cns_connector`` (CCCb's own
binding of its findings). The CCC half uses ``ccc.cns_connector`` (ALPHA only:
CCC judges an attempted transition before it happens and has no outcome end).
Skipped when CNS is absent, except in CI's with-CNS job (CCC_REQUIRE_CNS=1).
"""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pytest

if os.environ.get("CCC_REQUIRE_CNS") == "1":
    import cns.gate as cns_gate
else:
    cns_gate = pytest.importorskip(
        "cns.gate", reason="cns not installed; run in an environment with the [cns] extra"
    )

from cccb import TextMatcher  # noqa: E402
from cccb import cns_connector as cccb_cns  # noqa: E402
from ccc import Actor, AnalysisStage, CCCSystem, EpistemicStatus, ProvenanceStatus  # noqa: E402
from ccc.cns_connector import (  # noqa: E402
    PreflightError,
    attempt,
    attempt_digest,
    judge,
    to_cns_result,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL = Actor.model("ecology")
HUMAN = Actor.human("reviewer")
OUTCOME = cns_gate.GateOutcome

TEXT = ("The governance terminology inflated again into grandiose jargon across every revision "
        "of the planning notes, and the same inflation reappeared in the audit summary written afterwards.")
RECURRING = [
    "ledger hashing digest chain rolling block audit trail verification alpha",
    "verification audit trail block rolling chain digest hashing ledger bravo",
]


@dataclass(frozen=True)
class _Finding:
    conclusion: str
    method: str = "ecology.search"
    source_material: Tuple[str, ...] = ("notes.md",)
    confidence: Optional[float] = 0.6
    verified: bool = True
    evidence: Tuple[Tuple[str, str], ...] = ()


def _system():
    return CCCSystem(text_matcher=TextMatcher(), private_source_markers=())


def _state(system) -> str:
    return json.dumps(system.store.snapshot(), sort_keys=True)


def _verdict(finding, subject, digest, outcome=OUTCOME.PASS):
    return cns_gate.GateResult(
        gate="test-roster", position=cns_gate.GatePosition.ALPHA, outcome=outcome,
        reason="issued by the test", subject=subject, subject_digest=digest,
    )


def _admit(system, att):
    """The application's rule: run an attempt only if CNS says PASS. A verdict
    that cannot be obtained is not a PASS: the error propagates and nothing runs."""
    result = judge(system, att)
    if result.outcome is not OUTCOME.PASS:
        return result, None
    return result, att.run(system)


# --- the real path, end to end ------------------------------------------------------

def test_one_evidence_item_through_ccc_then_cccb_then_cns():
    system = _system()
    first = system.record_external_finding(_Finding(TEXT, evidence=(("notes.md", TEXT),)), actor=MODEL)
    second = system.record_external_finding(_Finding(TEXT, evidence=(("notes.md", TEXT),)), actor=MODEL)

    # 1-5. CCC received it, asked CCCb, validated the answer, applied its own rule.
    assert "duplicate detection" in second.method
    assert second.relationships == (first.discovery_id,)
    (group,) = system.recurring_groups()
    assert group.occurrences == (first.discovery_id,) and group.duplicates == (second.discovery_id,)
    assert group.stage is AnalysisStage.ANOMALY

    # 3. CCCb's measurement is deterministic: recomputed from the two stored texts it
    #    equals what CCC wrote into the record.
    earlier = system.store.discovery_match_texts[first.discovery_id]
    later = system.store.discovery_match_texts[second.discovery_id]
    finding = cccb_cns.duplicate_finding(later, earlier)
    assert finding.result is True
    assert f"{finding.anti_probability:.3e}" in second.method
    assert f"{finding.match_length} char overlap with {first.discovery_id}" in second.method
    assert cccb_cns.duplicate_finding(later, earlier) == finding

    # 6-7. A CNS verdict bound to exactly that measurement.
    result = _verdict(finding, cccb_cns.DUPLICATE_SUBJECT, cccb_cns.duplicate_digest(finding))
    assert result.outcome is OUTCOME.PASS and result.bound()
    assert cccb_cns.binds(result, finding)

    # 8. The final CCC state: the binding changed nothing, and the item is still only
    #    a machine's proposal, not evidence, not corroboration.
    before = _state(system)
    assert cccb_cns.binds(result, finding)
    assert _state(system) == before
    assert second.provenance_status is ProvenanceStatus.ASSISTANT_PROPOSED
    assert second.epistemic_status is EpistemicStatus.INFERENCE
    assert second.stage is AnalysisStage.ANOMALY


def test_a_recurrence_binds_and_ccc_alone_decides_what_it_is_worth():
    system = _system()
    first = system.record_external_finding(_Finding(RECURRING[0]), actor=MODEL)
    second = system.record_external_finding(_Finding(RECURRING[1]), actor=MODEL)
    finding = cccb_cns.recurrence_finding(
        system.store.discovery_match_texts[second.discovery_id],
        system.store.discovery_match_texts[first.discovery_id])
    assert finding.result is True
    result = _verdict(finding, cccb_cns.RECURRENCE_SUBJECT, cccb_cns.recurrence_digest(finding))
    assert cccb_cns.binds(result, finding)
    # CCC's rule: a recurrence is a second occurrence and may lift an anomaly to a
    # pattern, never to a mandate. Neither the measurement nor the binding went further.
    assert system.store.discoveries[first.discovery_id].stage is AnalysisStage.PATTERN
    assert not any(r.stage is AnalysisStage.MANDATE for r in system.store.discoveries.values())


# --- CCCb cannot authorize, CNS cannot override, a binding is not truth ----------------

def test_a_bound_pass_does_not_make_ccc_admit_what_its_rules_refuse():
    system = _system()
    first = system.record_external_finding(_Finding(RECURRING[0]), actor=MODEL)
    system.record_external_finding(_Finding(RECURRING[1]), actor=MODEL)   # CCC lifts the first to PATTERN
    assert system.store.discoveries[first.discovery_id].stage is AnalysisStage.PATTERN
    attempted = attempt("advance_discovery", first.discovery_id, stage=AnalysisStage.MANDATE,
                        actor=MODEL, reason="CCCb measured a recurrence and CNS passed it")
    # A PASS that really does bind this very attempt (hand-built: binding is correspondence).
    forged_pass = _verdict(None, attempted.operation, attempt_digest(attempted))
    assert forged_pass.binds(attempted.operation, attempt_digest(attempted))
    # CCC's own verdict on the same attempt is a refusal, and the refusal is the authority.
    before = _state(system)
    result = judge(system, attempted)
    assert result.outcome is OUTCOME.TERMINAL_BREACH and "CCC-123-001" in result.reason
    assert _state(system) == before
    with pytest.raises(Exception, match="CCC-123-001"):
        attempted.run(system)
    assert system.store.discoveries[first.discovery_id].stage is AnalysisStage.PATTERN


def test_judging_never_changes_live_state():
    system = _system()
    first = system.record_external_finding(_Finding(TEXT), actor=MODEL)
    before = _state(system)
    for att in (
        attempt("advance_discovery", first.discovery_id, stage=AnalysisStage.PATTERN, actor=MODEL, reason="r"),
        attempt("advance_discovery", first.discovery_id, stage=AnalysisStage.MANDATE, actor=MODEL, reason="r"),
        attempt("adopt_discovery", first.discovery_id, actor=MODEL, reason="r", authorization_basis="b"),
    ):
        judge(system, att)
        assert _state(system) == before


def test_a_measurement_alone_is_not_corroboration_even_with_a_valid_binding():
    system = _system()
    first = system.record_external_finding(_Finding(TEXT), actor=MODEL)
    for _ in range(4):
        system.record_external_finding(_Finding(TEXT), actor=MODEL)
    finding = cccb_cns.duplicate_finding(TEXT, system.store.discovery_match_texts[first.discovery_id])
    assert cccb_cns.binds(_verdict(finding, cccb_cns.DUPLICATE_SUBJECT, cccb_cns.duplicate_digest(finding)), finding)
    (group,) = system.recurring_groups()
    assert group.occurrence_count == 1 and len(group.duplicates) == 4
    assert group.needs_human_review is False


# --- negative path 1: a forged, altered, stale or mismatched matcher result -------------

def test_a_forged_matcher_result_is_refused_by_ccc_and_creates_nothing():
    class Forger:
        def add(self, item_id, text):
            pass

        def duplicate_of(self, text):
            return ("discovery_that_never_existed", 1e-30, 500)

        def recurrence_of(self, text):
            return None

    system = CCCSystem(text_matcher=Forger(), private_source_markers=())
    with pytest.raises(ValueError, match="unknown duplicate id"):
        system.record_external_finding(_Finding(TEXT), actor=MODEL)
    assert not system.store.discoveries and not system.store.audit_events


def test_an_altered_measurement_no_longer_binds_to_the_verdict_issued_for_the_true_one():
    finding = cccb_cns.duplicate_finding(TEXT, TEXT)
    result = _verdict(finding, cccb_cns.DUPLICATE_SUBJECT, cccb_cns.duplicate_digest(finding))
    assert cccb_cns.binds(result, finding)
    altered = (
        dataclasses.replace(finding, anti_probability=finding.anti_probability / 1e6),
        dataclasses.replace(finding, match_length=finding.match_length + 1),
        dataclasses.replace(finding, result=not finding.result),
        dataclasses.replace(finding, threshold=0.5),
        cccb_cns.duplicate_finding(TEXT + " (edited)", TEXT),     # a different pair: a stale verdict
        cccb_cns.duplicate_finding(TEXT, TEXT.upper()),
    )
    for other in altered:
        assert not cccb_cns.binds(result, other)


def test_a_verdict_bound_to_a_duplicate_does_not_bind_a_recurrence_of_the_same_texts():
    dup = cccb_cns.duplicate_finding(TEXT, TEXT)
    rec = cccb_cns.recurrence_finding(TEXT, TEXT)
    result = _verdict(dup, cccb_cns.DUPLICATE_SUBJECT, cccb_cns.duplicate_digest(dup))
    assert not cccb_cns.binds(result, rec)
    assert not cccb_cns.binds(result, dup, subject=cccb_cns.RECURRENCE_SUBJECT)


# --- negative path 2: CNS binding fails ---------------------------------------------------

@pytest.mark.parametrize("make", [
    pytest.param(lambda f, d: cns_gate.GateResult("g", cns_gate.GatePosition.ALPHA, OUTCOME.PASS), id="unbound"),
    pytest.param(lambda f, d: _verdict(f, cccb_cns.DUPLICATE_SUBJECT, ""), id="empty digest"),
    pytest.param(lambda f, d: _verdict(f, "", d), id="empty subject"),
    pytest.param(lambda f, d: _verdict(f, "cccb.recurrence", d), id="wrong subject"),
    pytest.param(lambda f, d: _verdict(f, cccb_cns.DUPLICATE_SUBJECT, d[:-1] + ("0" if d[-1] != "0" else "1")), id="changed digest"),
    pytest.param(lambda f, d: _verdict(f, cccb_cns.DUPLICATE_SUBJECT, d[:32]), id="truncated digest"),
    pytest.param(lambda f, d: _verdict(f, cccb_cns.DUPLICATE_SUBJECT, d.upper()), id="re-cased digest"),
])
def test_a_failed_binding_never_binds(make):
    finding = cccb_cns.duplicate_finding(TEXT, TEXT)
    digest = cccb_cns.duplicate_digest(finding)
    assert not cccb_cns.binds(make(finding, digest), finding)


@pytest.mark.parametrize("not_a_result", [None, True, "PASS", {"outcome": "PASS"}, object()])
def test_something_that_is_not_a_gate_result_never_binds(not_a_result):
    finding = cccb_cns.duplicate_finding(TEXT, TEXT)
    assert cccb_cns.binds(not_a_result, finding) is False


def test_a_binding_for_one_attempt_does_not_bind_another():
    one = attempt("advance_discovery", "discovery_x", stage=AnalysisStage.PATTERN, actor=MODEL, reason="one")
    two = attempt("advance_discovery", "discovery_x", stage=AnalysisStage.PATTERN, actor=MODEL, reason="two")
    result = _verdict(None, one.operation, attempt_digest(one))
    assert result.binds(one.operation, attempt_digest(one))
    assert not result.binds(two.operation, attempt_digest(two))
    assert not result.binds("accept", attempt_digest(one))


def test_a_judgement_that_cannot_be_made_is_an_error_and_nothing_is_admitted(monkeypatch):
    system = _system()
    first = system.record_external_finding(_Finding(TEXT), actor=MODEL)
    att = attempt("advance_discovery", first.discovery_id, stage=AnalysisStage.PATTERN, actor=MODEL, reason="r")
    before = _state(system)

    def broken(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(type(system.store), "save", broken)
    with pytest.raises(PreflightError, match="cannot snapshot"):
        _admit(system, att)
    monkeypatch.undo()
    assert _state(system) == before
    assert system.store.discoveries[first.discovery_id].stage is AnalysisStage.ANOMALY


def test_to_cns_result_will_not_turn_a_non_outcome_into_a_pass():
    att = attempt("advance_discovery", "discovery_x", stage=AnalysisStage.PATTERN, actor=MODEL, reason="r")
    for odd in (False, 0, "", "ok", [], ValueError):
        with pytest.raises(TypeError):
            to_cns_result(att, odd)


def test_ccc_works_and_cns_calls_fail_closed_when_cns_is_unavailable():
    code = (
        "import sys\n"
        "sys.modules['cns'] = None\n"
        "sys.modules['cns.gate'] = None\n"
        "from ccc import Actor, AnalysisStage, CCCSystem\n"
        "from ccc.cns_connector import CnsNotInstalled, attempt, cns_available, judge\n"
        "from cccb import TextMatcher\n"
        "s = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())\n"
        "class F:\n"
        "    conclusion='A claim worth recording.'; method='m'; source_material=('n.md',)\n"
        "    confidence=0.5; verified=True; evidence=()\n"
        "r = s.record_external_finding(F, actor=Actor.model('e'))\n"
        "assert r.stage is AnalysisStage.ANOMALY and not cns_available()\n"
        "att = attempt('advance_discovery', r.discovery_id, stage=AnalysisStage.PATTERN, actor=Actor.model('e'), reason='r')\n"
        "try:\n"
        "    judge(s, att)\n"
        "except CnsNotInstalled:\n"
        "    print('refused')\n"
        "else:\n"
        "    print('PERMISSIVE')\n"
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                          cwd=ROOT, env={"PYTHONPATH": str(ROOT)})
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "refused"


# --- native digests and binding digests are different things ------------------------------

def test_ccc_native_digests_are_not_cns_binding_digests():
    system = _system()
    note = system.ingest("A human note.", actor=HUMAN)
    att = attempt("ingest", "A human note.", actor=HUMAN)
    native = note.content_digest
    binding = attempt_digest(att)
    finding = cccb_cns.duplicate_finding(TEXT, TEXT)
    assert len({native, binding, cccb_cns.duplicate_digest(finding)}) == 3
    # The binding covers the attempted call; the native digest covers the stored text.
    # Only the first moves when the arguments move, and neither can stand in for the other.
    assert attempt_digest(attempt("ingest", "A different note.", actor=HUMAN)) != binding
    assert system.store.require_artifact(note.artifact_id).content_digest == native


# --- the limits, stated as assertions -------------------------------------------------------

def test_a_binding_has_no_state_in_it_so_a_stale_pass_still_binds():
    """CHARACTERIZATION (finding F-12). The digest covers the attempted call, not the
    store it was judged on. A PASS issued before another human rejected the record still
    binds to the same attempt afterwards; CCC's real operation is what refuses it."""
    system = _system()
    fact = system.ingest("A human fact.", actor=HUMAN, epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
                         authorization_basis="human record")
    proposal = system.derive("A machine inference.", actor=MODEL, evidence_ids=(fact.artifact_id,))
    att = attempt("accept", proposal.artifact_id, actor=HUMAN, reason="reviewed",
                  authorization_basis="explicit human adoption", evidence_ids=(fact.artifact_id,))
    first = judge(system, att)
    assert first.outcome is OUTCOME.PASS
    system.reject(proposal.artifact_id, actor=HUMAN, reason="rejected first", authorization_basis="explicit human rejection")
    assert first.binds(att.operation, attempt_digest(att))        # the old PASS still binds
    assert judge(system, att).outcome is OUTCOME.TERMINAL_BREACH  # CCC's answer now
    with pytest.raises(Exception):
        att.run(system)


def test_the_connector_judges_on_a_scratch_copy_that_has_no_human_verifier():
    """CHARACTERIZATION (finding F-11). The scratch copy carries neither the live
    system's write_permission nor its human_verifier, so a PASS says the rules admit the
    call, not that the application's own checks do."""
    allow = [True]
    system = CCCSystem(human_verifier=lambda request: allow[0])
    fact = system.ingest("A human fact.", actor=HUMAN, epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
                         authorization_basis="human record")
    proposal = system.derive("A machine inference.", actor=MODEL, evidence_ids=(fact.artifact_id,))
    att = attempt("accept", proposal.artifact_id, actor=HUMAN, reason="reviewed",
                  authorization_basis="explicit human adoption", evidence_ids=(fact.artifact_id,))
    allow[0] = False
    assert judge(system, att).outcome is OUTCOME.PASS
    before = _state(system)
    with pytest.raises(Exception, match="human verifier"):
        att.run(system)
    assert _state(system) == before
