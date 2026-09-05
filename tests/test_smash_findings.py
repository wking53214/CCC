"""Regression tests for the four live exploits found in the Hulk-smash pass
against the original difflib-based matching.py, and closed by the
shingle-based rewrite. Each one was demonstrated working against the
merged code before this file existed -- these are that proof, kept.
"""
from __future__ import annotations

import os

from ccc.matching import anti_probability_of_coincidental_match

_LICENSE_PATH = os.path.expanduser("~/HERALD/LICENSE")
_REAL_DUPLICATE = ("This is the actual thing being resubmitted every time to "
                    "inflate the anomaly count exactly what the duplicate "
                    "check exists to catch here")


def _license_text():
    if not os.path.exists(_LICENSE_PATH):
        return None
    return open(_LICENSE_PATH).read()[:900]


def test_boilerplate_can_no_longer_camouflage_a_real_duplicate():
    """Original exploit: append known boilerplate (longer than the real
    payload) to both sides. The single-longest-match algorithm picked the
    boilerplate, got it excluded, and never even looked at the real
    139-character duplicate sitting next to it."""
    license_text = _license_text()
    if license_text is None:
        return
    text_a = "11111" + _REAL_DUPLICATE + "22222" + license_text + "33333"
    text_b = "44444" + _REAL_DUPLICATE + "55555" + license_text + "66666"
    r = anti_probability_of_coincidental_match(text_a, text_b)
    assert r.implausible_as_coincidence is True


def test_padding_can_no_longer_push_the_real_content_out_of_range():
    """Original exploit: MAX_COMPARISON_LENGTH truncated to a fixed prefix.
    ~2100 characters of padding pushed real duplicate content entirely out
    of the compared window -- total, trivial evasion."""
    junk_a, junk_b = "x" * 2100, "y" * 2100
    r = anti_probability_of_coincidental_match(junk_a + _REAL_DUPLICATE, junk_b + _REAL_DUPLICATE)
    assert r.implausible_as_coincidence is True


def test_cyrillic_homoglyphs_can_no_longer_evade_matching():
    """Original exploit: swap five Latin characters for visually-identical
    Cyrillic lookalikes throughout an otherwise word-for-word identical
    string. No normalization at all meant match_length dropped from the
    full string to 11."""
    latin = "This is the actual finding text that should be recognized as duplicate content here"
    cyrillic = (latin.replace("a", "а").replace("e", "е")
                .replace("o", "о").replace("p", "р").replace("c", "с"))
    assert latin != cyrillic  # confirm the swap actually happened
    r = anti_probability_of_coincidental_match(latin, cyrillic)
    assert r.implausible_as_coincidence is True


def test_stacked_evasion_attempts_are_still_caught():
    """All three techniques combined -- padding, then boilerplate, wrapped
    around the real payload -- in one text, both sides."""
    license_text = _license_text()
    if license_text is None:
        return
    cloaked_a = ("x" * 2200) + _REAL_DUPLICATE + license_text
    cloaked_b = ("y" * 2200) + _REAL_DUPLICATE + license_text
    r = anti_probability_of_coincidental_match(cloaked_a, cloaked_b)
    assert r.implausible_as_coincidence is True
