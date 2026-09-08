"""Attacks on the semantic recurrence boundary that passed on 2026-09-08.

1. Event dates were serialized but never restored, so a reopen changed
   which discovery a recurrence cluster treats as its representative.
2. A non-numeric similarity escaped both except clauses and took recording
   down; a provider answering in ascending order made the recorded
   "nearest" the weakest match.
3. A provider that failed on every call left no trace anywhere.
4. The semantic index was not rebuilt on load.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ccc import Actor, CCCSystem
from ccc.semantic import SemanticMatch, evaluate_recurrence


@dataclass(frozen=True)
class _Finding:
    conclusion: str
    method: str
    source_material: Tuple[str, ...]
    confidence: Optional[float]
    verified: bool
    evidence: Tuple[Tuple[str, str], ...] = ()
    event_start_date: Optional[str] = None
    event_end_date: Optional[str] = None


def _finding(text, source="a.md", start=None, end=None):
    return _Finding(conclusion=text, method="test", source_material=(source,), confidence=0.8, verified=True,
                    evidence=((source, text),), event_start_date=start, event_end_date=end)


class _Index:
    provider_name = "fake"

    def __init__(self, answer=None):
        self.added = []
        self.answer = answer or []

    def add(self, finding_id, text):
        self.added.append((finding_id, text))

    def query(self, text, *, limit=10):
        return list(self.answer)


class _Broken:
    provider_name = "broken"

    def add(self, finding_id, text):
        raise RuntimeError("index down")

    def query(self, text, *, limit=10):
        raise RuntimeError("model host unreachable")


# ---------------------------------------------------------------- 1. event dates across a reopen

def test_event_dates_survive_a_reopen(tmp_path):
    system = CCCSystem()
    record = system.record_external_finding(_finding("alpha beta gamma delta", start="2026-01-05", end="2026-01-06"),
                                            actor=Actor.model("m"))
    assert record.event_start_date == "2026-01-05"
    path = system.save(tmp_path / "ccc.json")
    reopened = CCCSystem.load(path)
    stored = reopened.store.discoveries[record.discovery_id]
    assert (stored.event_start_date, stored.event_end_date) == ("2026-01-05", "2026-01-06")


# ---------------------------------------------------------------- 2. what the provider returns

def test_a_non_numeric_similarity_degrades_instead_of_raising():
    decision = evaluate_recurrence(text="x", lexical_match=False, semantic_index=_Index([SemanticMatch("f", "0.9")]))
    assert decision.semantic_match is False and "non-numeric" in decision.semantic_error
    system = CCCSystem(semantic_index=_Index([SemanticMatch("f", None)]))
    assert system.record_external_finding(_finding("still recorded"), actor=Actor.model("m")) is not None


def test_an_out_of_range_similarity_is_a_provider_failure():
    for bad in (1.5, -0.1, float("nan"), float("inf")):
        decision = evaluate_recurrence(text="x", lexical_match=False, semantic_index=_Index([SemanticMatch("f", bad)]))
        assert decision.semantic_match is False and decision.semantic_error, bad


def test_nearest_is_the_strongest_match_whatever_order_the_provider_used():
    decision = evaluate_recurrence(text="x", lexical_match=False,
                                   semantic_index=_Index([SemanticMatch("weak", 0.31), SemanticMatch("strong", 0.99)]))
    assert [m.finding_id for m in decision.semantic_matches] == ["strong", "weak"]
    system = CCCSystem(semantic_index=_Index([SemanticMatch("weak", 0.31), SemanticMatch("strong", 0.99)]))
    system.record_external_finding(_finding("an entirely novel observation sharing no words"), actor=Actor.model("m"))
    sign = list(system.store.road_signs.values())[0]
    assert sign.metadata["nearest_similarity"] == 0.99 and sign.linked_ids[0] == "strong"


# ---------------------------------------------------------------- 3. a dead signal leaves a trace

def test_a_provider_that_fails_leaves_an_audit_event_that_persists(tmp_path):
    system = CCCSystem(semantic_index=_Broken())
    record = system.record_external_finding(_finding("some finding"), actor=Actor.model("m"))
    events = [e for e in system.audit_trail.for_object(record.discovery_id) if e.operation == "semantic_provider_failed"]
    assert len(events) == 1
    assert events[0].new_state["semantic_provider"] == "broken" and "RuntimeError" in events[0].new_state["semantic_error"]
    path = system.save(tmp_path / "ccc.json")
    reopened = CCCSystem.load(path)
    assert any(e.operation == "semantic_provider_failed" for e in reopened.audit_trail.for_object(record.discovery_id))


def test_a_working_provider_leaves_no_failure_event():
    system = CCCSystem(semantic_index=_Index())
    record = system.record_external_finding(_finding("some finding"), actor=Actor.model("m"))
    assert not [e for e in system.audit_trail.for_object(record.discovery_id) if e.operation == "semantic_provider_failed"]


# ---------------------------------------------------------------- 4. the index is rebuilt on load

def test_the_semantic_index_is_rebuilt_from_the_store_on_load(tmp_path):
    system = CCCSystem(semantic_index=_Index())
    a = system.record_external_finding(_finding("first finding about widgets"), actor=Actor.model("m"))
    b = system.record_external_finding(_finding("second finding about gadgets"), actor=Actor.model("m"))
    path = system.save(tmp_path / "ccc.json")
    fresh = _Index()
    CCCSystem.load(path, semantic_index=fresh)
    assert {fid for fid, _ in fresh.added} == {a.discovery_id, b.discovery_id}
