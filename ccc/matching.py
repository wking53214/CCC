"""Anti-probability matching: is this content overlap implausible as
coincidence, rather than "does this look similar."

The distinction, stated plainly: this never proves either side is genuine.
Two forged findings can match each other perfectly and this will say so
with total confidence -- consistency between two items is not evidence
either one is true. What it *can* honestly answer is a narrower question:
given how much information is actually in the matching text, how implausible
is it that two independent, honest processes produced that overlap by
accident? A short common phrase matching is unremarkable. A long, specific,
idiosyncratic match is not something two unrelated processes produce by
chance -- which licenses treating the two as the same thing observed twice,
never that the thing itself is real.

The math: Shannon's 1951 estimate of English text entropy is roughly
1.0-1.5 bits per character (published, not invented here). Modeling a
chance character-for-character match at that rate, the probability that an
L-character exact overlap arose by coincidence between two independent
texts is roughly 2^(-H*L). That number gets astronomically small fast --
which is the point: a 20-character coincidental match is plausible, a
300-character one is not.
"""
from __future__ import annotations

import difflib
from typing import NamedTuple, Optional

# Shannon, "Prediction and Entropy of Printed English" (1951): ~1.0-1.5 bits
# per character for English text. A conservative (lower, i.e. more willing
# to call something coincidence) point estimate within that published range.
ENGLISH_ENTROPY_BITS_PER_CHAR = 1.3

# A match shorter than this is too short for the entropy estimate to mean
# anything -- coincidental short matches are genuinely common, and treating
# a 6-character overlap as "astronomically improbable" would be a formula
# artifact, not a real finding.
MINIMUM_MATCH_LENGTH = 20

# Anti-probability below this is treated as "not plausible as coincidence."
# One in a billion -- a deliberately conservative, clearly-labeled choice,
# not a derived constant. Change it in the open, not by drift.
DUPLICATE_THRESHOLD = 1e-9


class MatchResult(NamedTuple):
    anti_probability: float
    match_length: int

    @property
    def implausible_as_coincidence(self) -> bool:
        return (self.match_length >= MINIMUM_MATCH_LENGTH
                and self.anti_probability < DUPLICATE_THRESHOLD)


def anti_probability_of_coincidental_match(text_a: str, text_b: str) -> MatchResult:
    """How implausible is the longest exact overlap between these two texts,
    if it arose by chance between two independent sources?

    Uses the longest contiguous matching block (difflib, stdlib -- no new
    dependency), not overall similarity: a single long verbatim overlap
    inside otherwise-different text is the signal here, not how much of the
    two texts differ overall.
    """
    if not text_a or not text_b:
        return MatchResult(anti_probability=1.0, match_length=0)
    matcher = difflib.SequenceMatcher(None, text_a, text_b, autojunk=False)
    match = matcher.find_longest_match(0, len(text_a), 0, len(text_b))
    length = match.size
    anti_probability = 2.0 ** (-ENGLISH_ENTROPY_BITS_PER_CHAR * length)
    return MatchResult(anti_probability=anti_probability, match_length=length)


def best_match_against(text: str, candidates: dict) -> Optional[tuple]:
    """candidates: {discovery_id: comparison_text}. Returns
    (discovery_id, MatchResult) for the strongest match, or None if nothing
    clears MINIMUM_MATCH_LENGTH at all."""
    best = None
    for discovery_id, candidate_text in candidates.items():
        result = anti_probability_of_coincidental_match(text, candidate_text)
        if result.match_length < MINIMUM_MATCH_LENGTH:
            continue
        if best is None or result.anti_probability < best[1].anti_probability:
            best = (discovery_id, result)
    return best
