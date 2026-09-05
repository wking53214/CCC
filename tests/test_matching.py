"""Direct tests for ccc.matching -- the anti-probability engine itself,
separate from test_external_finding.py's integration-level coverage.

Several of these formalize things found during a flood/adversarial pass
rather than a straight-line functional test -- see each docstring for what
specifically broke and why the check exists.
"""
from __future__ import annotations

import random
import time

from ccc.matching import (
    DUPLICATE_THRESHOLD,
    MAX_COMPARISON_LENGTH,
    MINIMUM_MATCH_LENGTH,
    anti_probability_of_coincidental_match,
    best_match_against,
)


def _random_text(length, seed):
    rng = random.Random(seed)
    alphabet = "abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ.,"
    return "".join(rng.choice(alphabet) for _ in range(length))


def test_floor_does_real_independent_work_not_just_look_like_a_safeguard():
    """MINIMUM_MATCH_LENGTH was originally 20, below the probability
    threshold's own ~23-character crossover -- meaning it never once fired
    on its own. It's 40 now; confirm there's a real band (30-39 chars)
    where the probability check alone would allow a match through but the
    floor still blocks it."""
    text = ("abcdefghij" * 5)[:35]
    r = anti_probability_of_coincidental_match(text, text)
    assert r.anti_probability < DUPLICATE_THRESHOLD  # probability alone says yes
    assert r.match_length < MINIMUM_MATCH_LENGTH       # floor says no
    assert r.implausible_as_coincidence is False        # floor wins


def test_repetitive_text_does_not_hang():
    """Originally: a 129,000-char repetitive string did not finish in 120
    seconds. Bounded now by MAX_COMPARISON_LENGTH; this asserts it stays
    fast, not just that it eventually returns."""
    text = "the system works well and processes data " * 3000  # ~129,000 chars
    start = time.perf_counter()
    result = anti_probability_of_coincidental_match(text, text)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"took {elapsed:.2f}s, expected well under 2s"
    assert result.match_length == MAX_COMPARISON_LENGTH


def test_autojunk_stays_off_ordinary_text_over_a_normal_alphabet_still_matches():
    """A prior fix (autojunk=True) was tried to solve the hang above and
    reverted: it silently returns match_length=0 for perfectly ordinary
    text once it's long enough for autojunk's frequency heuristic to
    misfire, over any everyday-sized alphabet. This is the regression test
    for that specific failure, not a generic sanity check."""
    short = _random_text(900, seed=1)
    long_ = _random_text(5000, seed=2)
    query = short + long_
    result = anti_probability_of_coincidental_match(query, long_)
    assert result.match_length > 0, (
        "autojunk (or any future change with the same effect) is silently "
        "destroying real matches on ordinary text again"
    )


def test_ranking_breaks_ties_by_match_length_not_insertion_order():
    """Once anti_probability underflows to exactly 0.0 (confirmed around
    800-830 characters), two candidates compare equal under probability
    alone. Before the fix, whichever candidate was checked first silently
    won regardless of which was the actually-stronger match. Checked both
    insertion orders -- the correct (stronger, longer) one must win either
    way."""
    weak = _random_text(900, seed=10)
    strong = _random_text(5000, seed=11)
    query = weak + strong

    order_a = best_match_against(query, {"weak": weak, "strong": strong})
    order_b = best_match_against(query, {"strong": strong, "weak": weak})

    assert order_a[0] == "strong"
    assert order_b[0] == "strong"
    assert order_a[1].match_length == order_b[1].match_length


def test_known_boilerplate_does_not_trigger_a_false_duplicate():
    """Real Apache-2.0 LICENSE text from two unrelated repos in this
    ecosystem produced anti_probability 0.0 over a 900-character overlap --
    "impossible as coincidence" for two files that share nothing but
    standard license boilerplate."""
    import os
    license_path = os.path.expanduser("~/HERALD/LICENSE")
    if not os.path.exists(license_path):
        return  # environment-dependent fixture; skip quietly if unavailable
    license_text = open(license_path).read()[:900]
    result = anti_probability_of_coincidental_match(license_text, license_text)
    assert result.explained_by_known_boilerplate is True
    assert result.implausible_as_coincidence is False


def test_a_genuine_match_still_wins_when_boilerplate_is_also_a_candidate():
    """The boilerplate exclusion must not let a boilerplate-only candidate
    "win" best-match and silently hide a real duplicate sitting in a
    different candidate."""
    import os
    license_path = os.path.expanduser("~/HERALD/LICENSE")
    if not os.path.exists(license_path):
        return
    license_text = open(license_path).read()[:900]
    genuine = _random_text(500, seed=99)
    query = license_text + genuine
    candidates = {"just_the_license": license_text, "the_real_duplicate": genuine}
    best = best_match_against(query, candidates)
    assert best is not None
    assert best[0] == "the_real_duplicate"
