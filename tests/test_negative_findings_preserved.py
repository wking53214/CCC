"""Article XVIII: a negative finding cannot be erased or redacted, only superseded."""
from __future__ import annotations

import pytest

from ccc import Actor, CCCSystem
from ccc.errors import ConstitutionViolation
from ccc.models import ArtifactState, RelationshipType

H = Actor.human("w")


def _record(system, text="a record"):
    return system.ingest(text, actor=H, authorization_basis="mine")


def _rejected(system):
    item = _record(system, "a rejected hypothesis")
    system.reject(item.artifact_id, actor=H, reason="did not hold", authorization_basis="review")
    return item


def _conflict(system, first, second):
    return system.detect_conflict(
        material_ids=(first.artifact_id, second.artifact_id),
        why_material="they disagree",
        choices=("keep first", "keep second"),
        downstream_consequences=("either choice changes the plan",),
        remaining_uncertainty=("unknown which is right",),
        actor=Actor.system(),
    )


@pytest.mark.parametrize("operation", ["erase", "redact"])
def test_a_rejected_record_cannot_be_erased_or_redacted(operation):
    system = CCCSystem()
    item = _rejected(system)
    with pytest.raises(ConstitutionViolation) as caught:
        getattr(system, operation)(item.artifact_id, actor=H, reason="tidy", authorization_basis="human request")
    assert caught.value.rule_id == "CCC-HISTORY-003"
    kept = system.store.require_artifact(item.artifact_id)
    assert kept.state is ArtifactState.ACTIVE and kept.content == "a rejected hypothesis"


@pytest.mark.parametrize("operation", ["erase", "redact"])
def test_a_record_material_to_a_conflict_cannot_be_erased_or_redacted(operation):
    system = CCCSystem()
    first, second = _record(system, "claim one"), _record(system, "claim two")
    _conflict(system, first, second)
    for item in (first, second):
        with pytest.raises(ConstitutionViolation) as caught:
            getattr(system, operation)(item.artifact_id, actor=H, reason="tidy", authorization_basis="human request")
        assert caught.value.rule_id == "CCC-HISTORY-003"
        assert system.store.require_artifact(item.artifact_id).content is not None


def test_a_record_on_either_end_of_a_contradiction_edge_cannot_be_erased():
    system = CCCSystem()
    first, second = _record(system, "yes"), _record(system, "no")
    system.lineage.link(first.artifact_id, second.artifact_id, RelationshipType.CONTRADICTS, actor=H, reason="they contradict")
    for item in (first, second):
        with pytest.raises(ConstitutionViolation) as caught:
            system.erase(item.artifact_id, actor=H, reason="tidy", authorization_basis="human request")
        assert caught.value.rule_id == "CCC-HISTORY-003"


def test_an_ordinary_record_can_still_be_erased_and_redacted():
    system = CCCSystem()
    erased, redacted = _record(system, "erase me"), _record(system, "redact me")
    system.erase(erased.artifact_id, actor=H, reason="private", authorization_basis="human request")
    system.redact(redacted.artifact_id, actor=H, reason="private", authorization_basis="human request")
    assert system.store.require_artifact(erased.artifact_id).state is ArtifactState.ERASED
    assert system.store.require_artifact(redacted.artifact_id).state is ArtifactState.REDACTED


def test_a_model_is_still_refused_by_the_human_rule_first():
    system = CCCSystem()
    item = _rejected(system)
    with pytest.raises(ConstitutionViolation) as caught:
        system.erase(item.artifact_id, actor=Actor.model("m"), reason="x", authorization_basis="y")
    assert caught.value.rule_id == "CCC-HUMAN-001"


def test_a_rejected_record_can_still_be_superseded():
    system = CCCSystem()
    item = _rejected(system)
    newer = system.supersede(item.artifact_id, content="what we believe now", actor=H, reason="new record", authorization_basis="human review")
    assert newer.artifact_id != item.artifact_id
    assert system.store.require_artifact(item.artifact_id).content == "a rejected hypothesis"


def test_the_rule_names_the_article_it_comes_from():
    from ccc.constitutional_rules import RULES

    rule = next(r for r in RULES if r.rule_id == "CCC-HISTORY-003")
    assert rule.article == "XVIII" and rule.source == "CONSTITUTION_v4.0"
