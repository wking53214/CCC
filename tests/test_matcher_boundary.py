"""The matcher boundary, attacked.

CCC owns what a match means; the matcher (CCCb) only measures. These tests
treat the matcher's answers as untrusted input and prove that a bad answer is
refused before anything is written, that an answer cannot reach an
authoritative state by itself, and that the pinned CCCb really is the one CCC
is tested against. Where CCC's guard has a known limit it is stated here as a
strict expected failure, so closing the limit makes the test say so.
"""
from __future__ import annotations

import itertools
import json
import re
import subprocess
import sys
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pytest

from ccc import Actor, AnalysisStage, CCCSystem
from cccb import TextMatcher

ROOT = Path(__file__).resolve().parents[1]
MODEL = Actor.model("ecology")

# The CCCb commit CCC is reviewed against (PR #43). test_text_matching.py holds
# the same constant for the pin test; this file checks the pin a second way.
REVIEWED_CCCB = "8e3c779ea8f932dd34a637bf2fcb0835cc7bc068"
MATCH_PIN = re.compile(r"cccb @ git\+https://github\.com/wking53214/CCCb\.git@([0-9a-f]{40})")


@dataclass(frozen=True)
class _Finding:
    conclusion: str
    method: str = "ecology.search"
    source_material: Tuple[str, ...] = ("notes.md",)
    confidence: Optional[float] = 0.6
    verified: bool = True
    evidence: Tuple[Tuple[str, str], ...] = ()


BASE = ("The governance terminology inflated again into grandiose jargon across every revision "
        "of the planning notes, and the same inflation reappeared in the audit summary written afterwards.")


class _Scripted:
    """A matcher whose answers (or failures) the test dictates."""

    def __init__(self, duplicate=None, recurrence=None, raises=None, add_raises=False):
        self.duplicate, self.recurrence = duplicate, recurrence
        self.raises, self.add_raises = raises, add_raises
        self.added: list[str] = []

    def add(self, item_id, text):
        if self.add_raises:
            raise RuntimeError("index unavailable")
        self.added.append(item_id)

    def duplicate_of(self, text):
        if self.raises == "duplicate":
            raise RuntimeError("duplicate measurement failed")
        return self.duplicate

    def recurrence_of(self, text):
        if self.raises == "recurrence":
            raise RuntimeError("recurrence measurement failed")
        return self.recurrence


def _state(system) -> str:
    return json.dumps(system.store.snapshot(), sort_keys=True)


def _seeded(matcher):
    """A system with one real finding on record; returns (system, its id)."""
    system = CCCSystem(text_matcher=matcher, private_source_markers=())
    first = system.record_external_finding(_Finding("A first, plainly worded claim about ledgers."), actor=MODEL)
    return system, first.discovery_id


def _real():
    return CCCSystem(text_matcher=TextMatcher(), private_source_markers=())


def _kind(record) -> str:
    if "duplicate detection" in record.method:
        return "duplicate"
    if "recurrence of" in record.method:
        return "recurrence"
    return "independent"


# --- the pin, checked a second way -------------------------------------------------

def _match_pin(pyproject_text: str) -> str:
    """The commit the match extra installs, or AssertionError if it is not
    exactly one full 40-hex commit of CCCb (no branch, tag, short sha, range)."""
    extra = tomllib.loads(pyproject_text)["project"]["optional-dependencies"]["match"]
    assert len(extra) == 1, extra
    found = MATCH_PIN.fullmatch(extra[0])
    assert found is not None, f"not an exact CCCb commit pin: {extra[0]!r}"
    return found.group(1)


def test_the_match_extra_installs_exactly_the_reviewed_commit():
    assert _match_pin((ROOT / "pyproject.toml").read_text(encoding="utf-8")) == REVIEWED_CCCB


@pytest.mark.parametrize("drifted", [
    "cccb @ git+https://github.com/wking53214/CCCb.git@main",
    "cccb @ git+https://github.com/wking53214/CCCb.git@v0.1.0",
    "cccb @ git+https://github.com/wking53214/CCCb.git",
    "cccb @ git+https://github.com/wking53214/CCCb.git@8e3c779",
    "cccb @ git+https://github.com/wking53214/CCCb.git@8E3C779EA8F932DD34A637BF2FCB0835CC7BC068",
    "cccb @ git+https://github.com/wking53214/CCCb.git@8e3c779ea8f932dd34a637bf2fcb0835cc7bc068#egg=x",
    "cccb @ git+https://github.com/elsewhere/CCCb.git@8e3c779ea8f932dd34a637bf2fcb0835cc7bc068",
    "cccb>=0.1",
    "cccb",
])
def test_the_pin_check_catches_every_kind_of_drift(drifted):
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    original = tomllib.loads(text)["project"]["optional-dependencies"]["match"][0]
    mutated = text.replace(original, drifted)
    assert mutated != text
    with pytest.raises(AssertionError):
        _match_pin(mutated)


def test_a_different_full_commit_is_caught_by_the_reviewed_constant():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    mutated = text.replace(REVIEWED_CCCB, "f14492f77aef0e1244fe8a184a3fbde3947c9d3d")
    assert _match_pin(mutated) != REVIEWED_CCCB


def test_both_integrations_are_optional_extras_and_the_base_install_has_no_dependencies():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert meta["dependencies"] == []
    extras = meta["optional-dependencies"]
    assert set(extras) >= {"match", "cns"}
    assert not any("cccb" in d or "cns" in d.lower() for d in extras["dev"])


def test_ccc_runs_without_loading_cccb_or_cns():
    code = (
        "import sys\n"
        "sys.modules['cccb'] = None\n"
        "sys.modules['cns'] = None\n"
        "from ccc import Actor, CCCSystem\n"
        "s = CCCSystem()\n"
        "a = s.ingest('A human note.', actor=Actor.human())\n"
        "assert s.store.require_artifact(a.artifact_id).available\n"
        "print('ok')\n"
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0 and done.stdout.strip() == "ok", done.stderr


# --- the installed CCCb behaves like the pinned one ---------------------------------

def test_the_installed_matcher_has_the_pinned_tie_order_fix():
    """CCCb 8e3c779 resolves tied candidates in id order, not hash order. Run
    the real matcher under several hash seeds: one answer, and it is the
    lexically smallest id of the tied set."""
    code = (
        "from cccb import TextMatcher\n"
        "m = TextMatcher()\n"
        "text = 'ledger hashing chain digest rolling block verification audit trail'\n"
        "for i in ['delta', 'gamma', 'alpha', 'echo', 'bravo', 'charlie']:\n"
        "    m.add(i, text)\n"
        "print(m.recurrence_of('ledger hashing chain digest rolling block verification audit trail extra')[0])\n"
        "print(m.recurrence_of(text)[2][0][0])\n"
    )
    outputs = set()
    for seed in range(8):
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                              env={"PYTHONHASHSEED": str(seed)})
        assert done.returncode == 0, done.stderr
        outputs.add(done.stdout)
    assert outputs == {"alpha\nalpha\n"}


def test_the_matcher_interface_ccc_uses_is_the_one_cccb_provides():
    from ccc.text_matching import TextMatcher as Shape
    assert isinstance(TextMatcher(), Shape)
    matcher = TextMatcher()
    matcher.add("one", BASE)
    duplicate = matcher.duplicate_of(BASE)
    assert isinstance(duplicate, tuple) and len(duplicate) == 3
    assert duplicate[0] == "one" and 0.0 <= duplicate[1] <= 1.0 and duplicate[2] >= 1


# --- hostile answers are refused before anything is written -------------------------

_NAN, _INF = float("nan"), float("inf")
BAD_DUPLICATES = {
    "fabricated id": lambda real: ("never-given", 1e-12, 80),
    "id is None": lambda real: (None, 1e-12, 80),
    "id is an int": lambda real: (7, 1e-12, 80),
    "id is empty": lambda real: ("", 1e-12, 80),
    "missing field": lambda real: (real, 1e-12),
    "extra field": lambda real: (real, 1e-12, 80, "x"),
    "a list not a tuple": lambda real: [real, 1e-12, 80],
    "a dict": lambda real: {"id": real},
    "a string": lambda real: real,
    "score NaN": lambda real: (real, _NAN, 80),
    "score +inf": lambda real: (real, _INF, 80),
    "score -inf": lambda real: (real, -_INF, 80),
    "score negative": lambda real: (real, -0.1, 80),
    "score above one": lambda real: (real, 1.5, 80),
    "score is a bool": lambda real: (real, True, 80),
    "score is a string": lambda real: (real, "0.00001", 80),
    "score is None": lambda real: (real, None, 80),
    "score is huge int": lambda real: (real, 10 ** 400, 80),
    "length is a bool": lambda real: (real, 1e-12, True),
    "length is zero": lambda real: (real, 1e-12, 0),
    "length is negative": lambda real: (real, 1e-12, -5),
    "length is a float": lambda real: (real, 1e-12, 80.0),
    "length is a string": lambda real: (real, 1e-12, "80"),
}


@pytest.mark.parametrize("name", sorted(BAD_DUPLICATES))
def test_a_hostile_duplicate_answer_is_refused_and_nothing_changes(name):
    matcher = _Scripted()
    system, real_id = _seeded(matcher)
    matcher.duplicate = BAD_DUPLICATES[name](real_id)
    before = _state(system)
    with pytest.raises(ValueError, match="text matcher"):
        system.record_external_finding(_Finding("Another claim, worded differently."), actor=MODEL)
    assert _state(system) == before


BAD_RECURRENCES = {
    "fabricated best": lambda r: ("never-given", 0.9, (("never-given", 0.9),)),
    "fabricated cluster member": lambda r: (r, 0.9, ((r, 0.9), ("never-given", 0.8))),
    "best outside its cluster": lambda r: (r, 0.9, (("never-given", 0.9),)),
    "empty cluster": lambda r: (r, 0.9, ()),
    "cluster is a list": lambda r: (r, 0.9, [(r, 0.9)]),
    "cluster is None": lambda r: (r, 0.9, None),
    "entry has one field": lambda r: (r, 0.9, ((r,),)),
    "entry is a list": lambda r: (r, 0.9, ([r, 0.9],)),
    "missing field": lambda r: (r, 0.9),
    "best score NaN": lambda r: (r, _NAN, ((r, 0.9),)),
    "best score above one": lambda r: (r, 99.0, ((r, 0.9),)),
    "member score NaN": lambda r: (r, 0.9, ((r, _NAN),)),
    "member score +inf": lambda r: (r, 0.9, ((r, _INF),)),
    "member score negative": lambda r: (r, 0.9, ((r, -1.0),)),
    "member score a bool": lambda r: (r, 0.9, ((r, True),)),
    "member score a string": lambda r: (r, 0.9, ((r, "high"),)),
}


@pytest.mark.parametrize("name", sorted(BAD_RECURRENCES))
def test_a_hostile_recurrence_answer_is_refused_and_nothing_changes(name):
    matcher = _Scripted()
    system, real_id = _seeded(matcher)
    matcher.recurrence = BAD_RECURRENCES[name](real_id)
    before = _state(system)
    with pytest.raises(ValueError, match="text matcher"):
        system.record_external_finding(_Finding("Another claim, worded differently."), actor=MODEL)
    assert _state(system) == before


def test_in_range_edge_scores_are_still_accepted():
    """Validation must not reject answers the real matcher can give."""
    matcher = _Scripted()
    system, real_id = _seeded(matcher)
    matcher.duplicate = (real_id, 0.0, 1)
    assert _kind(system.record_external_finding(_Finding("Edge one."), actor=MODEL)) == "duplicate"
    matcher.duplicate = None
    matcher.recurrence = (real_id, 1.0, ((real_id, 1.0), (real_id, 0.0)))
    system.record_external_finding(_Finding("Edge two."), actor=MODEL)
    matcher.recurrence = (real_id, 1, ((real_id, 1),))
    system.record_external_finding(_Finding("Edge three, ints are numbers."), actor=MODEL)


# --- failures are loud, never a successful assessment --------------------------------

@pytest.mark.parametrize("stage", ["duplicate", "recurrence"])
def test_a_matcher_that_raises_while_measuring_records_nothing(stage):
    matcher = _Scripted()
    system, _ = _seeded(matcher)
    matcher.raises = stage
    before = _state(system)
    with pytest.raises(RuntimeError, match="measurement failed"):
        system.record_external_finding(_Finding("Another claim."), actor=MODEL)
    assert _state(system) == before


def test_a_matcher_whose_index_fails_after_the_write_leaves_a_visible_record_and_a_loud_error():
    """CHARACTERIZATION of a known partial failure (finding F-07, see the
    register): add() is called after the record is written, so an index
    failure raises to the caller but the record stays. In-process, a retry
    would not see the record as a duplicate. The match text was stored before
    the index call, so a reload re-indexes it: the guard comes back."""
    matcher = _Scripted(add_raises=True)
    system = CCCSystem(text_matcher=matcher, private_source_markers=())
    with pytest.raises(RuntimeError, match="index unavailable"):
        system.record_external_finding(_Finding(BASE), actor=MODEL)
    (record,) = system.store.discoveries.values()
    assert record.stage is AnalysisStage.ANOMALY
    assert system.store.discovery_match_texts[record.discovery_id] == BASE
    restored = _Scripted()
    reloaded = CCCSystem(store=system.store, text_matcher=restored, private_source_markers=())
    assert restored.added == [record.discovery_id]
    assert reloaded.store.discoveries.keys() == system.store.discoveries.keys()


# --- a measurement is not corroboration, and cannot decide anything alone ---------------

def test_resubmitting_the_same_finding_never_creates_a_second_occurrence():
    system = _real()
    first = system.record_external_finding(_Finding(BASE), actor=MODEL)
    for _ in range(6):
        assert _kind(system.record_external_finding(_Finding(BASE), actor=MODEL)) == "duplicate"
    (group,) = system.recurring_groups()
    assert group.occurrences == (first.discovery_id,)
    assert group.occurrence_count == 1 and len(group.duplicates) == 6
    assert group.stage is AnalysisStage.ANOMALY
    assert group.needs_human_review is False


def test_a_duplicate_link_to_a_duplicate_still_counts_one_occurrence():
    system = _real()
    system.record_external_finding(_Finding(BASE), actor=MODEL)
    system.record_external_finding(_Finding(BASE + " "), actor=MODEL)
    system.record_external_finding(_Finding(BASE), actor=MODEL)
    (group,) = system.recurring_groups()
    assert group.occurrence_count == 1


def test_a_matcher_that_lies_with_real_ids_can_reach_pattern_but_never_mandate():
    """Even a matcher that fabricates recurrence over ids CCC really holds is
    a machine, and a machine's top is PATTERN: MANDATE is human-only."""
    matcher = _Scripted()
    system, root = _seeded(matcher)
    for i in range(8):
        matcher.recurrence = (root, 0.99, ((root, 0.99),))
        system.record_external_finding(_Finding(f"Independent-looking claim number {i}."), actor=MODEL)
    stages = {r.stage for r in system.store.discoveries.values()}
    assert AnalysisStage.MANDATE not in stages
    assert system.store.discoveries[root].stage is AnalysisStage.PATTERN


def test_a_matcher_answer_never_changes_a_humans_record():
    matcher = _Scripted()
    system = CCCSystem(text_matcher=matcher, private_source_markers=())
    note = system.ingest("A human note.", actor=Actor.human())
    before = json.dumps(system.store.snapshot()["artifacts"], sort_keys=True)
    matcher.duplicate = ("never-given", 1e-12, 80)
    with pytest.raises(ValueError):
        system.record_external_finding(_Finding("A claim."), actor=MODEL)
    assert json.dumps(system.store.snapshot()["artifacts"], sort_keys=True) == before
    assert system.store.require_artifact(note.artifact_id).available


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
def test_the_order_a_matcher_lists_its_cluster_in_does_not_change_the_outcome(order):
    outcomes = set()
    for ordering in (order, tuple(reversed(order))):
        matcher = _Scripted()
        system, root = _seeded(matcher)
        ids = [root]
        for i in range(2):
            matcher.recurrence = (ids[0], 0.9, ((ids[0], 0.9),))
            ids.append(system.record_external_finding(_Finding(f"A distinct claim {i}."), actor=MODEL).discovery_id)
        cluster = tuple((ids[k], 0.9) for k in ordering)
        matcher.recurrence = (cluster[0][0], 0.9, cluster)
        new = system.record_external_finding(_Finding("A third distinct claim."), actor=MODEL)
        rank = {did: n for n, did in enumerate(ids)}
        outcomes.add((
            rank[new.relationships[-1]],
            tuple(sorted(r.stage.value for r in system.store.discoveries.values())),
        ))
    assert len(outcomes) == 1


# --- inputs: deliberate, not accidental ---------------------------------------------

@pytest.mark.parametrize("conclusion", ["", "   ", "\n\t ", "  "])
def test_a_blank_conclusion_is_refused_and_nothing_is_written(conclusion):
    system = _real()
    with pytest.raises(ValueError, match="empty conclusion"):
        system.record_external_finding(_Finding(conclusion), actor=MODEL)
    assert not system.store.discoveries and not system.store.audit_events


@pytest.mark.parametrize("excerpt", ["   ", "\n", "\t "])
def test_a_blank_evidence_excerpt_is_refused(excerpt):
    system = _real()
    with pytest.raises(ValueError, match="evidence entry"):
        system.record_external_finding(_Finding("A claim.", evidence=(("notes.md", excerpt),)), actor=MODEL)
    assert not system.store.discoveries


def test_a_very_large_finding_is_accepted_and_still_deduplicated():
    big = "alpha beta gamma delta epsilon " * 20_000  # ~620k chars, well past the matcher window
    system = _real()
    system.record_external_finding(_Finding(big), actor=MODEL)
    assert _kind(system.record_external_finding(_Finding(big), actor=MODEL)) == "duplicate"


@pytest.mark.parametrize("variant", [
    pytest.param(lambda t: unicodedata.normalize("NFD", t.replace("governance", "gövernance")), id="NFD with a diacritic"),
    pytest.param(lambda t: unicodedata.normalize("NFKC", t), id="NFKC"),
    pytest.param(lambda t: t.replace("e", "e​", 3), id="zero-width spaces"),
    pytest.param(lambda t: t.replace("a", "а"), id="cyrillic homoglyphs"),
    pytest.param(lambda t: ("x" * 3000) + " " + t, id="3000-char prefix padding"),
])
def test_cosmetic_variants_of_a_finding_are_still_duplicates(variant):
    system = _real()
    system.record_external_finding(_Finding(BASE), actor=MODEL)
    assert _kind(system.record_external_finding(_Finding(variant(BASE)), actor=MODEL)) == "duplicate"


_LIMIT = ("KNOWN LIMIT, a measurement gap in CCCb (finding F-02 in the register), not in "
          "CCC: its duplicate measurement is case- and whitespace-sensitive and looks "
          "only at the first {window} characters. The variant is measured as a "
          "recurrence, which CCC counts as an independent occurrence, so a resubmission "
          "can lift the original from ANOMALY to PATTERN. Closing it needs a separately "
          "authorized change in CCCb. When that lands this test XPASSes and the marker "
          "must be removed.")


@pytest.mark.xfail(strict=True, reason=_LIMIT.format(window="50,000"))
@pytest.mark.parametrize("variant", [
    pytest.param(lambda t: t.upper(), id="upper case"),
    pytest.param(lambda t: "  ".join(t.split()), id="doubled whitespace"),
    pytest.param(lambda t: ("xqz " * 20_000) + t, id="80k padding prefix"),
])
def test_known_limit_trivial_resubmission_variants_are_not_yet_duplicates(variant):
    system = _real()
    system.record_external_finding(_Finding(BASE), actor=MODEL)
    assert _kind(system.record_external_finding(_Finding(variant(BASE)), actor=MODEL)) == "duplicate"
