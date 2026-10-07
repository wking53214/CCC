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

The matcher owns: the measurement, its thresholds, and its indexes.

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
CCC never gave the matcher. A wrong answer is a defect in the matcher, and it
fails loudly rather than becoming a record.
"""

from __future__ import annotations

from typing import Any, Collection, Optional, Protocol, runtime_checkable

__all__ = [
    "TextMatcher",
    "TextMatcherMissing",
    "require_matcher",
    "checked_duplicate",
    "checked_recurrence",
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
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"text matcher returned a non-numeric {what}: {value!r}")
    return float(value)


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
    return (_known_id(best_id, known, "recurrence"), _number(best_score, "score"), tuple(cluster))
