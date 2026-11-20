"""What CCC needs from a text matcher, and the checks it applies to the answers.

Why this exists
---------------
CCC's job is remembering claims over time so a machine cannot rewrite what a
human thought. Part of that job is a guard on machine findings: re-submitting
the same finding must not count as a second, independent sighting, or a re-run
could push a hunch up the anomaly -> pattern -> mandate ladder on its own.

The guard is CCC's. The measurement it relies on (is this text a near copy of
an earlier one, and does it share enough vocabulary with an earlier one to be
the same pattern) is not: it is analysis, and it lives in CCCb
(``cccb.TextMatcher``), plugged in the same way Ecology's semantic provider is
(see ``ccc.semantic``). CCC never imports CCCb.

The boundary
------------
CCC owns: what a duplicate means (recorded and linked, never counted as an
occurrence), what a recurrence may do (raise an ANOMALY to a PATTERN, never to
a MANDATE), and the refusal when no matcher is attached.

The matcher owns: the measurement and its indexes. The two cut-offs are CCC's to
set (``CCCSystem(duplicate_threshold=..., recurrence_threshold=...)``). When CCC is
given a number it applies it to every answer, so a matcher that is looser than CCC
cannot change what counts as a match. Left unset, CCC uses whatever the matcher
uses, which is the earlier behaviour.

No matcher, no machine findings
-------------------------------
``CCCSystem.record_external_finding`` raises ``TextMatcherMissing`` when no
matcher is attached. Recording without the guard would let a re-run inflate an
anomaly into a pattern, and a guard that quietly did nothing looks exactly like
one that ran. Everything else in CCC works without a matcher.

Answers are checked
-------------------
A matcher's answers decide links and pattern advancement in a governed store,
so CCC checks their shape and refuses (``ValueError``) an answer naming an id
CCC never gave the matcher. Numbers are checked too: a score is a finite number
in [0, 1] (an anti-probability and a Jaccard overlap both are), a match length
is a positive integer, and a recurrence's best id is one of its own cluster.
With no cut-off set, CCC does not check a score against the matcher's threshold:
it acts on the matcher saying "this is a match". With one set, CCC drops any
answer that does not meet it. A matcher that reports a stricter cut-off than
CCC's is refused when the system is built, because CCC would never see the
matches in between. A wrong answer is a defect in the matcher, and it fails
loudly rather than becoming a record.
"""

from __future__ import annotations

import math
from typing import Any, Collection, Optional, Protocol, runtime_checkable

__all__ = [
    "TextMatcher",
    "TextMatcherMissing",
    "require_matcher",
    "checked_duplicate",
    "checked_recurrence",
    "checked_cutoff",
    "check_matcher_cutoffs",
    "apply_duplicate_cutoff",
    "apply_recurrence_cutoff",
]

INSTALL_HINT = (
    "attach one: CCCSystem(text_matcher=cccb.TextMatcher()), "
    "with CCCb installed (pip install -e '.[match]' from a checkout of ccc)"
)


@runtime_checkable
class TextMatcher(Protocol):
    """The measurement CCC plugs in. ``cccb.TextMatcher`` satisfies it."""

    def add(self, item_id: str, text: str) -> None: ...

    def duplicate_of(self, text: str) -> Optional[tuple[str, float, int]]: ...

    def recurrence_of(
        self, text: str
    ) -> Optional[tuple[str, float, tuple[tuple[str, float], ...]]]: ...


class TextMatcherMissing(RuntimeError):
    """Raised when a machine finding is recorded with no matcher attached."""


def require_matcher(matcher: Any) -> None:
    """Refuse a matcher that does not have the shape CCC needs."""
    if matcher is not None and not isinstance(matcher, TextMatcher):
        raise TypeError(
            "text_matcher must provide add, duplicate_of and recurrence_of "
            f"(ccc.text_matching.TextMatcher); got {type(matcher).__name__}"
        )


def _known_id(value: Any, known: Collection[str], what: str) -> str:
    if not isinstance(value, str) or value not in known:
        raise ValueError(f"text matcher named an unknown {what} id: {value!r}")
    return value


def _number(value: Any, what: str) -> float:
    """A finite number in [0, 1]. NaN, infinity and out-of-range values would
    be written into the record's method text as if they were measurements."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"text matcher returned a non-numeric {what}: {value!r}")
    try:
        number = float(value)
    except OverflowError:
        number = math.inf
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"text matcher returned an out-of-range {what} (need a finite number in [0, 1]): {value!r}")
    return number


def checked_duplicate(
    answer: Any, known: Collection[str]
) -> Optional[tuple[str, float, int]]:
    """A matcher's duplicate answer, or ValueError if it is malformed."""
    if answer is None:
        return None
    if not isinstance(answer, tuple) or len(answer) != 3:
        raise ValueError(f"text matcher returned a malformed duplicate answer: {answer!r}")
    item_id, anti_probability, match_length = answer
    if isinstance(match_length, bool) or not isinstance(match_length, int):
        raise ValueError(f"text matcher returned a non-integer match length: {match_length!r}")
    if match_length < 1:
        raise ValueError(f"text matcher returned a non-positive match length: {match_length!r}")
    return (
        _known_id(item_id, known, "duplicate"),
        _number(anti_probability, "anti-probability"),
        match_length,
    )


def checked_recurrence(
    answer: Any, known: Collection[str]
) -> Optional[tuple[str, float, tuple[tuple[str, float], ...]]]:
    """A matcher's recurrence answer, or ValueError if it is malformed."""
    if answer is None:
        return None
    if not isinstance(answer, tuple) or len(answer) != 3:
        raise ValueError(f"text matcher returned a malformed recurrence answer: {answer!r}")
    best_id, best_score, matches = answer
    if not isinstance(matches, tuple) or not matches:
        raise ValueError(f"text matcher returned no recurrence cluster: {matches!r}")
    cluster = []
    for pair in matches:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError(f"text matcher returned a malformed cluster entry: {pair!r}")
        cluster.append((_known_id(pair[0], known, "recurrence"), _number(pair[1], "score")))
    best = _known_id(best_id, known, "recurrence")
    if best not in {member for member, _score in cluster}:
        raise ValueError(f"text matcher named a best recurrence {best!r} outside its own cluster")
    return (best, _number(best_score, "score"), tuple(cluster))


def checked_cutoff(value: Any, what: str) -> Optional[float]:
    """None, or a finite number above 0 and at most 1. Anything else is refused, not clamped."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{what} must be a number or None; got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number) or not 0.0 < number <= 1.0:
        raise ValueError(f"{what} must be a finite number above 0 and at most 1; got {value!r}")
    return number


def check_matcher_cutoffs(
    matcher: Any, duplicate_threshold: Optional[float], recurrence_threshold: Optional[float]
) -> None:
    """Refuse a matcher whose own cut-off is stricter than CCC's.

    A stricter matcher hides the matches between its cut-off and CCC's, and CCC
    could never apply its own number to them. A matcher that does not report a
    cut-off cannot be checked here; CCC still applies its number to every answer.
    """
    if matcher is None:
        return
    theirs = getattr(matcher, "duplicate_threshold", None)
    if duplicate_threshold is not None and isinstance(theirs, (int, float)) and theirs < duplicate_threshold:
        raise ValueError(
            f"the text matcher's duplicate cut-off ({theirs!r}) is stricter than CCC's ({duplicate_threshold!r}); "
            "give the matcher CCC's number, for example cccb.TextMatcher(duplicate_threshold=...)"
        )
    theirs = getattr(matcher, "recurrence_threshold", None)
    if recurrence_threshold is not None and isinstance(theirs, (int, float)) and theirs > recurrence_threshold:
        raise ValueError(
            f"the text matcher's recurrence cut-off ({theirs!r}) is stricter than CCC's ({recurrence_threshold!r}); "
            "give the matcher CCC's number, for example cccb.TextMatcher(recurrence_threshold=...)"
        )


def apply_duplicate_cutoff(
    answer: Optional[tuple[str, float, int]], threshold: Optional[float]
) -> Optional[tuple[str, float, int]]:
    """A checked duplicate answer, or None when its anti-probability is not below CCC's cut-off."""
    if answer is None or threshold is None:
        return answer
    return answer if answer[1] < threshold else None


def apply_recurrence_cutoff(
    answer: Optional[tuple[str, float, tuple[tuple[str, float], ...]]], threshold: Optional[float]
) -> Optional[tuple[str, float, tuple[tuple[str, float], ...]]]:
    """A checked recurrence answer cut down to the matches at or above CCC's cut-off, or None if none remain."""
    if answer is None or threshold is None:
        return answer
    kept = tuple(m for m in answer[2] if m[1] >= threshold)
    if not kept:
        return None
    best = max(kept, key=lambda m: m[1])
    return (best[0], best[1], kept)

