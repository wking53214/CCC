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
which is the point: a short coincidental match is plausible, a long one
is not.

## History: this module was rewritten once, adversarially, against itself

The first version used difflib's SequenceMatcher for a single longest-match.
It had three confirmed, live exploits before this rewrite:

1. Boilerplate-decoy evasion: since only the single longest match was ever
   returned, appending known boilerplate (longer than a real duplicate
   payload) to a finding made the boilerplate "win" the match slot, get
   correctly excluded as boilerplate, and silently hide the real duplicate
   sitting right next to it. Confirmed: a 139-char genuine duplicate,
   camouflaged by a 900-char license, was never even considered.
2. Truncation-padding evasion: MAX_COMPARISON_LENGTH truncated to a fixed
   prefix. Padding ~2100 characters of anything in front of real duplicate
   content pushed it entirely out of the compared window. Confirmed:
   match_length=0 for a text pair sharing 139 real characters of duplicate
   content.
3. Unicode homoglyph evasion: no normalization at all. Swapping five Latin
   characters for visually-identical Cyrillic lookalikes throughout an
   otherwise word-for-word identical string dropped the match from the
   full string length to match_length=11.

This version replaces the single-longest-match algorithm with exhaustive
shingle-based matching (every position, not sampled) specifically because
sampling introduces a real, separate recall risk: two independent texts'
shingle grids can be out of phase with each other near the boundary of a
short match. Exhaustive (stride 1) extraction has no such gap -- any shared
substring of at least SHINGLE_LENGTH characters is guaranteed to produce at
least one matching shingle in both texts, independent of position. This is
the same reasoning that ruled out a sampled/strided global index earlier in
this project; it's used here because the risk it was rejected for doesn't
apply at stride 1.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import NamedTuple, Optional

# Shannon, "Prediction and Entropy of Printed English" (1951): ~1.0-1.5 bits
# per character for English text. A conservative (lower, i.e. more willing
# to call something coincidence) point estimate within that published range.
ENGLISH_ENTROPY_BITS_PER_CHAR = 1.3

# A match shorter than this is too short for the entropy estimate to mean
# anything -- coincidental short matches are genuinely common. Also doubles
# as the shingle length for candidate detection (see SHINGLE_LENGTH below):
# there is no reason to index at finer granularity than the shortest match
# that could ever matter.
#
# Set deliberately above the threshold's own crossover point (~23 chars at
# the constants below), not just below it -- a floor at or under the
# threshold's natural cutoff does zero independent work. 40 is a real,
# separate margin. If ENGLISH_ENTROPY_BITS_PER_CHAR or DUPLICATE_THRESHOLD
# ever change, re-check this is still genuinely above the new crossover.
MINIMUM_MATCH_LENGTH = 40
SHINGLE_LENGTH = MINIMUM_MATCH_LENGTH

# Anti-probability below this is treated as "not plausible as coincidence."
# One in a billion -- a deliberately conservative, clearly-labeled choice,
# not a derived constant. Change it in the open, not by drift.
DUPLICATE_THRESHOLD = 1e-9

# The shingle-based approach below is O(n) to index and O(k) to query
# (k = number of actual shared shingles), not O(n^2) -- so this cap exists
# to bound total memory/work per finding, not to work around a quadratic
# algorithm. It can be far larger than the old difflib-era cap (2000) for
# exactly that reason. Still an honest limit, not a hidden one: content
# beyond this many characters is not indexed or compared.
MAX_COMPARISON_LENGTH = 50_000

# --- Cross-script confusables -------------------------------------------
#
# NFKD decomposition + combining-mark stripping (below) closes diacritic and
# fullwidth-form evasion -- the same technique HERALD uses, ported rather
# than imported to keep this module dependency-free of that repo. It does
# NOT close true cross-script homoglyphs (Cyrillic "е" U+0435 has no
# canonical decomposition relating it to Latin "e") -- HERALD's own code
# says exactly this about its own, more thorough version. This table is a
# narrow, honest mitigation for the common, documented Cyrillic/Greek
# lookalikes, the same spirit as the boilerplate list below: it closes the
# specific, verified case, not homoglyph evasion in general.
_CONFUSABLES = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "α": "a", "ο": "o", "ρ": "p", "υ": "y", "χ": "x", "і": "i",
}


def _fold(text: str) -> str:
    """Normalize before matching: NFKD decomposition + strip combining
    marks, then map known common confusables to their Latin lookalike.
    Matching happens on folded text; reported matched substrings are also
    folded -- this is a comparison-time transform, not a claim about what
    the original text actually was."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(_CONFUSABLES.get(ch, ch) for ch in stripped)


# --- Known boilerplate ---------------------------------------------------
#
# The entropy formula assumes natural-English prose (~1.3 bits/char). It is
# wrong on exactly the text most likely to be identical across genuinely
# unrelated things: license headers, standard disclaimers, copy-pasted
# templates -- near-zero real entropy by design, since they're SUPPOSED to
# be identical everywhere. Confirmed directly: the real Apache-2.0 LICENSE
# text from two unrelated repos in this ecosystem produced anti_probability
# 0.0 over a 900-character match -- "impossible as coincidence" for two
# files that share nothing but standard license boilerplate.
#
# A narrow, honest mitigation, not a general solution: it excludes a span
# that falls entirely within one of a short, maintained list of known
# common texts. It catches the specific, verified case (and similar common
# licenses). It does NOT solve low-entropy template text that isn't listed.
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


def _known_boilerplate_shingles() -> frozenset:
    """Every SHINGLE_LENGTH-character shingle appearing anywhere in the
    known-boilerplate references. Used only to keep ShingleIndex candidate
    sets from filling up with everything that happens to cite the same
    LICENSE file -- a real, measured cost (500 findings all citing one real
    LICENSE degraded candidate lookup back toward O(N)), not a correctness
    concern: anti_probability_of_coincidental_match's own boilerplate
    exclusion already handles correctness regardless of what gets indexed
    here. Precomputed once; boilerplate references don't change at runtime.
    """
    shingles = set()
    for reference in _KNOWN_BOILERPLATE:
        shingles.update(_shingle_positions(reference).keys())
    return frozenset(shingles)


class MatchResult(NamedTuple):
    anti_probability: float
    match_length: int
    explained_by_known_boilerplate: bool = False

    @property
    def implausible_as_coincidence(self) -> bool:
        return (self.match_length >= MINIMUM_MATCH_LENGTH
                and self.anti_probability < DUPLICATE_THRESHOLD
                and not self.explained_by_known_boilerplate)


def _shingle_positions(text: str) -> dict:
    """shingle string -> its first starting position in text. O(n)."""
    n = len(text)
    if n < SHINGLE_LENGTH:
        return {}
    positions = {}
    for i in range(n - SHINGLE_LENGTH + 1):
        shingle = text[i:i + SHINGLE_LENGTH]
        if shingle not in positions:
            positions[shingle] = i
    return positions


def _extend_match(text_a: str, text_b: str, pos_a: int, pos_b: int, length: int) -> tuple:
    """Given a confirmed exact match of `length` starting at pos_a/pos_b,
    extend it as far as it actually goes in both directions. O(match
    length), not O(n)."""
    end_a, end_b = pos_a + length, pos_b + length
    while end_a < len(text_a) and end_b < len(text_b) and text_a[end_a] == text_b[end_b]:
        end_a += 1
        end_b += 1
    start_a, start_b = pos_a, pos_b
    while start_a > 0 and start_b > 0 and text_a[start_a - 1] == text_b[start_b - 1]:
        start_a -= 1
        start_b -= 1
    return start_a, start_b, end_a - start_a


def _matching_spans(text_a: str, text_b: str) -> list:
    """All maximal exact matching spans of at least SHINGLE_LENGTH
    characters between the two texts -- not just the single longest.
    Finding candidates is O(n) (shingle intersection); extending each into
    its full span is O(span length). This is what makes the boilerplate
    exclusion safe: a longer boilerplate span existing elsewhere in the
    text can no longer hide a shorter, genuine one."""
    positions_a = _shingle_positions(text_a)
    positions_b = _shingle_positions(text_b)
    shared = positions_a.keys() & positions_b.keys()

    spans = []
    covered = []  # (start, end) ranges in text_a already accounted for
    for shingle in shared:
        pos_a, pos_b = positions_a[shingle], positions_b[shingle]
        if any(start <= pos_a < end for start, end in covered):
            continue
        start_a, _start_b, length = _extend_match(text_a, text_b, pos_a, pos_b, SHINGLE_LENGTH)
        covered.append((start_a, start_a + length))
        spans.append((text_a[start_a:start_a + length], length))
    return spans


def anti_probability_of_coincidental_match(text_a: str, text_b: str) -> MatchResult:
    """How implausible is the strongest genuine (non-boilerplate) overlap
    between these two texts, if it arose by chance between two independent
    sources?

    Considers every matching span of at least MINIMUM_MATCH_LENGTH
    characters, not just the single longest -- a longer boilerplate-only
    span must not be able to suppress a shorter genuine one sitting
    elsewhere in the same text. Both inputs are folded (see `_fold`) to
    close diacritic/fullwidth/common-confusable evasion before matching,
    and truncated to MAX_COMPARISON_LENGTH -- O(n) indexing means this can
    be a real, generous cap rather than a narrow one.
    """
    if not text_a or not text_b:
        return MatchResult(anti_probability=1.0, match_length=0)

    text_a = _fold(text_a)[:MAX_COMPARISON_LENGTH]
    text_b = _fold(text_b)[:MAX_COMPARISON_LENGTH]

    spans = _matching_spans(text_a, text_b)
    if not spans:
        return MatchResult(anti_probability=1.0, match_length=0)

    candidates = []
    for matched_text, length in spans:
        is_boilerplate = _explained_by_known_boilerplate(matched_text)
        anti_probability = 2.0 ** (-ENGLISH_ENTROPY_BITS_PER_CHAR * length)
        candidates.append(MatchResult(
            anti_probability=anti_probability,
            match_length=length,
            explained_by_known_boilerplate=is_boilerplate,
        ))

    non_boilerplate = [c for c in candidates if not c.explained_by_known_boilerplate]
    if non_boilerplate:
        return min(non_boilerplate, key=lambda c: (c.anti_probability, -c.match_length))
    # Nothing genuine found; report the longest boilerplate-explained span
    # so callers can see what matched, even though it won't be flagged.
    return max(candidates, key=lambda c: c.match_length)


class ShingleIndex:
    """Incremental index from shingle -> the set of ids whose text contains
    it, so a new finding can be checked against candidates that plausibly
    overlap without scanning every prior finding. Safe by construction (see
    module docstring): exhaustive, stride-1 shingle extraction means any
    shared span of at least SHINGLE_LENGTH characters is guaranteed to
    produce a shared shingle, independent of where it falls in either
    text -- unlike a sampled/strided index, there is no phase-alignment gap
    to silently miss a match through.

    This closes the O(N) per-insert candidate scan for the common case
    (genuinely novel content shares no shingle with anything, so lookup
    costs are independent of how many prior findings exist) without
    replacing the exact matching logic above -- it only narrows which
    existing texts are worth running that logic against.

    Known-boilerplate shingles are not indexed for candidate lookup (see
    _known_boilerplate_shingles): measured directly, 500 findings that all
    cited the same real LICENSE file degraded candidate-set size back to
    "everything" (499 of 499), because the license's own content indexes
    like any other. anti_probability_of_coincidental_match's correctness
    doesn't depend on this -- it still excludes boilerplate matches
    regardless of what's indexed -- this is purely a performance
    consideration for the common, realistic case of many findings citing
    the same standard license or template.
    """

    def __init__(self):
        self._shingle_to_ids: dict = {}
        self._texts: dict = {}
        self._boilerplate_shingles = _known_boilerplate_shingles()

    def candidates_for(self, text: str) -> dict:
        """Returns {id: stored_text} for every id sharing at least one
        shingle with `text` -- the set anti_probability_of_coincidental_match
        actually needs to be run against, not the whole index."""
        folded = _fold(text)[:MAX_COMPARISON_LENGTH]
        ids = set()
        for shingle in _shingle_positions(folded):
            if shingle in self._boilerplate_shingles:
                continue
            ids.update(self._shingle_to_ids.get(shingle, ()))
        return {i: self._texts[i] for i in ids}

    def add(self, item_id: str, text: str) -> None:
        folded = _fold(text)[:MAX_COMPARISON_LENGTH]
        self._texts[item_id] = text
        for shingle in _shingle_positions(folded):
            if shingle in self._boilerplate_shingles:
                continue
            self._shingle_to_ids.setdefault(shingle, set()).add(item_id)


def best_match_against(text: str, candidates: dict) -> Optional[tuple]:
    """candidates: {id: comparison_text}. Returns (id, MatchResult) for the
    strongest genuine match, or None if nothing clears MINIMUM_MATCH_LENGTH
    as a non-boilerplate span.

    Ranks by (anti_probability ascending, match_length descending): once a
    match is long enough, anti_probability underflows to exactly 0.0 in
    IEEE754, and two underflowed candidates compare equal under probability
    alone -- match_length never loses precision the way the probability
    does, so it breaks the tie correctly instead of by iteration order.
    """
    best = None
    for candidate_id, candidate_text in candidates.items():
        result = anti_probability_of_coincidental_match(text, candidate_text)
        if result.match_length < MINIMUM_MATCH_LENGTH or result.explained_by_known_boilerplate:
            continue
        key = (result.anti_probability, -result.match_length)
        if best is None or key < (best[1].anti_probability, -best[1].match_length):
            best = (candidate_id, result)
    return best
