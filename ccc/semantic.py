"""Optional semantic recurrence evidence.

CCC's recurrence detection is lexical: concept-set Jaccard over the text of a
finding. That is deliberate and it stays. It is also limited -- two findings
saying the same thing in different words do not overlap lexically, and the
recurrence they represent goes unseen.

This module lets CCC *consume* semantic similarity without knowing anything
about how it was produced.

The boundary
------------
CCC owns the interface, the threshold, the combination policy, and the
decision. An implementation owns the model, the tokenizer, the vectors, and
the search.

    CCC  ──defines──►  SemanticIndex (Protocol)
                              ▲
                              │ implements
                        Ecology adapter
                              │
                        ONNX / MiniLM / vector store

The dependency arrow points *at* CCC, never away from it. `ccc/` contains no
`import onnxruntime`, no `import chromadb`, no model file, and no vector
implementation -- and this module is where that stays true. CCC receives
*similarities*, never embeddings: it does not need to know the vectors are
384-dimensional, or that MiniLM produced them, and encoding that here would
turn a semantic contract into an implementation detail CCC has to track.

Semantic evidence is supplemental, not foundational
---------------------------------------------------
Two rules follow from CCC being a governed store rather than a search engine.

**A model's judgement does not silently become authoritative.** Lexical and
semantic agreement is a confirmed recurrence. Lexical alone is still a
recurrence -- that is the mechanism CCC already trusts. But semantic *alone*
is a **candidate**, surfaced for attention, not established as fact. The
machine may propose that two findings are related; it does not get to decide
it on its own evidence. Same principle as MANDATE staying human-only.

**Losing the provider must not cost CCC its integrity or availability**, only
its reach. A missing, broken or slow semantic index degrades recurrence to
lexical-only and the store keeps working exactly as it did before this module
existed. That invariant is tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence, runtime_checkable

# CCC's declared policy threshold. It lives here, in the governed store, and
# not in whatever computes the similarity: "how similar is similar enough to
# count" is a governance rule, and a rule a provider could set for itself is
# not a rule CCC is enforcing.
#
# UNCALIBRATED, and the number is provider-dependent in a way that matters.
# Measured against the first real provider (Ecology's all-MiniLM-L6-v2): a
# genuine paraphrase sharing almost no vocabulary scores about 0.33, and an
# unrelated pair from the same domain about 0.18. A threshold of 0.80 against
# that provider would never fire once -- semantic recurrence would import
# cleanly, run on every finding, and silently do nothing.
#
# 0.30 sits above the unrelated observation (0.18) and just under the
# paraphrase one (0.33). It is deliberately permissive, and that is safe here
# only because of the combination policy below: a semantic-only match is a
# CANDIDATE and establishes nothing. A false candidate costs a flag someone
# glances at; a threshold set so high the signal never fires costs the whole
# feature, silently. Given that asymmetry the error worth avoiding is the
# second one.
#
# Note what the measurements say about the provider, not just the threshold:
# 0.33 against 0.18 is separation of only 1.8x, so semantic recurrence with
# this embedder will be noisy wherever the line is drawn. That is a property
# of all-MiniLM-L6-v2 on this domain and not something a better threshold
# fixes. It is another reason semantic-only may not establish a recurrence.
DEFAULT_SEMANTIC_THRESHOLD = 0.30

# How many neighbours to ask for. Bounded so a provider cannot flood a
# decision record with hundreds of near-misses.
DEFAULT_QUERY_LIMIT = 10


@dataclass(frozen=True)
class SemanticMatch:
    """One semantically similar prior finding, and how similar it was."""
    finding_id: str
    similarity: float


class SemanticUnavailable(Exception):
    """The provider cannot answer right now.

    Declared here so an adapter can say "I am unavailable" distinctly from
    "I failed in a way nobody anticipated". Both degrade to lexical-only, but
    only the second is worth waking someone up about, and a bare
    `except Exception` cannot tell them apart.
    """


@runtime_checkable
class SemanticIndex(Protocol):
    """Optional semantic recurrence provider.

    CCC owns this interface. Implementations live outside CCC.
    """

    def add(self, finding_id: str, text: str) -> None:
        """Index a finding for future semantic recurrence queries."""
        ...

    def query(self, text: str, *, limit: int = DEFAULT_QUERY_LIMIT) -> Sequence[SemanticMatch]:
        """Return semantically similar existing findings, strongest first."""
        ...


# --- decisions --------------------------------------------------------------

DECISION_CONFIRMED = "confirmed"          # both signals agree
DECISION_LEXICAL_ONLY = "lexical_only"    # the mechanism CCC already trusts
DECISION_SEMANTIC_ONLY = "semantic_only"  # a candidate, not an establishment
DECISION_NONE = "none"


def combine_recurrence(*, lexical_match: bool, semantic_match: bool) -> str:
    """The combination policy, as a table rather than as scattered ifs.

        lexical  semantic   decision
        -------  --------   ------------------------------------------
        yes      yes        confirmed
        yes      no         lexical_only     (still a recurrence)
        no       yes        semantic_only    (a CANDIDATE, not a fact)
        no       no         none

    The asymmetry between rows 2 and 3 is the point. Lexical alone is
    sufficient because it is deterministic, inspectable, and already CCC's
    mechanism. Semantic alone rests entirely on a model's similarity score,
    so it surfaces a possibility and stops there.
    """
    if lexical_match and semantic_match:
        return DECISION_CONFIRMED
    if lexical_match:
        return DECISION_LEXICAL_ONLY
    if semantic_match:
        return DECISION_SEMANTIC_ONLY
    return DECISION_NONE


def is_established_recurrence(decision: str) -> bool:
    """Whether a decision may drive escalation on its own.

    `semantic_only` deliberately returns False. A candidate is recorded and
    visible; it does not advance anything.
    """
    return decision in (DECISION_CONFIRMED, DECISION_LEXICAL_ONLY)


@dataclass(frozen=True)
class RecurrenceDecision:
    """A recurrence decision, with enough provenance to re-examine it later.

    Recording only `recurrence = true` would leave "why did CCC decide these
    two findings were related?" answerable only by re-running whatever model
    was loaded at the time -- which may no longer exist, and which would
    anyway be a different question (what does the model say *now*). The
    threshold, the provider, and the actual scores are kept so the decision
    can be audited against the evidence that produced it.
    """
    decision: str
    lexical_match: bool
    semantic_match: bool
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD
    semantic_matches: tuple[SemanticMatch, ...] = ()
    semantic_provider: Optional[str] = None
    semantic_error: Optional[str] = None

    @property
    def established(self) -> bool:
        return is_established_recurrence(self.decision)

    @property
    def is_candidate(self) -> bool:
        """A relationship the machine noticed and may not establish alone."""
        return self.decision == DECISION_SEMANTIC_ONLY

    def describe(self) -> str:
        """One line for an audit trail."""
        parts = [f"decision={self.decision}",
                 f"lexical={self.lexical_match}",
                 f"semantic={self.semantic_match}"]
        if self.semantic_provider:
            parts.append(f"provider={self.semantic_provider}")
        if self.semantic_matches:
            best = self.semantic_matches[0]
            parts.append(f"nearest={best.finding_id}@{best.similarity:.3f}")
            parts.append(f"threshold={self.semantic_threshold}")
        if self.semantic_error:
            parts.append(f"semantic_error={self.semantic_error}")
        return " ".join(parts)


def check_threshold_is_reachable(
    index: Optional[SemanticIndex],
    threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> Optional[str]:
    """Warn when a declared threshold no similarity from this provider can
    reach, or None when it looks reachable.

    A gate set above a provider's ceiling does not fail -- it imports, runs on
    every finding, and never fires. That is the worst failure shape for a
    governed store, because the audit trail fills with correct-looking
    lexical_only decisions and nothing indicates a whole signal is dead.

    Providers opt in by exposing `expected_similarity_range()`. One that does
    not is not interrogated and not assumed broken; this returns None and the
    caller learns nothing, which is honest.
    """
    if index is None:
        return None
    describe = getattr(index, "expected_similarity_range", None)
    if not callable(describe):
        return None
    try:
        observed = describe() or {}
        paraphrase = float(observed.get("paraphrase"))
    except Exception:  # noqa: BLE001
        return None
    if threshold > paraphrase:
        return (
            f"threshold {threshold} exceeds this provider's observed "
            f"paraphrase similarity {paraphrase} "
            f"({observed.get('provider', 'unknown provider')}) -- semantic "
            f"recurrence will never fire"
        )
    return None


def provider_name(index: Optional[SemanticIndex]) -> Optional[str]:
    """A stable name for the provider, for the audit record."""
    if index is None:
        return None
    return getattr(index, "provider_name", None) or type(index).__name__


def _validated(raw) -> tuple[SemanticMatch, ...]:
    """The provider's answer, checked and ordered strongest first.

    Measured 2026-09-08: a non-numeric similarity escaped both `except`
    clauses (the comparison ran outside the guard) and took recording
    down; a provider returning ascending order made the recorded "nearest"
    the weakest qualifying match, because CCC trusted the docstring's
    "strongest first" without enforcing it. A similarity that is not a
    finite number in [0, 1] is a provider failure, handled like any other.
    """
    import math
    out = []
    for m in raw:
        similarity = getattr(m, "similarity", None)
        finding_id = getattr(m, "finding_id", None)
        if isinstance(similarity, bool) or not isinstance(similarity, (int, float)) or not math.isfinite(similarity):
            raise ValueError(f"provider returned a non-numeric similarity {similarity!r} for {finding_id!r}")
        if not 0.0 <= similarity <= 1.0:
            raise ValueError(f"provider returned similarity {similarity!r} outside [0, 1] for {finding_id!r}")
        if not isinstance(finding_id, str) or not finding_id:
            raise ValueError(f"provider returned a match with no finding id: {m!r}")
        out.append(SemanticMatch(finding_id, float(similarity)))
    return tuple(sorted(out, key=lambda m: -m.similarity))


def evaluate_recurrence(
    *,
    text: str,
    lexical_match: bool,
    semantic_index: Optional[SemanticIndex] = None,
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
    limit: int = DEFAULT_QUERY_LIMIT,
) -> RecurrenceDecision:
    """Combine CCC's lexical verdict with optional semantic evidence.

    Never raises on account of the semantic provider. A provider that is
    absent, unavailable, or broken produces a lexical-only decision with the
    reason recorded -- because losing the provider must cost CCC reach, not
    integrity or availability.
    """
    if semantic_index is None:
        return RecurrenceDecision(
            decision=combine_recurrence(lexical_match=lexical_match, semantic_match=False),
            lexical_match=lexical_match,
            semantic_match=False,
            semantic_threshold=semantic_threshold,
        )

    name = provider_name(semantic_index)
    try:
        matches = _validated(semantic_index.query(text, limit=limit))
    except SemanticUnavailable as exc:
        return RecurrenceDecision(
            decision=combine_recurrence(lexical_match=lexical_match, semantic_match=False),
            lexical_match=lexical_match, semantic_match=False,
            semantic_threshold=semantic_threshold, semantic_provider=name,
            semantic_error=f"unavailable: {exc}" if str(exc) else "unavailable",
        )
    except Exception as exc:  # noqa: BLE001 - see SemanticUnavailable's docstring
        # An unanticipated provider failure. Still degrades rather than
        # propagating, but it is recorded differently from a declared
        # unavailability so the two are distinguishable in the audit trail.
        return RecurrenceDecision(
            decision=combine_recurrence(lexical_match=lexical_match, semantic_match=False),
            lexical_match=lexical_match, semantic_match=False,
            semantic_threshold=semantic_threshold, semantic_provider=name,
            semantic_error=f"{type(exc).__name__}: {exc}",
        )

    qualifying = tuple(m for m in matches if m.similarity >= semantic_threshold)
    return RecurrenceDecision(
        decision=combine_recurrence(lexical_match=lexical_match,
                                    semantic_match=bool(qualifying)),
        lexical_match=lexical_match,
        semantic_match=bool(qualifying),
        semantic_threshold=semantic_threshold,
        semantic_matches=matches,
        semantic_provider=name,
    )
