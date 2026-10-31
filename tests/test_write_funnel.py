"""One funnel for every machine-side write.

With a write permission that says no to everything, no door CCCSystem has may add an artifact, an evidence link or a
lineage edge. ``tests/test_write_permission.py`` and ``tests/test_write_permission_doors.py`` cover the public
doors that already asked. This file covers the ones that did not: the private ``_ingest`` and ``_derive``, the
discovery and road sign managers a caller can reach as ``system.discovery`` and ``system.road_signs``,
``attach_evidence`` and ``relate``. It ends with a sweep that fails when a public method is added without a decision
about which kind it is. None of these tests needs CNS and none skips.
"""

from __future__ import annotations

import inspect

import pytest
from test_human_verifier import OPERATIONS as HUMAN_OPERATIONS
from test_human_verifier import _world as human_world

from ccc import Actor, CCCSystem, EpistemicStatus, RelationshipType, RoadSignCategory
from ccc.errors import HumanVerificationRefused, WritePermissionRefused

HUMAN = Actor.human("william")
MODEL = Actor.model("model")
BASIS = "explicit human decision"


class Check:
    """A permission check that records what it was asked and answers as told."""

    def __init__(self, verdict=True):
        self.verdict = verdict
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.verdict


def _counts(system: CCCSystem) -> dict[str, int]:
    store = system.store
    return {
        "artifacts": len(store.artifacts),
        "evidence_links": len(store.evidence_links),
        "lineage_events": len(store.lineage_events),
        "discoveries": len(store.discoveries),
        "road_signs": len(store.road_signs),
        "audit_events": len(store.audit_events),
    }


def _world():
    """A store with a claim and a fact to relate, built with no guard on it."""
    plain = CCCSystem()
    fact = plain.ingest("a human fact", actor=HUMAN, epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
                        authorization_basis=BASIS)
    claim = plain.ingest("a machine claim", actor=MODEL)
    return plain.store, fact, claim


#: Each door that did not ask, with a call that works on _world(), and the operation it must ask under. The road sign
#: doors ask under their own method names, the same names the public doors use, so a check sees one name for one act.
DOORS = {
    "_ingest": ("ingest", lambda s, fact, claim: s._ingest("a machine write", actor=MODEL)),
    "_derive": ("derive", lambda s, fact, claim: s._derive("a machine conclusion", actor=MODEL)),
    "discovery.discover": ("discover", lambda s, fact, claim: s.discovery.discover(
        source_material=(), method="scan", conclusion="a candidate", confidence=0.3, actor=MODEL)),
    "road_signs.detect_road_sign": ("detect_road_sign", lambda s, fact, claim: s.road_signs.detect_road_sign(
        observation="a reversal", category=RoadSignCategory.REVERSAL, actor=MODEL)),
    "road_signs.record_road_sign": ("record_road_sign", lambda s, fact, claim: s.road_signs.record_road_sign(
        observation="a reversal", category=RoadSignCategory.REVERSAL, actor=MODEL)),
    "attach_evidence": ("attach_evidence", lambda s, fact, claim: s.attach_evidence(
        claim.artifact_id, fact.artifact_id, actor=MODEL, rationale="the fact supports the claim")),
    "relate": ("relate", lambda s, fact, claim: s.relate(
        claim.artifact_id, fact.artifact_id, RelationshipType.RELATED_TO, actor=MODEL, reason="they are related")),
}


@pytest.mark.parametrize("door", DOORS)
def test_a_deny_all_permission_stops_every_door_and_nothing_is_added(door, tmp_path):
    store, fact, claim = _world()
    system = CCCSystem(store=store, write_permission=Check(False))
    before_counts = _counts(system)
    before = system.store.save(tmp_path / "before.json").read_bytes()
    with pytest.raises(WritePermissionRefused) as refused:
        DOORS[door][1](system, fact, claim)
    assert refused.value.operation == DOORS[door][0]
    assert _counts(system) == before_counts
    assert system.store.save(tmp_path / "after.json").read_bytes() == before  # byte for byte


@pytest.mark.parametrize("door", DOORS)
def test_a_yes_lets_the_door_through_and_the_check_is_asked_exactly_once(door):
    store, fact, claim = _world()
    check = Check(True)
    system = CCCSystem(store=store, write_permission=check)
    before = _counts(system)
    DOORS[door][1](system, fact, claim)
    assert [r.operation for r in check.requests] == [DOORS[door][0]]
    assert _counts(system) != before


@pytest.mark.parametrize("door", DOORS)
def test_without_a_permission_every_door_works_as_before(door):
    store, fact, claim = _world()
    system = CCCSystem(store=store)
    before = _counts(system)
    DOORS[door][1](system, fact, claim)
    assert _counts(system) != before


def test_the_request_for_a_door_carries_the_callers_arguments_as_given():
    store, fact, claim = _world()
    check = Check(True)
    system = CCCSystem(store=store, write_permission=check)
    system.attach_evidence(claim.artifact_id, fact.artifact_id, actor=MODEL, rationale="because")
    system.relate(claim.artifact_id, fact.artifact_id, RelationshipType.RELATED_TO, actor=MODEL, reason="they relate")
    attach, relate = check.requests
    assert (attach.operation, attach.args) == ("attach_evidence", (claim.artifact_id, fact.artifact_id))
    assert set(attach.kwargs) == {"actor", "rationale"}  # no defaults filled in
    assert (relate.operation, relate.args) == ("relate", (claim.artifact_id, fact.artifact_id,
                                                          RelationshipType.RELATED_TO))
    assert set(relate.kwargs) == {"actor", "reason"}


def test_what_a_door_calls_beneath_itself_does_not_ask_again():
    """derive attaches evidence and ingests; interpret derives; record_external_finding raises road signs and
    discoveries. Each is one call, so each is one ask."""
    store, fact, claim = _world()
    check = Check(True)
    system = CCCSystem(store=store, write_permission=check)
    system.derive("a conclusion", actor=MODEL, evidence_ids=(fact.artifact_id,))
    system.interpret("an interpretation", actor=MODEL, evidence_ids=(fact.artifact_id,))
    assert [r.operation for r in check.requests] == ["derive", "interpret"]
    assert len(system.store.evidence_links) == 2


def test_a_human_operation_still_never_asks_the_write_permission_though_it_writes_artifacts_and_edges():
    """decide, correct and the rest write artifacts and edges through the same store. They carry a human's action, so
    the machine's permission is not asked; the human verifier is."""
    deny = Check(False)
    w = human_world()
    system = CCCSystem(store=w.store, write_permission=deny)
    for call in HUMAN_OPERATIONS.values():
        call(system, w)
    assert deny.requests == []


# What every public method of CCCSystem is, so that adding one forces a decision.
GUARDED_MACHINE = {
    "ingest", "record", "derive", "infer", "interpret", "discover", "record_external_finding", "detect_road_sign",
    "record_road_sign", "attach_evidence", "relate",
}
GUARDED_HUMAN = set(HUMAN_OPERATIONS) | {"resolve"}
#: Add a record that is not an artifact, an evidence link or a lineage edge, or change one that exists. Left open
#: on purpose: a question, a conflict, a sign's links, and a stage a machine may move (not MANDATE).
OPEN_BY_DESIGN = {"ask", "detect_conflict", "request_human_resolution", "link_road_sign"}
READ_ONLY = {
    "audit", "classify_conflict", "evidence_root", "present", "present_conflict", "query", "query_road_signs",
    "recurring_groups", "system_actor", "trace_evidence_chain", "validate_constitution", "validate_evidence_chain",
    "save", "load", "version",
}


def test_every_public_method_is_a_guarded_door_a_read_or_open_on_purpose():
    public = {name for name, _ in inspect.getmembers(CCCSystem) if not name.startswith("_")}
    decided = GUARDED_MACHINE | GUARDED_HUMAN | OPEN_BY_DESIGN | READ_ONLY
    assert public - decided == set(), f"public methods with no decision about their door: {sorted(public - decided)}"
    assert decided - public == set(), f"decisions about methods that do not exist: {sorted(decided - public)}"


def test_with_a_deny_all_permission_and_a_refusing_verifier_no_door_adds_an_artifact_a_link_or_an_edge(tmp_path):
    w = human_world()
    stores = {}
    attempts = {}
    for name, call in HUMAN_OPERATIONS.items():
        attempts[name] = (HumanVerificationRefused, lambda s, w=w, call=call: call(s, w))
    store, fact, claim = _world()
    for name, (_op, call) in DOORS.items():
        attempts[name] = (WritePermissionRefused, lambda s, call=call, fact=fact, claim=claim: call(s, fact, claim))
    for name, call in {
        "ingest": lambda s: s.ingest("text", actor=MODEL),
        "record": lambda s: s.record("text", actor=MODEL),
        "derive": lambda s: s.derive("text", actor=MODEL),
        "infer": lambda s: s.infer("text", actor=MODEL),
        "interpret": lambda s: s.interpret("text", actor=MODEL),
        "discover": lambda s: s.discover(source_material=(), method="m", conclusion="c", confidence=0.3, actor=MODEL),
        "detect_road_sign": lambda s: s.detect_road_sign(observation="o", category=RoadSignCategory.REVERSAL,
                                                         actor=MODEL),
        "record_road_sign": lambda s: s.record_road_sign(observation="o", category=RoadSignCategory.REVERSAL,
                                                         actor=MODEL),
    }.items():
        attempts[f"public {name}"] = (WritePermissionRefused, call)
    for name, (error, call) in attempts.items():
        owner = w if name in HUMAN_OPERATIONS else None
        system = CCCSystem(store=(owner.store if owner else store), write_permission=Check(False),
                           human_verifier=lambda request: False)
        before = _counts(system)
        with pytest.raises(error):
            call(system)
        after = _counts(system)
        for kind in ("artifacts", "evidence_links", "lineage_events"):
            assert after[kind] == before[kind], f"{name} added to {kind}"
        stores[name] = after
    assert len(stores) == len(HUMAN_OPERATIONS) + len(DOORS) + 8
