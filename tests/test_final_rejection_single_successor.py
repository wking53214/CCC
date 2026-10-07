"""Two rules carried over from innovation_os's invariants (2026-10-07).

1. A rejection is final. Nothing leaves REJECTED, not even UNRESOLVED (which
   would be a two-step way back to acceptance). A human who changes course
   supersedes the record with a new one, and the rejection stays on record.
2. A record has at most one successor. Superseding the same record twice
   would leave two replacements that each look current. Corrections and
   amendments of an old version stay allowed.
"""

from __future__ import annotations

import pytest

from ccc import Actor, CCCSystem
from ccc.errors import InvalidTransition
from ccc.models import ProvenanceStatus, RelationshipType

HUMAN = Actor.human("william")
BASIS = "explicit human decision"


def _rejected(system: CCCSystem):
    item = system.ingest("model suggestion", actor=Actor.model("m"))
    system.reject(item.artifact_id, actor=HUMAN, reason="not useful", authorization_basis=BASIS)
    return item.artifact_id


@pytest.mark.parametrize("operation", ["accept", "establish_provenance"])
def test_a_rejected_record_cannot_be_approved(operation):
    system = CCCSystem()
    artifact_id = _rejected(system)
    with pytest.raises(InvalidTransition, match="rejection is final"):
        getattr(system, operation)(artifact_id, actor=HUMAN, reason="changed my mind", authorization_basis=BASIS)
    assert system.store.require_artifact(artifact_id).provenance_status is ProvenanceStatus.REJECTED


def test_a_rejected_record_cannot_be_reopened_as_unresolved():
    system = CCCSystem()
    artifact_id = _rejected(system)
    with pytest.raises(InvalidTransition, match="rejection is final"):
        system.provenance.transition(
            artifact_id, ProvenanceStatus.UNRESOLVED, actor=HUMAN, reason="reopen", authorization_basis=BASIS)


def test_changing_course_after_a_rejection_is_a_supersession():
    system = CCCSystem()
    artifact_id = _rejected(system)
    successor = system.supersede(artifact_id, content="revised suggestion, now adopted", actor=HUMAN,
                                 reason="changed course", authorization_basis=BASIS)
    assert system.store.require_artifact(artifact_id).provenance_status is ProvenanceStatus.REJECTED
    assert successor.provenance_status is ProvenanceStatus.USER_ESTABLISHED


def _decision(system: CCCSystem):
    return system.decide("use A", actor=HUMAN, reason="initial", authorization_basis=BASIS)


def test_a_record_can_be_superseded_once():
    system = CCCSystem()
    first = _decision(system)
    second = system.supersede(first.artifact_id, content="use B", actor=HUMAN, reason="r", authorization_basis=BASIS)
    links = system.lineage.related(first.artifact_id, RelationshipType.SUPERSEDES)
    assert [(e.source_id, e.target_id) for e in links] == [(second.artifact_id, first.artifact_id)]


def test_superseding_the_same_record_twice_is_refused_and_names_the_successor():
    system = CCCSystem()
    first = _decision(system)
    second = system.supersede(first.artifact_id, content="use B", actor=HUMAN, reason="r", authorization_basis=BASIS)
    count = len(system.store.artifacts)
    with pytest.raises(InvalidTransition, match=second.artifact_id):
        system.supersede(first.artifact_id, content="use C", actor=HUMAN, reason="r", authorization_basis=BASIS)
    assert len(system.store.artifacts) == count


def test_the_newest_version_can_be_superseded_so_history_stays_one_line():
    system = CCCSystem()
    first = _decision(system)
    second = system.supersede(first.artifact_id, content="use B", actor=HUMAN, reason="r", authorization_basis=BASIS)
    third = system.supersede(second.artifact_id, content="use C", actor=HUMAN, reason="r", authorization_basis=BASIS)
    assert third.metadata["version_of"] == second.artifact_id


def test_an_old_version_can_still_be_corrected_after_it_is_superseded():
    system = CCCSystem()
    first = _decision(system)
    system.supersede(first.artifact_id, content="use B", actor=HUMAN, reason="r", authorization_basis=BASIS)
    correction = system.correct(first.artifact_id, content="use A (typo fixed)", actor=HUMAN,
                                reason="fix the historical record", authorization_basis=BASIS)
    assert correction.metadata["operation"] == "CORRECT"
