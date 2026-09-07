"""Semantic recurrence evidence, and the boundary that keeps it optional.

No model runs in this file. That is the point of the protocol: CCC's CI must
never need onnxruntime, a tokenizer, or a vector store to test the governance
policy those things feed.

The tests that matter most are the availability ones. Semantic recurrence is
supplemental, and if losing it could break CCC, it would not be supplemental.
"""

from __future__ import annotations

import pytest

from ccc.semantic import (
    DECISION_CONFIRMED,
    DECISION_LEXICAL_ONLY,
    DECISION_NONE,
    DECISION_SEMANTIC_ONLY,
    DEFAULT_SEMANTIC_THRESHOLD,
    RecurrenceDecision,
    SemanticIndex,
    SemanticMatch,
    SemanticUnavailable,
    combine_recurrence,
    evaluate_recurrence,
    is_established_recurrence,
)


class FakeSemanticIndex:
    """A provider that returns whatever it was told to, and runs no model."""

    provider_name = "fake"

    def __init__(self, matches=None):
        self.matches = matches or {}
        self.added: list[tuple[str, str]] = []

    def add(self, finding_id: str, text: str) -> None:
        self.added.append((finding_id, text))

    def query(self, text: str, *, limit: int = 10):
        return self.matches.get(text, [])[:limit]


class UnavailableIndex:
    provider_name = "unavailable-provider"

    def add(self, finding_id: str, text: str) -> None:
        raise SemanticUnavailable("embedder not loaded")

    def query(self, text: str, *, limit: int = 10):
        raise SemanticUnavailable("embedder not loaded")


class BrokenIndex:
    provider_name = "broken-provider"

    def add(self, finding_id: str, text: str) -> None:
        raise RuntimeError("segfault in the tokenizer")

    def query(self, text: str, *, limit: int = 10):
        raise RuntimeError("segfault in the tokenizer")


# ---------------------------------------------------------------------------
# The combination policy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lexical,semantic,expected", [
    (True,  True,  DECISION_CONFIRMED),
    (True,  False, DECISION_LEXICAL_ONLY),
    (False, True,  DECISION_SEMANTIC_ONLY),
    (False, False, DECISION_NONE),
])
def test_the_combination_table(lexical, semantic, expected):
    assert combine_recurrence(lexical_match=lexical, semantic_match=semantic) == expected


def test_semantic_alone_is_a_candidate_and_may_not_establish_recurrence():
    """The load-bearing asymmetry. Lexical alone is sufficient because it is
    deterministic, inspectable, and already CCC's mechanism. Semantic alone
    rests entirely on a model's similarity score, so it surfaces a
    possibility and stops there -- a model's judgement does not silently
    become authoritative in a governed store."""
    assert is_established_recurrence(DECISION_SEMANTIC_ONLY) is False
    assert is_established_recurrence(DECISION_LEXICAL_ONLY) is True
    assert is_established_recurrence(DECISION_CONFIRMED) is True
    assert is_established_recurrence(DECISION_NONE) is False


def test_a_semantic_only_decision_reports_itself_as_a_candidate():
    fake = FakeSemanticIndex({"finding": [SemanticMatch("prior-17", 0.91)]})
    decision = evaluate_recurrence(text="finding", lexical_match=False, semantic_index=fake)
    assert decision.decision == DECISION_SEMANTIC_ONLY
    assert decision.is_candidate is True
    assert decision.established is False


# ---------------------------------------------------------------------------
# Threshold ownership
# ---------------------------------------------------------------------------

def test_the_threshold_is_ccc_policy_not_the_providers():
    """The provider reports similarities; CCC decides what counts. A rule the
    provider could set for itself is not a rule CCC is enforcing."""
    fake = FakeSemanticIndex({"finding": [SemanticMatch("prior-17", 0.85)]})

    lenient = evaluate_recurrence(text="finding", lexical_match=False,
                                  semantic_index=fake, semantic_threshold=0.80)
    strict = evaluate_recurrence(text="finding", lexical_match=False,
                                 semantic_index=fake, semantic_threshold=0.90)

    assert lenient.semantic_match is True
    assert strict.semantic_match is False
    assert strict.decision == DECISION_NONE


def test_below_threshold_neighbours_are_still_recorded():
    """A near-miss is evidence about the decision even though it did not
    qualify -- 'the closest thing we found scored 0.62' is exactly what a
    later reviewer needs."""
    fake = FakeSemanticIndex({"finding": [SemanticMatch("prior-17", 0.22)]})
    decision = evaluate_recurrence(text="finding", lexical_match=True, semantic_index=fake)

    assert decision.decision == DECISION_LEXICAL_ONLY
    assert decision.semantic_match is False
    assert decision.semantic_matches[0].similarity == 0.22


def test_agreement_between_both_signals_is_confirmed():
    fake = FakeSemanticIndex({"finding": [SemanticMatch("prior-17", 0.91)]})
    decision = evaluate_recurrence(text="finding", lexical_match=True, semantic_index=fake)
    assert decision.decision == DECISION_CONFIRMED
    assert decision.established is True


# ---------------------------------------------------------------------------
# Availability: the invariant that makes this supplemental
# ---------------------------------------------------------------------------

def test_no_provider_at_all_leaves_lexical_recurrence_intact():
    """Removing the provider must not change CCC's ability to detect lexical
    recurrence. If it could, the feature would not be optional."""
    decision = evaluate_recurrence(text="finding", lexical_match=True, semantic_index=None)
    assert decision.decision == DECISION_LEXICAL_ONLY
    assert decision.lexical_match is True
    assert decision.semantic_match is False
    assert decision.semantic_provider is None


def test_an_unavailable_provider_degrades_rather_than_raising():
    decision = evaluate_recurrence(text="finding", lexical_match=True,
                                   semantic_index=UnavailableIndex())
    assert decision.decision == DECISION_LEXICAL_ONLY
    assert decision.semantic_error.startswith("unavailable")
    assert decision.semantic_provider == "unavailable-provider"


def test_an_unexpectedly_broken_provider_also_degrades():
    """A provider failing in a way nobody anticipated must not take the
    governed store down with it."""
    decision = evaluate_recurrence(text="finding", lexical_match=True,
                                   semantic_index=BrokenIndex())
    assert decision.decision == DECISION_LEXICAL_ONLY
    assert "RuntimeError" in decision.semantic_error


def test_declared_unavailability_is_distinguishable_from_an_unknown_failure():
    """Both degrade, but only one is worth waking someone up about, and a
    bare `except Exception` cannot tell them apart."""
    unavailable = evaluate_recurrence(text="f", lexical_match=True,
                                      semantic_index=UnavailableIndex())
    broken = evaluate_recurrence(text="f", lexical_match=True, semantic_index=BrokenIndex())
    assert unavailable.semantic_error != broken.semantic_error
    assert "RuntimeError" not in unavailable.semantic_error


def test_a_failing_provider_cannot_manufacture_a_recurrence():
    """The dangerous direction: a broken provider must not fail *open*."""
    for provider in (UnavailableIndex(), BrokenIndex()):
        decision = evaluate_recurrence(text="f", lexical_match=False, semantic_index=provider)
        assert decision.decision == DECISION_NONE
        assert decision.semantic_match is False


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def test_the_decision_records_enough_to_re_examine_it():
    """'Why did CCC decide these two findings were related?' has to be
    answerable without re-running whatever model was loaded at the time --
    which may no longer exist, and would anyway answer a different question."""
    fake = FakeSemanticIndex({"finding": [SemanticMatch("F-1842", 0.91),
                                          SemanticMatch("F-0031", 0.83)]})
    decision = evaluate_recurrence(text="finding", lexical_match=False,
                                   semantic_index=fake, semantic_threshold=0.80)

    assert decision.semantic_provider == "fake"
    assert decision.semantic_threshold == 0.80
    assert decision.semantic_matches[0].finding_id == "F-1842"
    line = decision.describe()
    for expected in ("decision=semantic_only", "provider=fake",
                     "nearest=F-1842@0.910", "threshold=0.8"):
        assert expected in line, line


def test_provider_name_falls_back_to_the_class_name():
    class Unnamed:
        def add(self, finding_id, text): ...
        def query(self, text, *, limit=10): return []

    decision = evaluate_recurrence(text="f", lexical_match=True, semantic_index=Unnamed())
    assert decision.semantic_provider == "Unnamed"


# ---------------------------------------------------------------------------
# The boundary itself
# ---------------------------------------------------------------------------

def test_ccc_stays_free_of_model_dependencies():
    """The rule this module exists to keep true: nothing under ccc/ imports a
    model runtime, a tokenizer, or a vector store. Asserted rather than
    trusted, because the failure is silent -- everything still works on the
    machine where the dependency happens to be installed."""
    import ast
    import pathlib

    # Parsed, not grepped. A text search matches this module's own docstring,
    # which names the forbidden imports in order to forbid them -- and a
    # boundary test that fires on its own prose is a test nobody keeps.
    forbidden = {"onnxruntime", "sentence_transformers", "chromadb", "torch",
                 "transformers", "numpy", "faiss", "scipy", "sklearn"}
    offenders = []
    for path in pathlib.Path(__file__).parent.parent.joinpath("ccc").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if name in forbidden:
                    offenders.append(f"{path.name}:{node.lineno} imports {name}")
    assert not offenders, f"model dependency leaked into CCC: {offenders}"


def test_the_protocol_accepts_any_structural_implementation():
    """A provider does not subclass anything -- it just has the two methods.
    Ecology's adapter must not have to import from CCC to satisfy this."""
    assert isinstance(FakeSemanticIndex(), SemanticIndex)


def test_ccc_receives_similarities_not_embeddings():
    """The contract is semantic, not implementation-specific. CCC never sees
    a vector, so it never acquires an opinion about dimensionality or which
    model produced it."""
    fake = FakeSemanticIndex({"f": [SemanticMatch("prior", 0.9)]})
    decision = evaluate_recurrence(text="f", lexical_match=False, semantic_index=fake)
    for match in decision.semantic_matches:
        assert set(vars(match)) == {"finding_id", "similarity"}


def test_the_query_limit_is_bounded_so_a_provider_cannot_flood_a_record():
    many = [SemanticMatch(f"F-{i}", 0.99) for i in range(500)]
    fake = FakeSemanticIndex({"f": many})
    decision = evaluate_recurrence(text="f", lexical_match=False,
                                   semantic_index=fake, limit=10)
    assert len(decision.semantic_matches) == 10


def test_default_threshold_is_declared_in_one_place():
    assert RecurrenceDecision(decision=DECISION_NONE, lexical_match=False,
                              semantic_match=False).semantic_threshold == DEFAULT_SEMANTIC_THRESHOLD


# ---------------------------------------------------------------------------
# A threshold nothing can reach
# ---------------------------------------------------------------------------

class RangePublishingIndex:
    """A provider that reports the range its scores actually occupy."""
    provider_name = "measured-provider"

    def __init__(self, paraphrase=0.33):
        self._paraphrase = paraphrase

    def add(self, finding_id, text): ...
    def query(self, text, *, limit=10): return []
    def expected_similarity_range(self):
        return {"provider": self.provider_name, "paraphrase": self._paraphrase,
                "unrelated": 0.18}


def test_an_unreachable_threshold_is_reported_not_silently_obeyed():
    """The failure shape this guards is the dangerous one: a gate above the
    provider's ceiling imports cleanly, runs on every finding, and never
    fires. The audit trail fills with correct-looking lexical_only decisions
    and nothing says a whole signal is dead."""
    from ccc.semantic import check_threshold_is_reachable

    warning = check_threshold_is_reachable(RangePublishingIndex(), threshold=0.80)
    assert warning is not None
    assert "never fire" in warning
    assert "measured-provider" in warning


def test_a_reachable_threshold_produces_no_warning():
    from ccc.semantic import check_threshold_is_reachable
    assert check_threshold_is_reachable(RangePublishingIndex(), threshold=0.30) is None


def test_a_provider_that_publishes_no_range_is_not_assumed_broken():
    """Not interrogable is not the same as misconfigured. Returning None means
    the caller learns nothing, which is the honest answer."""
    from ccc.semantic import check_threshold_is_reachable
    assert check_threshold_is_reachable(FakeSemanticIndex(), threshold=0.99) is None
    assert check_threshold_is_reachable(None, threshold=0.99) is None


def test_the_default_threshold_is_reachable_by_a_realistic_provider():
    """Guards the specific mistake already made once: shipping 0.80 against a
    provider whose real paraphrase similarity is 0.33."""
    from ccc.semantic import check_threshold_is_reachable
    assert check_threshold_is_reachable(RangePublishingIndex()) is None, (
        "CCC's default threshold cannot be reached by a realistic embedding "
        "provider -- semantic recurrence would be a silent no-op"
    )
