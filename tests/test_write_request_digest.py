"""``write_request_digest``: the digest of the call a WriteRequest describes.

A permission issued for a verdict bound to an Attempt uses it to check that the write it is asked about is that
exact call. Skipped when CNS is absent, like the rest of the connected half (``test_cns_connector.py``).
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("CCC_REQUIRE_CNS") == "1":
    import cns.gate  # noqa: F401
else:
    pytest.importorskip("cns.gate", reason="cns not installed; run in an environment with the [cns] extra")

from ccc.cns_connector import attempt, attempt_digest, write_request_digest
from ccc.models import Actor, EpistemicStatus
from ccc.permission import build_request

TEXT = "Invoice INV-2207 came to $412.00."


def request(operation="ingest", *args, **kwargs):
    return build_request(operation, args or (TEXT,), kwargs or {"actor": Actor.model("herald"),
                                                                 "epistemic_status": EpistemicStatus.INFERENCE,
                                                                 "metadata": {"source_id": "doc-1"}})


def test_equals_the_attempt_digest_for_the_same_call():
    call = {"actor": Actor.model("herald"), "epistemic_status": EpistemicStatus.INFERENCE,
            "metadata": {"source_id": "doc-1"}, "reason": "read"}
    assert write_request_digest(build_request("ingest", (TEXT,), call)) == attempt_digest(attempt("ingest", TEXT, **call))


def test_defaults_applied_so_spelling_a_default_out_changes_nothing():
    bare = build_request("ingest", (TEXT,), {"actor": Actor.model("herald")})
    spelled = build_request("ingest", (TEXT,), {"actor": Actor.model("herald"), "presentation_priority": 0})
    assert write_request_digest(bare) == write_request_digest(spelled)


@pytest.mark.parametrize("change", [
    {"actor": Actor.human("mallory")},
    {"epistemic_status": EpistemicStatus.HISTORICAL_RECORD},
    {"metadata": {"source_id": "doc-1", "approved_amount": "4120.00"}},
    {"presentation_priority": 100},
    {"topics": ("payments-approved",)},
    {"confidence": 0.99},
    {"authorization_basis": "I say so"},
])
def test_any_changed_argument_changes_the_digest(change):
    base = {"actor": Actor.model("herald"), "epistemic_status": EpistemicStatus.INFERENCE,
            "metadata": {"source_id": "doc-1"}}
    assert write_request_digest(build_request("ingest", (TEXT,), {**base, **change})) != \
        write_request_digest(build_request("ingest", (TEXT,), base))


def test_changed_text_changes_the_digest():
    assert write_request_digest(request("ingest", TEXT)) != write_request_digest(request("ingest", TEXT + " "))


def test_another_operation_over_the_same_arguments_digests_differently():
    kwargs = {"actor": Actor.model("herald"), "metadata": {"source_id": "doc-1"}}
    assert write_request_digest(build_request("record", (TEXT,), kwargs)) != \
        write_request_digest(build_request("ingest", (TEXT,), kwargs))


def test_an_operation_ccc_has_no_method_for_is_a_value_error():
    with pytest.raises(ValueError):
        write_request_digest(build_request("no_such_door", (TEXT,), {}))


def test_arguments_that_are_not_canonical_content_are_a_type_error():
    with pytest.raises(TypeError):
        write_request_digest(build_request("ingest", (TEXT,), {"metadata": {"x": object()}}))
