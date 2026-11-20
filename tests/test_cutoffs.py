"""CCC owns the duplicate and recurrence cut-offs.

When CCC is given a number it applies it to every matcher answer, and it refuses
a matcher that reports a stricter one. With no number, behaviour is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pytest

from ccc import Actor, CCCSystem
from ccc.text_matching import apply_duplicate_cutoff, apply_recurrence_cutoff

MODEL = Actor.model("ecology")


@dataclass(frozen=True)
class _Finding:
    conclusion: str
    method: str = "ecology.search"
    source_material: Tuple[str, ...] = ("notes.md",)
    confidence: Optional[float] = 0.6
    verified: bool = True
    evidence: Tuple[Tuple[str, str], ...] = ()


class _Scripted:
    """A matcher whose answers the test dictates. Optionally reports its own cut-offs."""

    def __init__(self, duplicate=None, recurrence=None, **reported):
        self.duplicate, self.recurrence = duplicate, recurrence
        for name, value in reported.items():
            setattr(self, name, value)

    def add(self, item_id, text):
        pass

    def duplicate_of(self, text):
        return self.duplicate

    def recurrence_of(self, text):
        return self.recurrence


def _system(matcher, **cutoffs):
    return CCCSystem(text_matcher=matcher, private_source_markers=(), allow_unguarded_writes=True,
                     allow_unverified_humans=True, **cutoffs)


def _kind(record) -> str:
    if "duplicate detection" in record.method:
        return "duplicate"
    if "recurrence of" in record.method:
        return "recurrence"
    return "independent"


def _second_finding(duplicate=None, recurrence=None, **cutoffs):
    """Record a first finding, then a second one that the scripted matcher answers about the first."""
    matcher = _Scripted()
    system = _system(matcher, **cutoffs)
    first = system.record_external_finding(_Finding("A first, plainly worded claim about ledgers."), actor=MODEL)
    matcher.duplicate = (first.discovery_id, duplicate[0], duplicate[1]) if duplicate else None
    matcher.recurrence = (
        (first.discovery_id, recurrence, ((first.discovery_id, recurrence),)) if recurrence is not None else None
    )
    return system.record_external_finding(_Finding("A second claim, worded differently."), actor=MODEL)


# --- duplicate ----------------------------------------------------------------------

def test_with_no_cutoff_the_matchers_duplicate_answer_is_acted_on():
    assert _kind(_second_finding(duplicate=(1e-6, 50))) == "duplicate"


def test_a_stricter_duplicate_cutoff_of_ccc_overrides_a_looser_matcher():
    assert _kind(_second_finding(duplicate=(1e-6, 50), duplicate_threshold=1e-9)) == "independent"


def test_a_duplicate_below_ccc_cutoff_still_counts():
    assert _kind(_second_finding(duplicate=(1e-12, 50), duplicate_threshold=1e-9)) == "duplicate"


# --- recurrence ---------------------------------------------------------------------

def test_with_no_cutoff_the_matchers_recurrence_answer_is_acted_on():
    assert _kind(_second_finding(recurrence=0.4)) == "recurrence"


def test_a_higher_recurrence_cutoff_of_ccc_overrides_a_looser_matcher():
    assert _kind(_second_finding(recurrence=0.4, recurrence_threshold=0.5)) == "independent"


def test_a_recurrence_at_ccc_cutoff_still_counts():
    assert _kind(_second_finding(recurrence=0.5, recurrence_threshold=0.5)) == "recurrence"


def test_the_recurrence_cluster_is_cut_down_to_the_matches_that_meet_the_cutoff():
    answer = ("a", 0.9, (("a", 0.9), ("b", 0.6), ("c", 0.4)))
    assert apply_recurrence_cutoff(answer, 0.5) == ("a", 0.9, (("a", 0.9), ("b", 0.6)))
    assert apply_recurrence_cutoff(answer, 0.95) is None
    assert apply_recurrence_cutoff(answer, None) == answer
    assert apply_recurrence_cutoff(None, 0.5) is None


def test_the_duplicate_helper_keeps_only_answers_below_the_cutoff():
    answer = ("a", 1e-6, 50)
    assert apply_duplicate_cutoff(answer, 1e-3) == answer
    assert apply_duplicate_cutoff(answer, 1e-9) is None
    assert apply_duplicate_cutoff(answer, 1e-6) is None  # at the cut-off is not below it
    assert apply_duplicate_cutoff(answer, None) == answer


# --- the matcher is checked against CCC's numbers ------------------------------------

def test_a_matcher_with_a_stricter_duplicate_cutoff_is_refused_at_construction():
    with pytest.raises(ValueError, match="duplicate cut-off"):
        _system(_Scripted(duplicate_threshold=1e-12), duplicate_threshold=1e-9)


def test_a_matcher_with_a_stricter_recurrence_cutoff_is_refused_at_construction():
    with pytest.raises(ValueError, match="recurrence cut-off"):
        _system(_Scripted(recurrence_threshold=0.6), recurrence_threshold=0.5)


def test_a_matcher_with_equal_or_looser_cutoffs_is_accepted():
    _system(_Scripted(duplicate_threshold=1e-9, recurrence_threshold=0.5),
            duplicate_threshold=1e-9, recurrence_threshold=0.5)
    _system(_Scripted(duplicate_threshold=1e-3, recurrence_threshold=0.2),
            duplicate_threshold=1e-9, recurrence_threshold=0.5)


def test_a_matcher_that_reports_nothing_is_accepted_and_still_filtered():
    _system(_Scripted(), duplicate_threshold=1e-9, recurrence_threshold=0.5)


def test_the_pinned_real_matcher_reports_its_cutoffs_and_is_checked_against_ccc():
    cccb = pytest.importorskip("cccb")
    ok = cccb.TextMatcher(duplicate_threshold=1e-9, recurrence_threshold=0.5)
    assert (ok.duplicate_threshold, ok.recurrence_threshold) == (1e-9, 0.5)
    _system(ok, duplicate_threshold=1e-9, recurrence_threshold=0.5)
    _system(cccb.TextMatcher(), duplicate_threshold=1e-9, recurrence_threshold=0.5)  # defaults are looser
    with pytest.raises(ValueError, match="duplicate cut-off"):
        _system(cccb.TextMatcher(duplicate_threshold=1e-12), duplicate_threshold=1e-9)
    with pytest.raises(ValueError, match="recurrence cut-off"):
        _system(cccb.TextMatcher(recurrence_threshold=0.9), recurrence_threshold=0.5)


def test_unset_cutoffs_do_not_check_the_matcher_at_all():
    system = _system(_Scripted(duplicate_threshold=1e-300, recurrence_threshold=1.0))
    assert system.duplicate_threshold is None and system.recurrence_threshold is None


# --- bad numbers are refused, not clamped --------------------------------------------

@pytest.mark.parametrize("bad", [0, -0.1, 1.5, float("nan"), float("inf")])
def test_an_out_of_range_cutoff_is_refused(bad):
    with pytest.raises(ValueError):
        _system(_Scripted(), duplicate_threshold=bad)
    with pytest.raises(ValueError):
        _system(_Scripted(), recurrence_threshold=bad)


@pytest.mark.parametrize("bad", ["0.5", True, [0.5]])
def test_a_non_number_cutoff_is_refused(bad):
    with pytest.raises(TypeError):
        _system(_Scripted(), duplicate_threshold=bad)


def test_the_cutoffs_survive_a_save_and_load_only_when_given_again(tmp_path):
    system = _system(_Scripted(), duplicate_threshold=1e-9, recurrence_threshold=0.5)
    path = tmp_path / "store.json"
    system.save(path)
    reloaded = CCCSystem.load(path, text_matcher=_Scripted(), private_source_markers=(),
                              allow_unguarded_writes=True, allow_unverified_humans=True,
                              duplicate_threshold=1e-9, recurrence_threshold=0.5)
    assert (reloaded.duplicate_threshold, reloaded.recurrence_threshold) == (1e-9, 0.5)
    plain = CCCSystem.load(path, text_matcher=_Scripted(), private_source_markers=(),
                           allow_unguarded_writes=True, allow_unverified_humans=True)
    assert plain.duplicate_threshold is None and plain.recurrence_threshold is None
