"""Recurrence detection: is a new observation a fresh, independent
occurrence of a pattern already on record -- even when the specific
evidence is different?

This is the piece CCC's discovery.py (anomaly -> pattern -> mandate) never
had. discovery.py has the escalation machine; it had no way to notice that
observation #2 is the same underlying thing as observation #1 unless a
human said so. Without that, a stream of findings either stays a pile of
disconnected ANOMALYs or gets miscounted -- the anti-probability duplicate
check (ccc.matching) catches "literally the same content re-observed," but
that is the opposite signal: a re-observation is NOT an independent
occurrence and must not advance a pattern. Recurrence is the other case --
different content, same shape -- and it is what a 2nd occurrence means.

The method here is lexical, not semantic. A recurrence is recognized when
two observations share enough of their significant vocabulary (Jaccard
over concept sets). It will catch "the terminology inflated again" against
"vocabulary inflation recurred"; it will NOT catch the same idea phrased
with no shared words. That is a real limit, stated plainly: a semantic
version needs an embedding layer (Ecology has one), and this stays
deterministic, explainable, and dependency-free to match discovery.py's
own discipline about not guessing.

APM (William's own framework, and discovery.py's state machine):
1st occurrence = ANOMALY, 2nd = PATTERN (machine may advance -- pattern is
"investigate," not "act"), 3rd = MANDATE candidate (human establishment
only, never advanced here).
"""
from __future__ import annotations

import re
from typing import Optional

from .matching import _fold

# Jaccard over concept sets at or above this counts as the same pattern.
# 0.5 -- half the significant vocabulary shared -- is deliberately
# conservative: recurrence advances a discovery toward MANDATE territory,
# so a false recurrence is worse than a missed one.
RECURRENCE_THRESHOLD = 0.5

# A signature needs at least this many concepts to mean anything -- two
# three-word observations sharing two words is not a pattern, it's a
# coincidence of short text.
MINIMUM_SIGNATURE_SIZE = 4

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+/.\-]*")
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by",
    "at", "as", "from", "into", "that", "this", "it", "is", "are", "was", "were",
    "be", "been", "being", "has", "have", "had", "not", "which", "who", "what",
    "when", "where", "how", "all", "any", "both", "each", "more", "most", "other",
    "some", "such", "own", "same", "so", "than", "then", "there", "these", "those",
    "will", "would", "can", "could", "may", "might", "must", "should", "about",
})


def concept_set(text: str) -> frozenset:
    """The significant lowercase terms of a piece of text -- its concept
    signature. Folded (see matching._fold) first, so a homoglyph or
    diacritic variant produces the same signature."""
    folded = _fold(text).lower()
    return frozenset(
        w.strip(".-/")
        for w in _WORD.findall(folded)
        if len(w) > 2 and w.lower() not in _STOPWORDS
    )


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class RecurrenceDetector:
    """Concept-signature matching with an inverted index (concept -> the
    discovery_ids whose signature contains it), so checking a new
    observation costs O(concepts it shares with anything), not O(all prior
    discoveries)."""

    def __init__(self):
        self._signatures: dict = {}          # discovery_id -> frozenset
        self._concept_to_ids: dict = {}      # concept -> set(discovery_id)

    def register(self, discovery_id: str, text: str) -> frozenset:
        sig = concept_set(text)
        self._signatures[discovery_id] = sig
        for concept in sig:
            self._concept_to_ids.setdefault(concept, set()).add(discovery_id)
        return sig

    def find_recurrence(self, text: str) -> Optional[tuple]:
        """(best_id, best_jaccard, matches) or None.

        `best_id` / `best_jaccard` are the single strongest prior discovery
        whose concept signature overlaps this text at or above
        RECURRENCE_THRESHOLD. `matches` is the FULL tuple of
        ``(discovery_id, jaccard)`` for every prior discovery at or above
        the threshold, strongest first -- the whole recurrence cluster.

        The caller needs the whole cluster, not just the best match,
        because a pattern is a cluster of linked occurrences: occurrence
        #3 routinely scores highest against occurrence #2 (which is still
        an ANOMALY) rather than occurrence #1 (already advanced to
        PATTERN). Branching escalation on the single best lexical match
        would keep minting parallel PATTERNs and never reach the
        third-occurrence signal.

        A signature below MINIMUM_SIGNATURE_SIZE never matches -- too
        little to be a pattern."""
        sig = concept_set(text)
        if len(sig) < MINIMUM_SIGNATURE_SIZE:
            return None

        candidate_ids = set()
        for concept in sig:
            candidate_ids.update(self._concept_to_ids.get(concept, ()))

        matches = []
        for did in candidate_ids:
            other = self._signatures.get(did, frozenset())
            if len(other) < MINIMUM_SIGNATURE_SIZE:
                continue
            j = _jaccard(sig, other)
            if j >= RECURRENCE_THRESHOLD:
                matches.append((did, j))
        if not matches:
            return None
        matches.sort(key=lambda m: m[1], reverse=True)
        best_id, best_j = matches[0]
        return (best_id, best_j, tuple(matches))
