"""A roster can insist that the CCC it approves a write for has a write permission, and which one.

A CCC built without a `write_permission` is not stopped, and from outside nothing could tell. `has_write_permission`
and `write_permission` say what the system holds, read-only, and `CccGate(require_permission=True)` refuses (a
TERMINAL_BREACH) a system with none. `accept_permission` hands the permission to a predicate the roster supplies, so a
function that answers True to everything satisfies the first but not an isinstance check on the roster's own guard.
Skipped when CNS is absent, like the rest of the connected half.
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("CCC_REQUIRE_CNS") == "1":
    import cns.gate  # noqa: F401
else:
    pytest.importorskip("cns.gate", reason="cns not installed; run in an environment with the [cns] extra")

from ccc.cns_connector import CccGate, attempt, attempt_digest
from ccc.models import Actor, EpistemicStatus
from ccc.system import CCCSystem

TEXT = "Invoice INV-2207 came to $412.00."


def ingest():
    return attempt("ingest", TEXT, actor=Actor.model("herald"), epistemic_status=EpistemicStatus.INFERENCE)


class OurPermission:
    def __call__(self, request):
        return False


def ours(permission):
    return isinstance(permission, OurPermission)


def test_a_system_says_whether_it_holds_a_write_permission_and_which():
    permission = OurPermission()
    assert CCCSystem(write_permission=permission).has_write_permission is True
    assert CCCSystem(write_permission=permission).write_permission is permission
    assert CCCSystem().has_write_permission is False and CCCSystem().write_permission is None


def test_the_permission_cannot_be_replaced_through_the_public_interface():
    system = CCCSystem(write_permission=OurPermission())
    with pytest.raises(AttributeError):
        system.write_permission = None
    with pytest.raises(AttributeError):
        system.has_write_permission = False


def test_a_gate_without_the_requirement_judges_a_system_with_none_as_before():
    assert CccGate(CCCSystem()).check(ingest()).outcome.value == "pass"


def test_a_gate_that_requires_a_permission_refuses_a_system_with_none_and_binds_the_refusal_to_the_attempt():
    att = ingest()
    result = CccGate(CCCSystem(), require_permission=True).check(att)
    assert result.outcome.value == "terminal_breach"
    assert "no write permission" in result.reason
    assert result.binds(att.subject, attempt_digest(att))


def test_a_gate_that_requires_a_permission_passes_a_system_that_has_one():
    assert CccGate(CCCSystem(write_permission=lambda r: False), require_permission=True).check(ingest()).outcome.value == "pass"


def test_a_lambda_that_says_yes_to_everything_is_refused_by_an_acceptance_predicate():
    system = CCCSystem(write_permission=lambda request: True)
    assert CccGate(system, require_permission=True).check(ingest()).outcome.value == "pass"
    result = CccGate(system, accept_permission=ours).check(ingest())
    assert result.outcome.value == "terminal_breach" and "not one the roster accepts" in result.reason
    assert CccGate(CCCSystem(write_permission=OurPermission()), accept_permission=ours).check(ingest()).outcome.value == "pass"


def test_asking_to_accept_a_permission_also_refuses_a_system_with_none():
    result = CccGate(CCCSystem(), accept_permission=ours).check(ingest())
    assert result.outcome.value == "terminal_breach" and "no write permission" in result.reason


def test_a_predicate_that_raises_or_answers_loosely_never_accepts():
    def boom(permission):
        raise RuntimeError("cannot say")
    system = CCCSystem(write_permission=OurPermission())
    for predicate in (boom, lambda p: 1, lambda p: "yes", lambda p: None):
        assert CccGate(system, accept_permission=predicate).check(ingest()).outcome.value == "terminal_breach"


def test_a_predicate_that_is_not_callable_is_refused_at_construction():
    with pytest.raises(ValueError, match="accept_permission"):
        CccGate(CCCSystem(), accept_permission="OurPermission")


def test_the_requirement_does_not_run_the_attempt_or_touch_the_store():
    system = CCCSystem()
    CccGate(system, require_permission=True).check(ingest())
    assert len(system.store.artifacts) == 0 and len(system.audit_trail.all()) == 0
