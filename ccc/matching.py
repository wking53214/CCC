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
from pathlib import Path
from typing import NamedTuple, Optional

# Shannon, "Prediction and Entropy of Printed English" (1951): ~1.0-1.5 bits
# per character for English text. A conservative (lower, i.e. more willing
# to call something coincidence) point estimate within that published range.
ENGLISH_ENTROPY_BITS_PER_CHAR = 1.3

# A match shorter than this is too short for the entropy estimate to mean
# anything -- coincidental short matches are genuinely common, and treating
# a 6-character overlap as "astronomically improbable" would be a formula
# artifact, not a real finding.
#
# Set deliberately above the threshold's own crossover point (~23 chars at
# the constants below), not just below it: a floor equal to or under the
# threshold's natural cutoff does zero independent work -- it looks like a
# safeguard but the probability check alone already requires more length
# than the floor demands, so the floor never once fires. 40 is a real,
# separate margin, not a number that happens to already be implied by the
# other constant. If ENGLISH_ENTROPY_BITS_PER_CHAR or DUPLICATE_THRESHOLD
# ever change, re-check this is still genuinely above the new crossover --
# it drifting back into redundancy silently is exactly what happened here.
MINIMUM_MATCH_LENGTH = 40

# Anti-probability below this is treated as "not plausible as coincidence."
# One in a billion -- a deliberately conservative, clearly-labeled choice,
# not a derived constant. Change it in the open, not by drift.
DUPLICATE_THRESHOLD = 1e-9

# difflib's SequenceMatcher is quadratic in the worst case on long input --
# confirmed directly, two ways: a 129,000-character repetitive string did
# not finish in 120 seconds, AND (this is the part worth flagging) even
# genuinely random, non-repetitive text is slow at scale purely from size --
# 50,000 identical random characters took 7 seconds. This length cap is the
# actual fix. autojunk=True was tried first and reverted: it's difflib's own
# documented mitigation for repetitive input, but confirmed directly to
# silently return match_length=0 on perfectly ordinary random text over a
# ~60-character alphabet (any text using a moderate, everyday alphabet at
# real length trips its "popular element" heuristic and stops matching
# correctly) -- worse than the problem it fixed, so autojunk stays off
# (explicit below, not left to a version-dependent default). Comparison is
# truncated, not the stored record -- the full text is still kept for
# audit, only the matching pass sees a bounded prefix. Honest limitation,
# not hidden: a genuine duplicate whose only overlap falls past this many
# characters won't be found. 2000 was chosen from measured timings (recall
# scales as size squared): ~10ms worst case even for two long, identical
# inputs, not from a length any real excerpt is expected to need.
MAX_COMPARISON_LENGTH = 2000

# The entropy formula assumes natural-English prose (~1.3 bits/char). It is
# wrong on exactly the text most likely to be identical across genuinely
# unrelated things: license headers, standard disclaimers, copy-pasted
# templates -- near-zero real entropy by design, since they're SUPPOSED to
# be identical everywhere. Confirmed directly: the real Apache-2.0 LICENSE
# text from two unrelated repos in this ecosystem produced anti_probability
# 0.0 over a 900-character match -- "impossible as coincidence" for two
# files that share nothing but standard license boilerplate.
#
# This is a narrow, honest mitigation, not a general solution: it excludes
# a match that falls entirely within one of a short, maintained list of
# known common texts. It catches the specific, verified case (and similar
# common licenses). It does NOT solve the deeper problem of low-entropy
# template text that isn't on this list -- that would need measuring the
# matched text's own empirical entropy rather than recognizing it by
# reference, and isn't attempted here.
_BOILERPLATE_DIR = Path(__file__).parent / "known_boilerplate"


def _load_known_boilerplate() -> tuple:
    if not _BOILERPLATE_DIR.is_dir():
        return ()
    return tuple(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(_BOILERPLATE_DIR.glob("*.txt"))
    )


_KNOWN_BOILERPLATE = _load_known_boilerplate()


def _explained_by_known_boilerplate(matched_text: str) -> bool:
    if len(matched_text) < MINIMUM_MATCH_LENGTH:
        return False
    return any(matched_text in reference for reference in _KNOWN_BOILERPLATE)


class MatchResult(NamedTuple):
    anti_probability: float
    match_length: int
    explained_by_known_boilerplate: bool = False

    @property
    def implausible_as_coincidence(self) -> bool:
        return (self.match_length >= MINIMUM_MATCH_LENGTH
                and self.anti_probability < DUPLICATE_THRESHOLD
                and not self.explained_by_known_boilerplate)


def anti_probability_of_coincidental_match(text_a: str, text_b: str) -> MatchResult:
    """How implausible is the longest exact overlap between these two texts,
    if it arose by chance between two independent sources?

    Uses the longest contiguous matching block (difflib, stdlib -- no new
    dependency), not overall similarity: a single long verbatim overlap
    inside otherwise-different text is the signal here, not how much of the
    two texts differ overall.

    Both inputs are truncated to MAX_COMPARISON_LENGTH before matching --
    performance-necessary given confirmed quadratic blowup on long text
    (repetitive or not), not a change to what's being measured: the entropy
    formula already treats any match past a few dozen characters as
    effectively certain, so bounding the input doesn't lose real signal for
    ordinary excerpts. autojunk is explicitly off: see MAX_COMPARISON_LENGTH's
    comment for why turning it on was tried and reverted.
    """
    if not text_a or not text_b:
        return MatchResult(anti_probability=1.0, match_length=0)
    text_a = text_a[:MAX_COMPARISON_LENGTH]
    text_b = text_b[:MAX_COMPARISON_LENGTH]
    matcher = difflib.SequenceMatcher(None, text_a, text_b, autojunk=False)
    match = matcher.find_longest_match(0, len(text_a), 0, len(text_b))
    length = match.size
    matched_text = text_a[match.a: match.a + match.size]
    anti_probability = 2.0 ** (-ENGLISH_ENTROPY_BITS_PER_CHAR * length)
    return MatchResult(
        anti_probability=anti_probability,
        match_length=length,
        explained_by_known_boilerplate=_explained_by_known_boilerplate(matched_text),
    )


def best_match_against(text: str, candidates: dict) -> Optional[tuple]:
    """candidates: {discovery_id: comparison_text}. Returns
    (discovery_id, MatchResult) for the strongest match, or None if nothing
    clears MINIMUM_MATCH_LENGTH at all.

    Ranks by (anti_probability ascending, match_length descending): once a
    match is long enough, anti_probability underflows to exactly 0.0 in
    IEEE754 (confirmed around 800-830 characters at these constants), and
    two underflowed candidates compare equal under anti_probability alone --
    which silently picked whichever candidate came first in iteration order,
    not the actually-stronger match. match_length never loses precision the
    way the probability does, so it breaks the tie correctly instead of by
    insertion order.
    """
    best = None
    for discovery_id, candidate_text in candidates.items():
        result = anti_probability_of_coincidental_match(text, candidate_text)
        if result.match_length < MINIMUM_MATCH_LENGTH:
            continue
        if result.explained_by_known_boilerplate:
            # Skip ranking a boilerplate-explained match at all, rather than
            # let it win "best" and then get rejected by the caller -- if it
            # won, a genuinely implausible match against a *different*
            # candidate would be silently discarded, since only one "best"
            # is ever returned.
            continue
        key = (result.anti_probability, -result.match_length)
        if best is None or key < (best[1].anti_probability, -best[1].match_length):
            best = (discovery_id, result)
    return best
