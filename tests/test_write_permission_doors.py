"""The permission check in front of the four doors that create findings and road signs.

``tests/test_write_permission.py`` covers ingest, record, derive, infer and interpret. This file covers the other
four record-creating doors: ``record_external_finding``, ``discover``, ``detect_road_sign`` and
``record_road_sign``. Each asks the check once, first, and goes on only if the answer is exactly True; anything else
refuses before CCC touches its store, rules or audit trail. ``record_road_sign`` is the same act as
``detect_road_sign`` and ``discover`` is the bare way to create what ``record_external_finding`` creates, so none of
them is left open beside the others. The methods that carry a human's action, and the ones that change a record that
already exists, never ask. None of these tests needs CNS and none skips.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
import textwrap
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pytest
from cccb import TextMatcher

from ccc import Actor, AnalysisStage, CCCSystem, RoadSignCategory
from ccc.cns_connector import _scratches
from ccc.errors import WritePermissionRefused
from ccc.permission import WriteRequest

ROOT = Path(__file__).resolve().parents[1]
HUMAN = Actor.human("william")
BASIS = "explicit human decision"


@dataclass(frozen=True)
class _Finding:
    """A stand-in for an external finding: the contract is structural, so nothing here imports its producer."""

    conclusion: str
    method: str
    source_material: Tuple[str, ...]
    confidence: Optional[float]
    verified: bool
    evidence: Tuple[Tuple[str, str], ...] = ()


def _finding(conclusion: str, source: str, verified: bool = True) -> _Finding:
    return _Finding(conclusion=conclusion, method="ecology.search", source_material=(source,), confidence=0.6,
                    verified=verified, evidence=((source, conclusion),))


def _system(check=None) -> CCCSystem:
    """A system that can take external findings, with the given permission (or none)."""
    return CCCSystem(text_matcher=TextMatcher(), private_source_markers=(), write_permission=check)


#: Each covered door with a call that works on an empty store.
COVERED = {
    "record_external_finding": lambda s: s.record_external_finding(
        _finding("a finding about the readme", "a.md"), actor=Actor.model("ecology")),
    "discover": lambda s: s.discover(
        source_material=(), method="scan", conclusion="a candidate", confidence=0.3, actor=Actor.model("model")),
    "detect_road_sign": lambda s: s.detect_road_sign(
        observation="a reversal occurred", category=RoadSignCategory.REVERSAL, actor=Actor.model("model")),
    "record_road_sign": lambda s: s.record_road_sign(
        observation="a reversal occurred", category=RoadSignCategory.REVERSAL, actor=Actor.model("model")),
}


class Check:
    """A permission check that records what it was asked and answers as told."""

    def __init__(self, verdict=True):
        self.verdict = verdict
        self.requests: list[WriteRequest] = []

    def __call__(self, request):
        self.requests.append(request)
        if isinstance(self.verdict, BaseException):
            raise self.verdict
        return self.verdict


def _bytes(system: CCCSystem, tmp_path, name: str) -> bytes:
    return system.store.save(tmp_path / name).read_bytes()


def test_without_a_permission_every_door_works_as_before():
    system = _system()
    for call in COVERED.values():
        assert call(system) is not None
    assert system.store.discoveries and system.store.road_signs


@pytest.mark.parametrize("door", COVERED)
def test_a_yes_lets_the_call_through_and_the_check_is_asked_exactly_once(door):
    check = Check(True)
    system = _system(check)
    COVERED[door](system)
    assert [r.operation for r in check.requests] == [door]
    if door in ("record_external_finding", "discover"):
        assert len(system.store.discoveries) == 1
    else:
        assert len(system.store.road_signs) == 1


def test_the_road_signs_and_stage_moves_record_external_finding_makes_itself_do_not_ask_again():
    """Three independent occurrences make it advance the first to PATTERN and raise a road sign. All of that
    happens under each call's one ask: three calls, three requests, nothing more."""
    check = Check(True)
    system = _system(check)
    actor = Actor.model("ecology")
    first = system.record_external_finding(_finding(
        "governance terminology escalated into grandiose theological jargon", "m.md"), actor=actor)
    system.record_external_finding(_finding(
        "grandiose theological jargon: the governance terminology escalated once again", "y.md"), actor=actor)
    system.record_external_finding(_finding(
        "escalated governance terminology, grandiose theological jargon yet another time", "g.md"), actor=actor)
    assert system.store.discoveries[first.discovery_id].stage is AnalysisStage.PATTERN
    assert any("MANDATE candidate" in s.observation for s in system.store.road_signs.values())
    assert [r.operation for r in check.requests] == ["record_external_finding"] * 3


def test_the_request_names_the_door_and_carries_the_callers_arguments_as_given():
    check = Check(True)
    _system(check).discover(source_material=("s1",), method="scan", conclusion="c", confidence=0.3,
                            actor=Actor.model("model"))
    (request,) = check.requests
    assert request.operation == "discover"
    assert request.args == ()
    assert set(request.kwargs) == {"source_material", "method", "conclusion", "confidence", "actor"}  # no defaults
    assert request.kwargs["source_material"] == ("s1",)

    check = Check(True)
    finding = _finding("a finding", "a.md")
    _system(check).record_external_finding(finding, actor=Actor.model("ecology"))
    (request,) = check.requests
    assert request.operation == "record_external_finding"
    assert request.args == (finding,)
    assert set(request.kwargs) == {"actor"}


def test_the_request_is_a_copy_so_the_check_cannot_change_what_is_written():
    def tampering(request):
        request.kwargs["metadata"]["source"] = "forged"
        return True

    theirs = {"source": "real"}
    sign = _system(tampering).detect_road_sign(
        observation="seen", category=RoadSignCategory.REVERSAL, actor=Actor.model("model"), metadata=theirs)
    assert theirs == {"source": "real"}
    assert sign.metadata["source"] == "real"


@pytest.mark.parametrize("verdict", [False, None, 1, "yes", object(), [True]])
@pytest.mark.parametrize("door", COVERED)
def test_anything_but_true_refuses_and_leaves_the_store_untouched(door, verdict, tmp_path):
    system = _system(Check(verdict))
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(WritePermissionRefused) as refused:
        COVERED[door](system)
    assert refused.value.operation == door
    assert _bytes(system, tmp_path, "after.json") == before  # byte for byte
    assert list(system.audit_trail.all()) == []
    assert not system.store.discoveries and not system.store.road_signs


@pytest.mark.parametrize("door", COVERED)
def test_a_check_that_raises_is_a_refusal_and_the_error_is_its_cause(door, tmp_path):
    system = _system(Check(RuntimeError("roster down")))
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(WritePermissionRefused) as refused:
        COVERED[door](system)
    assert isinstance(refused.value.__cause__, RuntimeError)
    assert "roster down" in str(refused.value)
    assert _bytes(system, tmp_path, "after.json") == before
    assert list(system.audit_trail.all()) == []


def test_a_refusal_does_not_stop_the_other_door_that_makes_the_same_thing():
    """The permission is per call. A no for detect_road_sign says nothing about record_road_sign, and the check
    is what decides; nothing here lets one door stand in for the other."""
    answers = iter([False, True])
    system = _system(lambda request: next(answers))
    with pytest.raises(WritePermissionRefused):
        COVERED["detect_road_sign"](system)
    COVERED["record_road_sign"](system)
    assert len(system.store.road_signs) == 1


def test_the_permission_is_asked_first_so_a_no_beats_the_rules_that_would_refuse_anyway(tmp_path):
    """An unverified finding is refused by CCC's own rule. With a no in front, the no is what is raised, and
    nothing about the finding was looked at."""
    system = _system(Check(False))
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(WritePermissionRefused):
        system.record_external_finding(_finding("", "a.md", verified=False), actor=Actor.model("ecology"))
    assert _bytes(system, tmp_path, "after.json") == before


def test_a_yes_spent_on_a_call_ccc_then_refuses_writes_nothing(tmp_path):
    check = Check(True)
    system = _system(check)
    before = _bytes(system, tmp_path, "before.json")
    with pytest.raises(ValueError):
        system.record_external_finding(_finding("", "a.md", verified=False), actor=Actor.model("ecology"))
    assert [r.operation for r in check.requests] == ["record_external_finding"]
    assert _bytes(system, tmp_path, "after.json") == before
    assert list(system.audit_trail.all()) == []


def test_a_finding_that_cannot_be_copied_is_refused_and_never_asked(tmp_path):
    check = Check(True)
    system = _system(check)
    before = _bytes(system, tmp_path, "before.json")
    bad = _Finding(conclusion="c", method="m", source_material=("a.md",), confidence=0.5, verified=True,
                   evidence=(("a.md", threading.Lock()),))  # type: ignore[arg-type]
    with pytest.raises(WritePermissionRefused):
        system.record_external_finding(bad, actor=Actor.model("ecology"))
    assert check.requests == []
    assert _bytes(system, tmp_path, "after.json") == before


def test_the_methods_that_carry_a_humans_action_and_change_existing_records_never_ask():
    plain = _system()
    anomaly = plain.discover(source_material=(), method="scan", conclusion="a", confidence=0.3,
                             actor=Actor.model("model"), stage=AnalysisStage.ANOMALY)
    pattern = plain.discover(source_material=(), method="scan", conclusion="b", confidence=0.3,
                             actor=Actor.model("model"))
    sign = plain.detect_road_sign(observation="seen", category=RoadSignCategory.REVERSAL, actor=Actor.model("model"))
    original = plain.ingest("material", actor=HUMAN)

    deny = Check(False)
    system = CCCSystem(store=plain.store, write_permission=deny)

    system.advance_discovery(anomaly.discovery_id, stage=AnalysisStage.PATTERN, actor=HUMAN, reason="r")
    system.adopt_discovery(pattern.discovery_id, actor=HUMAN, reason="r", authorization_basis=BASIS)
    system.link_road_sign(sign.road_sign_id, original.artifact_id, actor=HUMAN, reason="r")
    system.decide("a human decision", actor=HUMAN, reason="r", authorization_basis=BASIS)
    for name in ("correct", "amend", "supersede"):
        fresh = plain.ingest(f"material for {name}", actor=HUMAN).artifact_id
        getattr(system, name)(fresh, content=f"new text for {name}", actor=HUMAN, reason="r",
                              authorization_basis=BASIS)

    assert deny.requests == []


@pytest.mark.parametrize("door", COVERED)
def test_the_connectors_scratch_copies_carry_no_permission(door):
    """A scratch copy is where the CNS connector judges an attempt; it must never ask a check, or judging would
    spend a one-use permission."""
    check = Check(False)
    system = _system(check)
    with _scratches(system) as fresh:
        scratch = fresh()
        assert scratch._write_permission is None
        scratch.text_matcher = TextMatcher()
        scratch.private_source_markers = ()
        assert COVERED[door](scratch) is not None
    assert check.requests == []


def test_the_permission_is_not_saved_with_the_store_and_load_can_be_given_one(tmp_path):
    path = _system(Check(False)).save(tmp_path / "s.json")
    reloaded = CCCSystem.load(path)
    assert reloaded._write_permission is None  # an always-yes check would act the same, so look at it directly
    assert COVERED["discover"](reloaded) is not None
    with pytest.raises(WritePermissionRefused):
        COVERED["discover"](CCCSystem.load(path, write_permission=Check(False)))


@pytest.mark.parametrize("door", COVERED)
def test_the_public_signature_is_unchanged(door):
    """The CNS connector binds a call to the real signature to build its digest, so the signature is part of the
    contract. Each door must show the same parameters as before the check existed."""
    signature = inspect.signature(getattr(CCCSystem, door))
    expected = {
        "record_external_finding": ["self", "finding", "actor", "epistemic_status", "allow_private_source"],
        "discover": ["self", "kwargs"],
        "detect_road_sign": ["self", "kwargs"],
        "record_road_sign": ["self", "kwargs"],
    }[door]
    assert list(signature.parameters) == expected
    assert getattr(CCCSystem, door).__name__ == door


def test_the_gated_doors_work_and_refuse_with_cns_absent():
    """CCC imports nothing from CNS. In a fresh interpreter where any import of it fails, a gated system still
    permits, still refuses, and still leaves the store alone."""
    code = textwrap.dedent(
        """
        import sys
        sys.modules['cns'] = None
        sys.modules['cns.gate'] = None
        from ccc import Actor, CCCSystem, RoadSignCategory
        from ccc.errors import WritePermissionRefused

        make = dict(observation="seen", category=RoadSignCategory.REVERSAL, actor=Actor.model("m"))
        allowed = CCCSystem(write_permission=lambda request: True)
        allowed.discover(source_material=(), method="scan", conclusion="c", confidence=0.3, actor=Actor.model("m"))
        allowed.detect_road_sign(**make)
        allowed.record_road_sign(**make)
        assert len(allowed.store.discoveries) == 1 and len(allowed.store.road_signs) == 2

        shut = CCCSystem(write_permission=lambda request: False)
        for call in (lambda: shut.detect_road_sign(**make), lambda: shut.record_road_sign(**make),
                     lambda: shut.discover(source_material=(), method="scan", conclusion="c", confidence=0.3,
                                           actor=Actor.model("m"))):
            try:
                call()
            except WritePermissionRefused:
                pass
            else:
                raise SystemExit("a no did not refuse")
        assert not shut.store.discoveries and not shut.store.road_signs
        assert not any(name == 'cns' or name.startswith('cns.') for name, mod in sys.modules.items() if mod)
        print("ok")
        """
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT,
                          env={"PYTHONPATH": str(ROOT)})
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"
