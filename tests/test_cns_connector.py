"""The connected half: what CCC's attempted transitions become when CNS is
installed.

Skipped when CNS is absent. The independence half, which must hold in both
environments, is in ``test_cns_independence.py`` and never skips.

The scenario table below is the contract. Each row names one attempted
transition, the verdict CCC's own code implies for it, and the front of the
reason CCC raises. The agreement tests then check the connector against what
CCC actually does, not against the table.

The words mean this. ``pass``: CCC admits the call. ``gated`` (RETRY): CCC
refuses it, and a human supplying what the refusal asks for gets this same
call admitted; REPAIRS says what, and a test applies it to the live world.
``blocked`` (TERMINAL_BREACH): nothing a human supplies admits it, or CCC
refused the input itself.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import pickle
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

cns_gate = pytest.importorskip(
    "cns.gate", reason="cns not installed; run in an environment with the [cns] extra"
)

from ccc import (  # noqa: E402
    Actor,
    AnalysisStage,
    CCCSystem,
    EpistemicStatus,
    ProvenanceStatus,
)
from ccc import constitutional_rules  # noqa: E402
from ccc.cns_connector import (  # noqa: E402
    GATE_NAME,
    MAX_DEPTH,
    MAX_INT_BITS,
    PASS_REASON,
    TRANSITIONS,
    AttemptChanged,
    CccGate,
    CnsNotInstalled,
    PreflightError,
    attempt,
    attempt_digest,
    cns_available,
    cns_chain,
    judge,
    to_cns_result,
)
from ccc.errors import (  # noqa: E402
    CCCError,
    ConstitutionViolation,
    InvalidTransition,
    NotFound,
)
from ccc.store import CCCStore  # noqa: E402

PASS = cns_gate.GateOutcome.PASS
RETRY = cns_gate.GateOutcome.RETRY
BREACH = cns_gate.GateOutcome.TERMINAL_BREACH
OUTCOME = {"pass": PASS, "gated": RETRY, "blocked": BREACH}

HIST = EpistemicStatus.HISTORICAL_RECORD

#: Written out, not imported, so changing the connector's wording is seen here.
ADMITTED = "admitted: no constitutional rule refused this transition"

GOOD = "explicit human authorization"


def _world() -> SimpleNamespace:
    """One system holding every kind of material the scenarios need."""
    system = CCCSystem()
    human, model = Actor.human("human"), Actor.model("model")
    w = SimpleNamespace(system=system, human=human, model=model)

    def fact(text: str):
        return system.ingest(
            text, actor=human, epistemic_status=HIST, authorization_basis="human record"
        )

    w.fact, w.fact2 = fact("human fact"), fact("second human fact")
    w.proposal = system.derive(
        "machine inference", actor=model, evidence_ids=(w.fact.artifact_id,)
    )
    w.unsupported = system.derive("machine inference with no evidence", actor=model)
    w.consensus = system.derive(
        "machine consensus", actor=model, machine_consensus=True
    )
    w.simulation = system.ingest(
        "modeled trajectory", actor=model, epistemic_status=EpistemicStatus.SIMULATION
    )
    accepted = system.derive(
        "machine inference, already adopted",
        actor=model,
        evidence_ids=(w.fact.artifact_id,),
    )
    w.accepted = system.accept(
        accepted.artifact_id,
        actor=human,
        reason="reviewed",
        authorization_basis="explicit human adoption",
        evidence_ids=(w.fact.artifact_id,),
    )
    erased = fact("a fact that was erased")
    system.erase(
        erased.artifact_id,
        actor=human,
        reason="requested",
        authorization_basis="explicit human erasure request",
    )
    w.erased = system.store.require_artifact(erased.artifact_id)
    w.anomaly = system.discover(
        source_material=(w.fact.artifact_id,),
        method="machine discovery",
        conclusion="an anomaly",
        confidence=0.5,
        actor=model,
        stage=AnalysisStage.ANOMALY,
    )
    w.pattern = system.discover(
        source_material=(w.fact.artifact_id,),
        method="machine discovery",
        conclusion="a pattern",
        confidence=0.5,
        actor=model,
        stage=AnalysisStage.PATTERN,
    )
    w.term = system.propose_term(term="continuity", definition="d", actor=model)
    w.conflict = system.detect_conflict(
        material_ids=(w.fact.artifact_id, w.fact2.artifact_id),
        why_material="two human facts disagree",
        choices=("a", "b"),
        downstream_consequences=("a downstream effect",),
        remaining_uncertainty=("which one holds",),
        actor=model,
    )
    w.uncertainty = system.ask(context="a context", question="which one?", actor=model)
    w.inflection = system.detect_inflection(
        artifact_id=w.fact.artifact_id,
        directions=("up", "down"),
        divergence=0.5,
        sensitivity=0.5,
        actor=model,
    )
    return w


def _id(artifact) -> str:
    return artifact.artifact_id


def _with(att, **changes):
    """``att`` again, with some keyword arguments changed or added."""
    return attempt(att.operation, *att.args, **{**att.kwargs, **changes})


def _human_op(op: str, extra=None, basis: str = GOOD):
    """``op`` on the human fact, by a human, with an explicit basis."""

    def make(w):
        return attempt(
            op,
            _id(w.fact),
            actor=w.human,
            reason="explicit human operation",
            authorization_basis=basis,
            **(extra or {}),
        )

    return make


def _model_op(op: str, extra=None):
    """The same operation attempted by a model."""

    def make(w):
        return attempt(
            op,
            _id(w.fact),
            actor=w.model,
            reason="model recommendation",
            authorization_basis="model vote",
            **(extra or {}),
        )

    return make


_REWRITE = ("correct", "amend", "supersede")
_HISTORY = (*_REWRITE, "redact", "erase")


def _extra(op):
    return {"content": "rewritten"} if op in _REWRITE else None


# (name, builder(world) -> Attempt, "pass" | "gated" | "blocked", front of reason)
SCENARIOS = [
    # Admission of new material.
    (
        "ingest: a model cannot enter material as evidence",
        lambda w: attempt(
            "ingest", "machine claim", actor=w.model,
            epistemic_status=EpistemicStatus.EVIDENCE,
        ),
        "blocked", "CCC-RATIFICATION-001",
    ),
    (
        "ingest: a model cannot claim human provenance",
        lambda w: attempt(
            "ingest", "machine claim", actor=w.model,
            provenance_status=ProvenanceStatus.USER_ESTABLISHED,
        ),
        "blocked", "CCC-PROVENANCE-002",
    ),
    (
        "ingest: a human may establish a record",
        lambda w: attempt(
            "ingest", "a human claim", actor=w.human, epistemic_status=HIST,
            authorization_basis="human record",
        ),
        "pass", ADMITTED,
    ),
    (
        "ingest: external material needs human classification first",
        lambda w: attempt(
            "ingest", "external claim", actor=Actor.external("outside"),
            epistemic_status=HIST,
        ),
        "blocked", "CCC-EPISTEMIC-001",
    ),
    (
        "ingest: a source that does not exist",
        lambda w: attempt(
            "ingest", "a claim", actor=w.human, source_material=("artifact_missing",),
        ),
        "blocked", "NotFound",
    ),
    # Chain B, evidence.
    (
        "attach: a second root under a proposal",
        lambda w: attempt(
            "attach_evidence", _id(w.proposal), _id(w.fact2), actor=w.model,
            rationale="more support",
        ),
        "pass", ADMITTED,
    ),
    (
        "attach: a claim cannot support itself",
        lambda w: attempt(
            "attach_evidence", _id(w.proposal), _id(w.proposal), actor=w.model,
            rationale="circular",
        ),
        "blocked", "CCC-EVIDENCE-002",
    ),
    (
        "attach: erased material is not available as evidence",
        lambda w: attempt(
            "attach_evidence", _id(w.proposal), _id(w.erased), actor=w.model,
            rationale="gone",
        ),
        "blocked", "CCC-EVIDENCE-001",
    ),
    (
        "attach: a support strength outside 0 to 1 is malformed input",
        lambda w: attempt(
            "attach_evidence", _id(w.proposal), _id(w.fact2), actor=w.human,
            rationale="too strong", support_strength=1.5,
        ),
        "blocked", "ValueError: support_strength must be between 0 and 1",
    ),
    # Proposal to authority.
    (
        "establish: by a model",
        lambda w: attempt(
            "establish_provenance", _id(w.proposal), actor=w.model, reason="consensus",
            authorization_basis="model vote",
        ),
        "blocked", "CCC-PROVENANCE-002",
    ),
    (
        "establish: by a human",
        lambda w: attempt(
            "establish_provenance", _id(w.proposal), actor=w.human,
            reason="reviewed", authorization_basis="explicit human establishment",
        ),
        "pass", ADMITTED,
    ),
    (
        "establish: by a human who gives no basis",
        lambda w: attempt(
            "establish_provenance", _id(w.proposal), actor=w.human,
            reason="reviewed", authorization_basis="",
        ),
        "gated", "CCC-PROVENANCE-002",
    ),
    (
        "establish: machine consensus is not established fact, even for a human",
        lambda w: attempt(
            "establish_provenance", _id(w.consensus), actor=w.human,
            reason="reviewed", authorization_basis="explicit human establishment",
        ),
        "blocked", "CCC-RATIFICATION-001",
    ),
    (
        "establish: erased material cannot be promoted",
        lambda w: attempt(
            "establish_provenance", _id(w.erased), actor=w.human,
            reason="revive", authorization_basis="explicit human establishment",
        ),
        "blocked", "CCC-HISTORY-002",
    ),
    (
        "accept: by a model",
        lambda w: attempt(
            "accept", _id(w.proposal), actor=w.model, reason="consensus",
            authorization_basis="machine consensus",
        ),
        "blocked", "CCC-PROVENANCE-002",
    ),
    (
        "accept: by a human, with the evidence root",
        lambda w: attempt(
            "accept", _id(w.proposal), actor=w.human, reason="reviewed",
            authorization_basis="explicit human adoption",
            evidence_ids=(_id(w.fact),),
        ),
        "pass", ADMITTED,
    ),
    (
        "accept: machine consensus can be adopted by a human",
        lambda w: attempt(
            "accept", _id(w.consensus), actor=w.human, reason="reviewed",
            authorization_basis="explicit human adoption",
        ),
        "pass", ADMITTED,
    ),
    (
        "accept: by a human who gives no basis",
        lambda w: attempt(
            "accept", _id(w.proposal), actor=w.human, reason="reviewed",
            authorization_basis="",
        ),
        "gated", "CCC-PROVENANCE-002",
    ),
    (
        "accept: already accepted is not a transition",
        lambda w: attempt(
            "accept", _id(w.accepted), actor=w.human, reason="again",
            authorization_basis="explicit human adoption",
        ),
        "blocked", "InvalidTransition",
    ),
    (
        "reject: by a model",
        lambda w: attempt(
            "reject", _id(w.proposal), actor=w.model, reason="veto",
            authorization_basis="model vote",
        ),
        "blocked", "CCC-HUMAN-001",
    ),
    (
        "reject: by a human",
        lambda w: attempt(
            "reject", _id(w.proposal), actor=w.human, reason="not supported",
            authorization_basis="explicit human rejection",
        ),
        "pass", ADMITTED,
    ),
    (
        "ratify: by a model",
        lambda w: attempt(
            "ratify", _id(w.proposal), actor=w.model, reason="consensus",
            authorization_basis="machine consensus",
        ),
        "blocked", "CCC-PROVENANCE-002",
    ),
    (
        "ratify: by a human",
        lambda w: attempt(
            "ratify", _id(w.proposal), actor=w.human, reason="reviewed",
            authorization_basis="explicit human adoption",
            status=ProvenanceStatus.USER_ESTABLISHED,
        ),
        "pass", ADMITTED,
    ),
    (
        "ratify: by a human who gives no basis",
        lambda w: attempt(
            "ratify", _id(w.proposal), actor=w.human, reason="reviewed",
            authorization_basis="", status=ProvenanceStatus.USER_ESTABLISHED,
        ),
        "gated", "CCC-PROVENANCE-002",
    ),
    # Epistemic promotion.
    (
        "classify: a simulation can never become history",
        lambda w: attempt(
            "classify", _id(w.simulation), HIST, actor=w.human, reason="relabel",
        ),
        "blocked", "CCC-EPISTEMIC-002",
    ),
    (
        "classify: a model cannot promote an inference to evidence",
        lambda w: attempt(
            "classify", _id(w.proposal), EpistemicStatus.EVIDENCE, actor=w.model,
            reason="promote",
        ),
        "blocked", "CCC-EPISTEMIC-001",
    ),
    (
        "classify: a human promotes an inference that has an evidence root",
        lambda w: attempt(
            "classify", _id(w.proposal), EpistemicStatus.EVIDENCE, actor=w.human,
            reason="rooted in a human fact",
        ),
        "pass", ADMITTED,
    ),
    (
        "classify: a human cannot promote an inference with no evidence root",
        lambda w: attempt(
            "classify", _id(w.unsupported), EpistemicStatus.EVIDENCE, actor=w.human,
            reason="no root",
        ),
        "gated", "CCC-EPISTEMIC-003",
    ),
    (
        "classify: machine consensus is not promoted, even by a human",
        lambda w: attempt(
            "classify", _id(w.consensus), EpistemicStatus.EVIDENCE, actor=w.human,
            reason="many models agree",
        ),
        "blocked", "CCC-RATIFICATION-001",
    ),
    (
        "classify: erased material cannot be reclassified",
        lambda w: attempt(
            "classify", _id(w.erased), EpistemicStatus.EVIDENCE, actor=w.human,
            reason="revive",
        ),
        "blocked", "CCC-HISTORY-002",
    ),
    # Human decisions and history.
    (
        "decide: by a model",
        lambda w: attempt(
            "decide", "adopt the plan", actor=w.model, reason="recommendation",
            authorization_basis="model vote",
        ),
        "blocked", "CCC-HUMAN-001",
    ),
    (
        "decide: by a human",
        lambda w: attempt(
            "decide", "adopt the plan", actor=w.human, reason="decision",
            authorization_basis="explicit human decision",
        ),
        "pass", ADMITTED,
    ),
    (
        "decide: by a human who gives no basis",
        lambda w: attempt(
            "decide", "adopt the plan", actor=w.human, reason="decision",
            authorization_basis="",
        ),
        "gated", "CCC-HUMAN-001",
    ),
    (
        "decide: no basis and a recommendation that does not exist",
        lambda w: attempt(
            "decide", "adopt the plan", actor=w.human, reason="decision",
            authorization_basis="", recommendation_id="artifact_missing",
        ),
        "blocked", "CCC-HUMAN-001",
    ),
    *[
        (f"{op}: by a model", _model_op(op, _extra(op)), "blocked", "CCC-HUMAN-001")
        for op in _HISTORY
    ],
    *[
        (f"{op}: by a human", _human_op(op, _extra(op)), "pass", ADMITTED)
        for op in _HISTORY
    ],
    *[
        (
            f"{op}: by a human who gives no basis",
            _human_op(op, _extra(op), basis=""),
            "gated", "CCC-HUMAN-001",
        )
        for op in _HISTORY
    ],
    # Discoveries and the 1 -> 2 -> 3 method.
    (
        "discover: a model cannot create a discovery as evidence",
        lambda w: attempt(
            "discover", source_material=(_id(w.fact),), method="machine discovery",
            conclusion="a claim", confidence=0.5, actor=w.model,
            epistemic_status=EpistemicStatus.EVIDENCE,
        ),
        "blocked", "CCC-DISCOVERY-001",
    ),
    (
        "discover: a model may record an inference",
        lambda w: attempt(
            "discover", source_material=(_id(w.fact),), method="machine discovery",
            conclusion="a claim", confidence=0.5, actor=w.model,
        ),
        "pass", ADMITTED,
    ),
    (
        "adopt_discovery: by a model",
        lambda w: attempt(
            "adopt_discovery", w.anomaly.discovery_id, actor=w.model, reason="consensus",
            authorization_basis="machine consensus",
        ),
        "blocked", "CCC-RATIFICATION-001",
    ),
    (
        "adopt_discovery: by a human",
        lambda w: attempt(
            "adopt_discovery", w.anomaly.discovery_id, actor=w.human, reason="reviewed",
            authorization_basis="explicit human adoption",
        ),
        "pass", ADMITTED,
    ),
    (
        "adopt_discovery: by a human who gives no basis",
        lambda w: attempt(
            "adopt_discovery", w.anomaly.discovery_id, actor=w.human, reason="reviewed",
            authorization_basis="",
        ),
        "gated", "CCC-RATIFICATION-001",
    ),
    (
        "adopt_discovery: a discovery that does not exist",
        lambda w: attempt(
            "adopt_discovery", "discovery_missing", actor=w.human, reason="reviewed",
            authorization_basis="explicit human adoption",
        ),
        "blocked", "KeyError",
    ),
    (
        "adopt_discovery: a model, on a discovery that does not exist",
        lambda w: attempt(
            "adopt_discovery", "discovery_missing", actor=w.model, reason="consensus",
            authorization_basis="machine consensus",
        ),
        "blocked", "CCC-RATIFICATION-001",
    ),
    (
        "adopt_discovery: no basis and a discovery that does not exist",
        lambda w: attempt(
            "adopt_discovery", "discovery_missing", actor=w.human, reason="reviewed",
            authorization_basis="",
        ),
        "blocked", "CCC-RATIFICATION-001",
    ),
    (
        "advance: an anomaly cannot jump to a mandate",
        lambda w: attempt(
            "advance_discovery", w.anomaly.discovery_id, stage=AnalysisStage.MANDATE,
            actor=w.human, reason="jump", evidence_ids=(_id(w.fact),),
            human_event=True, authorization_basis="explicit human establishment",
        ),
        "blocked", "InvalidTransition",
    ),
    (
        "advance: a model cannot establish a mandate",
        lambda w: attempt(
            "advance_discovery", w.pattern.discovery_id, stage=AnalysisStage.MANDATE,
            actor=w.model, reason="consensus", evidence_ids=(_id(w.fact),),
        ),
        "blocked", "CCC-123-001",
    ),
    (
        "advance: a mandate needs evidence",
        lambda w: attempt(
            "advance_discovery", w.pattern.discovery_id, stage=AnalysisStage.MANDATE,
            actor=w.human, reason="mandate", human_event=True,
            authorization_basis="explicit human establishment",
        ),
        "gated", "CCC-123-001",
    ),
    (
        "advance: a mandate needs an evidence root, not just evidence",
        lambda w: attempt(
            "advance_discovery", w.pattern.discovery_id, stage=AnalysisStage.MANDATE,
            actor=w.human, reason="mandate", evidence_ids=(_id(w.unsupported),),
            human_event=True, authorization_basis="explicit human establishment",
        ),
        "gated", "CCC-123-001",
    ),
    (
        "advance: a mandate needs the human event",
        lambda w: attempt(
            "advance_discovery", w.pattern.discovery_id, stage=AnalysisStage.MANDATE,
            actor=w.human, reason="mandate", evidence_ids=(_id(w.fact),),
            human_event=False, authorization_basis="explicit human establishment",
        ),
        "gated", "CCC-123-001",
    ),
    (
        "advance: a human establishes a mandate on a rooted pattern",
        lambda w: attempt(
            "advance_discovery", w.pattern.discovery_id, stage=AnalysisStage.MANDATE,
            actor=w.human, reason="mandate", evidence_ids=(_id(w.fact),),
            human_event=True, authorization_basis="explicit human establishment",
        ),
        "pass", ADMITTED,
    ),
    # Canonical terminology.
    (
        "canonicalize: by a model",
        lambda w: attempt(
            "canonicalize", w.term.term_id, actor=w.model,
            source_material=(_id(w.fact),), reason="consensus",
            authorization_basis="machine consensus",
        ),
        "blocked", "CCC-CANON-001",
    ),
    (
        "canonicalize: from a machine-proposed source",
        lambda w: attempt(
            "canonicalize", w.term.term_id, actor=w.human,
            source_material=(_id(w.proposal),), reason="cite the proposal",
            authorization_basis="explicit human action",
        ),
        "gated", "CCC-CANON-001",
    ),
    (
        "canonicalize: by a human from a human-established source",
        lambda w: attempt(
            "canonicalize", w.term.term_id, actor=w.human,
            source_material=(_id(w.fact),), reason="established",
            authorization_basis="explicit human action",
        ),
        "pass", ADMITTED,
    ),
    (
        "canonicalize: by a human who names no source",
        lambda w: attempt(
            "canonicalize", w.term.term_id, actor=w.human, source_material=(),
            reason="established", authorization_basis="explicit human action",
        ),
        "gated", "CCC-CANON-001",
    ),
    (
        "canonicalize: by a human who gives no basis",
        lambda w: attempt(
            "canonicalize", w.term.term_id, actor=w.human,
            source_material=(_id(w.fact),), reason="established",
            authorization_basis="",
        ),
        "gated", "CCC-CANON-001",
    ),
    (
        "canonicalize: a term that does not exist",
        lambda w: attempt(
            "canonicalize", "term_missing", actor=w.human,
            source_material=(_id(w.fact),), reason="established",
            authorization_basis="explicit human action",
        ),
        "blocked", "KeyError",
    ),
    (
        "canonicalize: a model, on a term that does not exist",
        lambda w: attempt(
            "canonicalize", "term_missing", actor=w.model,
            source_material=(_id(w.fact),), reason="consensus",
            authorization_basis="machine consensus",
        ),
        "blocked", "CCC-CANON-001",
    ),
    (
        "canonicalize: no basis and a term that does not exist",
        lambda w: attempt(
            "canonicalize", "term_missing", actor=w.human,
            source_material=(_id(w.fact),), reason="established",
            authorization_basis="",
        ),
        "blocked", "CCC-CANON-001",
    ),
    (
        "deprecate_term: by a model",
        lambda w: attempt(
            "deprecate_term", w.term.term_id, actor=w.model, reason="veto",
            authorization_basis="model vote",
        ),
        "blocked", "CCC-HUMAN-001",
    ),
    (
        "deprecate_term: by a human",
        lambda w: attempt(
            "deprecate_term", w.term.term_id, actor=w.human, reason="obsolete",
            authorization_basis="explicit human action",
        ),
        "pass", ADMITTED,
    ),
    (
        "deprecate_term: by a human who gives no basis",
        lambda w: attempt(
            "deprecate_term", w.term.term_id, actor=w.human, reason="obsolete",
            authorization_basis="",
        ),
        "gated", "CCC-HUMAN-001",
    ),
    (
        "supersede_term: by a model",
        lambda w: attempt(
            "supersede_term", w.term.term_id, definition="a better definition",
            actor=w.model, source_material=(_id(w.fact),), reason="consensus",
            authorization_basis="machine consensus",
        ),
        "blocked", "CCC-CANON-001",
    ),
    (
        "supersede_term: by a human from a human-established source",
        lambda w: attempt(
            "supersede_term", w.term.term_id, definition="a better definition",
            actor=w.human, source_material=(_id(w.fact),), reason="superseded",
            authorization_basis="explicit human action",
        ),
        "pass", ADMITTED,
    ),
    (
        "supersede_term: from a machine-proposed source",
        lambda w: attempt(
            "supersede_term", w.term.term_id, definition="a better definition",
            actor=w.human, source_material=(_id(w.proposal),), reason="cite the proposal",
            authorization_basis="explicit human action",
        ),
        "gated", "CCC-CANON-001",
    ),
    (
        "supersede_term: by a human who gives no basis",
        lambda w: attempt(
            "supersede_term", w.term.term_id, definition="a better definition",
            actor=w.human, source_material=(_id(w.fact),), reason="superseded",
            authorization_basis="",
        ),
        "gated", "CCC-CANON-001",
    ),
    (
        "supersede_term: a term that does not exist",
        lambda w: attempt(
            "supersede_term", "term_missing", definition="a better definition",
            actor=w.human, source_material=(_id(w.fact),), reason="superseded",
            authorization_basis="explicit human action",
        ),
        "blocked", "KeyError",
    ),
    # Resolutions that belong to a human.
    (
        "record_resolution: by a model",
        lambda w: attempt(
            "record_resolution", w.conflict.conflict_id, choice="a", actor=w.model,
            reason="consensus", authorization_basis="machine consensus",
        ),
        "blocked", "CCC-HUMAN-001",
    ),
    (
        "record_resolution: by a human",
        lambda w: attempt(
            "record_resolution", w.conflict.conflict_id, choice="a", actor=w.human,
            reason="decided", authorization_basis="explicit human decision",
        ),
        "pass", ADMITTED,
    ),
    (
        "record_resolution: by a human who gives no basis",
        lambda w: attempt(
            "record_resolution", w.conflict.conflict_id, choice="a", actor=w.human,
            reason="decided", authorization_basis="",
        ),
        "gated", "CCC-HUMAN-001",
    ),
    (
        "resolve_uncertainty: by a model",
        lambda w: attempt(
            "resolve_uncertainty", w.uncertainty.uncertainty_id, choice="a",
            actor=w.model, reason="consensus", authorization_basis="machine consensus",
        ),
        "blocked", "CCC-HUMAN-001",
    ),
    (
        "resolve_uncertainty: by a human",
        lambda w: attempt(
            "resolve_uncertainty", w.uncertainty.uncertainty_id, choice="a",
            actor=w.human, reason="decided", authorization_basis="explicit human decision",
        ),
        "pass", ADMITTED,
    ),
    (
        "resolve_inflection: by a model",
        lambda w: attempt(
            "resolve_inflection", w.inflection.inflection_id, significance="material",
            actor=w.model, reason="consensus", authorization_basis="machine consensus",
        ),
        "blocked", "CCC-HUMAN-001",
    ),
    (
        "resolve_inflection: by a human",
        lambda w: attempt(
            "resolve_inflection", w.inflection.inflection_id, significance="material",
            actor=w.human, reason="decided", authorization_basis="explicit human decision",
        ),
        "pass", ADMITTED,
    ),
]

SCENARIO_IDS = [name for name, *_ in SCENARIOS]
GATED = [row for row in SCENARIOS if row[2] == "gated"]
BLOCKED = [row for row in SCENARIOS if row[2] == "blocked"]
#: The blocked scenarios CCC refuses by a rule (the others are refused input).
BLOCKED_BY_A_RULE = [row for row in BLOCKED if row[3].startswith("CCC-")]


def _supply_basis(w, att):
    return _with(att, authorization_basis=GOOD)


def _attach_a_human_root_then_retry(w, att):
    w.system.attach_evidence(
        att.args[0], _id(w.fact2), actor=w.human, rationale="a human fact supports it",
    )
    return att


#: What a human supplies, for each gated scenario, to get the same call admitted.
#: A repair may act on the live world first (attach evidence); it returns the
#: attempt to make again. A test applies it and checks CCC then admits the call.
REPAIRS = {
    "establish: by a human who gives no basis": _supply_basis,
    "accept: by a human who gives no basis": _supply_basis,
    "ratify: by a human who gives no basis": _supply_basis,
    "decide: by a human who gives no basis": _supply_basis,
    **{f"{op}: by a human who gives no basis": _supply_basis for op in _HISTORY},
    "adopt_discovery: by a human who gives no basis": _supply_basis,
    "canonicalize: by a human who gives no basis": _supply_basis,
    "deprecate_term: by a human who gives no basis": _supply_basis,
    "supersede_term: by a human who gives no basis": _supply_basis,
    "supersede_term: from a machine-proposed source": lambda w, att: _with(
        att, source_material=(_id(w.fact),)
    ),
    "record_resolution: by a human who gives no basis": _supply_basis,
    "classify: a human cannot promote an inference with no evidence root": (
        _attach_a_human_root_then_retry
    ),
    "advance: a mandate needs evidence": lambda w, att: _with(
        att, evidence_ids=(_id(w.fact),)
    ),
    "advance: a mandate needs an evidence root, not just evidence": lambda w, att: _with(
        att, evidence_ids=(_id(w.fact),)
    ),
    "advance: a mandate needs the human event": lambda w, att: _with(
        att, human_event=True
    ),
    "canonicalize: from a machine-proposed source": lambda w, att: _with(
        att, source_material=(_id(w.fact),)
    ),
    "canonicalize: by a human who names no source": lambda w, att: _with(
        att, source_material=(_id(w.fact),)
    ),
}


def _fingerprint(system: CCCSystem) -> str:
    return json.dumps(system.store.snapshot(), sort_keys=True)


def _records(system: CCCSystem) -> str:
    """Every record but the log of rule decisions, which a refusal does append to."""
    snapshot = system.store.snapshot()
    snapshot.pop("rule_decisions")
    return json.dumps(snapshot, sort_keys=True)


def _native(att, system: CCCSystem):
    """What CCC itself does with the attempt: None if it returned, else the refusal."""
    try:
        att.run(system)
    except (CCCError, ValueError, KeyError) as exc:
        return exc
    return None


def test_cns_is_seen_as_available():
    assert cns_available() is True


def test_the_pass_reason_is_the_one_the_tests_and_the_readme_quote():
    assert PASS_REASON == ADMITTED


def test_the_gate_name_is_the_one_the_docs_quote():
    """Written out, not imported: a consumer filters verdicts on this string."""
    w = _world()
    assert GATE_NAME == "ccc.transition"
    assert CccGate(w.system).name == "ccc.transition"
    att = attempt("reject", _id(w.proposal), actor=w.human, reason="r", authorization_basis="b")
    assert judge(w.system, att).gate == "ccc.transition"


def test_every_transition_the_connector_judges_exists_on_the_facade():
    assert all(callable(getattr(CCCSystem, name)) for name in TRANSITIONS)
    assert len(set(TRANSITIONS)) == len(TRANSITIONS)


def test_the_scenarios_cover_every_judged_transition_and_every_verdict():
    w = _world()
    built = [make(w) for _, make, _, _ in SCENARIOS]
    assert {a.operation for a in built} == set(TRANSITIONS)
    assert {kind for _, _, kind, _ in SCENARIOS} == {"pass", "gated", "blocked"}
    assert len(set(SCENARIO_IDS)) == len(SCENARIO_IDS)


@pytest.mark.parametrize("name,make,kind,front", SCENARIOS, ids=SCENARIO_IDS)
def test_each_attempt_gets_the_verdict_ccc_implies(name, make, kind, front):
    w = _world()
    att = make(w)
    verdict = CccGate(w.system).check(att)
    assert verdict.outcome is OUTCOME[kind]
    assert verdict.reason.startswith(front), verdict.reason
    assert verdict.position is cns_gate.GatePosition.ALPHA
    assert verdict.gate == GATE_NAME
    assert verdict.blocking() is (kind != "pass")
    if kind == "pass":
        assert verdict.reason == ADMITTED


@pytest.mark.parametrize("name,make,kind,front", SCENARIOS, ids=SCENARIO_IDS)
def test_the_connector_agrees_with_what_ccc_actually_does(name, make, kind, front):
    """The translation must not change what CCC decided."""
    w = _world()
    att = make(w)
    verdict = judge(w.system, att)
    native = _native(att, w.system)
    assert (verdict.outcome is PASS) is (native is None)
    if isinstance(native, ConstitutionViolation):
        assert verdict.outcome in (RETRY, BREACH)
        assert verdict.reason == str(native)
    elif native is not None:
        assert verdict.outcome is BREACH
        assert verdict.reason == f"{type(native).__name__}: {native}"


@pytest.mark.parametrize("name,make,kind,front", SCENARIOS, ids=SCENARIO_IDS)
def test_judging_leaves_the_live_system_exactly_as_it_was(name, make, kind, front):
    w = _world()
    att = make(w)
    before = _fingerprint(w.system)
    CccGate(w.system).check(att)
    judge(w.system, att)
    assert _fingerprint(w.system) == before
    assert "repair-probe" not in before  # the stand-in root never reaches the live store


@pytest.mark.parametrize("name,make,kind,front", SCENARIOS, ids=SCENARIO_IDS)
def test_judging_first_does_not_change_what_ccc_then_decides(name, make, kind, front):
    judged, control = _world(), _world()
    CccGate(judged.system).check(make(judged))
    a = _native(make(judged), judged.system)
    b = _native(make(control), control.system)
    assert type(a) is type(b)
    assert getattr(a, "rule_id", None) == getattr(b, "rule_id", None)
    assert len(judged.system.store.audit_events) == len(control.system.store.audit_events)
    assert len(judged.system.store.rule_decisions) == len(control.system.store.rule_decisions)
    assert judged.system.validate_constitution()["valid"] is True


@pytest.mark.parametrize("name,make,kind,front", SCENARIOS, ids=SCENARIO_IDS)
def test_every_verdict_is_bound_to_the_attempt_it_judged(name, make, kind, front):
    w = _world()
    att = make(w)
    verdict = judge(w.system, att)
    assert verdict.bound()
    assert cns_gate.unbound([verdict]) == ()
    assert verdict.binds(att.subject, attempt_digest(att))
    assert not verdict.binds(att.subject, attempt_digest(attempt(
        "decide", "something else", actor=w.human, reason="r", authorization_basis="b",
    )))


@pytest.mark.parametrize(
    "name,make,kind,front",
    [row for row in SCENARIOS if row[2] != "pass"],
    ids=[row[0] for row in SCENARIOS if row[2] != "pass"],
)
def test_a_refused_transition_has_changed_no_record(name, make, kind, front):
    """The ALPHA claim, for every judged operation that a scenario refuses: CCC
    evaluates before it mutates, so a refusal leaves every record as it was (only
    the log of rule decisions grows)."""
    w = _world()
    att = make(w)
    before = _records(w.system)
    assert _native(att, w.system) is not None
    assert _records(w.system) == before


# What RETRY and TERMINAL_BREACH mean, checked from outside the connector.


def test_every_gated_scenario_has_a_repair_and_every_repair_a_scenario():
    assert set(REPAIRS) == {name for name, *_ in GATED}


@pytest.mark.parametrize("name,make,kind,front", GATED, ids=[row[0] for row in GATED])
def test_a_retry_names_a_repair_that_gets_the_same_call_admitted(name, make, kind, front):
    w = _world()
    att = make(w)
    assert judge(w.system, att).outcome is RETRY
    repaired = REPAIRS[name](w, att)
    assert repaired.operation == att.operation
    assert repaired.kwargs["actor"] == att.kwargs["actor"]  # the actor never changes
    assert judge(w.system, repaired).outcome is PASS
    assert _native(repaired, w.system) is None


def _padded(w, att):
    """What a human could add to the same call: a basis, the human event, a
    human-established root as evidence and as source material, and the root
    attached to, and the human adoption of, the artifact it concerns."""
    given = set(att.content["arguments"])
    fact = _id(w.fact)
    patch = {}
    if "authorization_basis" in given:
        patch["authorization_basis"] = GOOD
    if "human_event" in given:
        patch["human_event"] = True
    if "evidence_ids" in given:
        patch["evidence_ids"] = (fact,)
    if "source_material" in given:
        patch["source_material"] = (fact,)
    target = att.args[0] if att.args else None
    if target in w.system.store.artifacts:
        for step in (
            lambda: w.system.attach_evidence(
                target, fact, actor=w.human, rationale="a human fact supports it"
            ),
            lambda: w.system.accept(
                target, actor=w.human, reason="adopted", authorization_basis=GOOD
            ),
        ):
            try:
                step()
            except (CCCError, ValueError, KeyError):
                pass
    return _with(att, **patch)


@pytest.mark.parametrize(
    "name,make,kind,front", BLOCKED_BY_A_RULE, ids=[row[0] for row in BLOCKED_BY_A_RULE]
)
def test_nothing_a_human_adds_admits_a_blocked_constitutional_refusal(name, make, kind, front):
    w = _world()
    att = make(w)
    assert isinstance(_native(att, w.system), ConstitutionViolation)
    padded = _padded(w, att)
    assert judge(w.system, padded).outcome is not PASS
    assert _native(padded, w.system) is not None


def test_a_model_is_blocked_whatever_it_adds_and_the_human_asking_is_a_different_call():
    """CCC's own word is blocked (``self_promotion_blocked``). The same proposal:
    refused for the model however it is padded; refused for a human who leaves the
    basis out, who is told to supply it; admitted for a human who supplies it."""
    w = _world()
    gate = CccGate(w.system)
    by_model = gate.check(attempt(
        "accept", _id(w.proposal), actor=w.model, reason="consensus",
        authorization_basis="machine consensus", evidence_ids=(_id(w.fact),),
    ))
    by_human_without = gate.check(attempt(
        "accept", _id(w.proposal), actor=w.human, reason="reviewed",
        authorization_basis="", evidence_ids=(_id(w.fact),),
    ))
    by_human = gate.check(attempt(
        "accept", _id(w.proposal), actor=w.human, reason="reviewed",
        authorization_basis="explicit human adoption", evidence_ids=(_id(w.fact),),
    ))
    assert by_model.outcome is BREACH
    assert by_human_without.outcome is RETRY
    assert by_human.outcome is PASS
    assert cns_gate.resolve([by_model, by_human]) is BREACH
    assert cns_gate.resolve([by_human_without, by_human]) is RETRY


def test_the_same_fault_gets_the_same_verdict_whichever_rule_fires():
    """The verdict follows who is asking and what is missing, not the rule's name:
    a model is blocked and a human who left the basis out is told to supply it, for
    every human-only operation alike."""
    w = _world()
    gate = CccGate(w.system)
    cases = {
        "accept": lambda a, b: attempt(
            "accept", _id(w.proposal), actor=a, reason="r", authorization_basis=b),
        "establish_provenance": lambda a, b: attempt(
            "establish_provenance", _id(w.proposal), actor=a, reason="r",
            authorization_basis=b),
        "decide": lambda a, b: attempt(
            "decide", "choice", actor=a, reason="r", authorization_basis=b),
        "erase": lambda a, b: attempt(
            "erase", _id(w.fact), actor=a, reason="r", authorization_basis=b),
        "correct": lambda a, b: attempt(
            "correct", _id(w.fact), content="c", actor=a, reason="r",
            authorization_basis=b),
        "deprecate_term": lambda a, b: attempt(
            "deprecate_term", w.term.term_id, actor=a, reason="r", authorization_basis=b),
        "supersede_term": lambda a, b: attempt(
            "supersede_term", w.term.term_id, definition="d", actor=a,
            source_material=(_id(w.fact),), reason="r", authorization_basis=b),
        "adopt_discovery": lambda a, b: attempt(
            "adopt_discovery", w.anomaly.discovery_id, actor=a, reason="r",
            authorization_basis=b),
    }
    for op, build in cases.items():
        for model_like in (w.model, Actor.system(), Actor.external("x")):
            assert gate.check(build(model_like, "any basis")).outcome is BREACH, op
        assert gate.check(build(w.human, "")).outcome is RETRY, op
        assert gate.check(build(w.human, GOOD)).outcome is PASS, op


def test_an_evidence_list_of_none_is_read_as_empty_by_the_repair_probe():
    """CCC refuses erased material before it reads ``evidence_ids``, so ``None``
    reaches the probe, which must read it as empty rather than splat it."""
    w = _world()
    for op, args in (
        ("classify", (_id(w.erased), EpistemicStatus.EVIDENCE)),
        ("accept", (_id(w.erased),)),
    ):
        att = attempt(
            op, *args, actor=w.human, reason="r", authorization_basis=GOOD,
            evidence_ids=None,
        ) if op == "accept" else attempt(
            op, *args, actor=w.human, reason="r", evidence_ids=None,
        )
        assert _native(att, w.system).rule_id == "CCC-HISTORY-002"
        verdict = judge(w.system, att)
        assert verdict.outcome is BREACH
        assert verdict.reason.startswith("CCC-HISTORY-002")


def test_a_refusal_whose_repaired_call_cannot_run_is_a_breach_not_a_crash():
    """CCC refuses these before it would touch the badly typed argument, so the
    real operation returns a refusal. With the human inputs added the rule no
    longer comes first and CCC cannot run the call at all (AttributeError,
    TypeError). That is no repair, and judge must say so, not crash where CCC
    refused: the verdict is a breach carrying CCC's own refusal."""
    w = _world()
    gate = CccGate(w.system)
    cases = [
        attempt(
            "amend", _id(w.fact), content=5.5, actor=w.human, reason="r",
            authorization_basis="",
        ),
        attempt(
            "correct", _id(w.fact), content=["x"], actor=w.human, reason="r",
            authorization_basis="",
        ),
        attempt("decide", {"a": 1}, actor=w.human, reason="r", authorization_basis=""),
        attempt(
            "deprecate_term", {}, actor=w.human, reason="r", authorization_basis="",
        ),
        attempt(
            "record_resolution", [], choice="a", actor=w.human, reason="r",
            authorization_basis="",
        ),
        attempt(
            "adopt_discovery", ["x"], actor=w.human, reason="r", authorization_basis="",
        ),
        attempt(
            "ratify", _id(w.erased), actor=Actor.system(), reason="r",
            authorization_basis="", status=ProvenanceStatus.USER_ESTABLISHED,
            evidence_ids=-1,
        ),
        attempt(
            "accept", _id(w.erased), actor=w.model, reason="r",
            authorization_basis="b", evidence_ids=Actor.human("not-a-list"),
        ),
    ]
    for att in cases:
        refusal = _native(att, w.system)
        assert isinstance(refusal, ConstitutionViolation), att.operation
        verdict = gate.check(att)
        assert verdict.outcome is BREACH, att.operation
        assert verdict.reason == str(refusal), att.operation
        assert verdict.binds(att.subject, attempt_digest(att)), att.operation


def test_an_input_that_makes_the_real_operation_crash_crashes_judge_the_same_way():
    """Not a refusal, so not translated: the same TypeError, never a verdict."""
    w = _world()
    att = attempt(
        "advance_discovery", w.pattern.discovery_id, stage=AnalysisStage.MANDATE,
        actor=w.human, reason="mandate", evidence_ids=None, human_event=True,
        authorization_basis=GOOD,
    )
    with pytest.raises(TypeError):
        att.run(w.system)
    with pytest.raises(TypeError):
        judge(w.system, att)


def test_a_retry_becomes_a_pass_once_the_evidence_root_exists():
    w = _world()
    gate = CccGate(w.system)
    promote = attempt(
        "classify", _id(w.unsupported), EpistemicStatus.EVIDENCE, actor=w.human,
        reason="now rooted",
    )
    assert gate.check(promote).outcome is RETRY
    w.system.attach_evidence(
        _id(w.unsupported), _id(w.fact2), actor=w.human, rationale="a human fact supports it",
    )
    assert gate.check(promote).outcome is PASS


def test_a_blocked_refusal_stays_blocked_whatever_the_human_adds():
    w = _world()
    gate = CccGate(w.system)
    promote = attempt(
        "classify", _id(w.simulation), HIST, actor=w.human, reason="relabel",
        evidence_ids=(_id(w.fact),),
    )
    assert gate.check(promote).outcome is BREACH
    w.system.attach_evidence(
        _id(w.simulation), _id(w.fact), actor=w.human, rationale="a human fact",
    )
    assert gate.check(promote).outcome is BREACH


def test_machine_consensus_can_be_adopted_but_not_established():
    """Established is refused for good, so it is a breach; adopted is admitted."""
    w = _world()
    gate = CccGate(w.system)
    establish = attempt(
        "establish_provenance", _id(w.consensus), actor=w.human, reason="reviewed",
        authorization_basis="explicit human establishment",
    )
    adopt = attempt(
        "accept", _id(w.consensus), actor=w.human, reason="reviewed",
        authorization_basis="explicit human adoption",
    )
    assert gate.check(establish).outcome is BREACH
    assert gate.check(adopt).outcome is PASS
    w.system.accept(
        _id(w.consensus), actor=w.human, reason="reviewed",
        authorization_basis="explicit human adoption",
    )
    assert gate.check(establish).outcome is BREACH  # adopting did not unlock it


def test_erased_material_stays_refused_because_ccc_has_no_restore():
    w = _world()
    gate = CccGate(w.system)
    for att in (
        attempt("attach_evidence", _id(w.proposal), _id(w.erased), actor=w.human,
                rationale="gone"),
        attempt("accept", _id(w.erased), actor=w.human, reason="r",
                authorization_basis=GOOD),
        attempt("classify", _id(w.erased), EpistemicStatus.EVIDENCE, actor=w.human,
                reason="r"),
    ):
        assert gate.check(att).outcome is BREACH
        assert gate.check(_padded(w, att)).outcome is BREACH


def test_the_verdict_follows_what_ccc_does_not_what_the_registry_says(monkeypatch):
    """Every rule's declared ``decision`` text is rewritten; no verdict moves."""
    baseline = {}
    w = _world()
    for name, make, _, _ in SCENARIOS:
        baseline[name] = judge(w.system, make(w)).outcome
    for decision in ("ALLOW", "REJECT", "ALLOW only with human adoption", ""):
        rewritten = {
            rule_id: dataclasses.replace(rule, decision=decision)
            for rule_id, rule in constitutional_rules.RULE_INDEX.items()
        }
        monkeypatch.setattr(constitutional_rules, "RULE_INDEX", rewritten)
        w = _world()
        for name, make, _, _ in SCENARIOS:
            assert judge(w.system, make(w)).outcome is baseline[name], (name, decision)


# The translation, exercised without a store: every kind of native outcome.


def _att():
    return attempt(
        "accept", "artifact_x", actor=Actor.human("h"), reason="r",
        authorization_basis="b",
    )


def test_a_call_that_returned_is_a_pass_with_an_honest_reason():
    verdict = to_cns_result(_att(), None)
    assert verdict.outcome is PASS
    assert verdict.reason == ADMITTED
    assert not verdict.blocking()


@pytest.mark.parametrize(
    "rule_id",
    ["CCC-PROVENANCE-002", "CCC-EPISTEMIC-003", "CCC-HUMAN-001", "CCC-NOT-A-RULE", ""],
)
def test_a_constitutional_refusal_fails_closed_unless_a_repair_was_shown(rule_id):
    """No rule name, declared or not, makes a refusal retryable by itself."""
    refusal = ConstitutionViolation(rule_id, "because")
    closed = to_cns_result(_att(), refusal)
    assert closed.outcome is BREACH
    assert closed.reason == f"{rule_id}: because"
    assert to_cns_result(_att(), refusal, repairable=False).outcome is BREACH
    assert to_cns_result(_att(), refusal, repairable=1).outcome is BREACH
    shown = to_cns_result(_att(), refusal, repairable=True)
    assert shown.outcome is RETRY
    assert shown.reason == f"{rule_id}: because"


@pytest.mark.parametrize(
    "error",
    [
        InvalidTransition("USER_ACCEPTED -> USER_ACCEPTED is not a transition"),
        NotFound("artifact artifact_x"),
        ValueError("refusing a malformed finding"),
        KeyError("discovery_x"),
        CCCError("a base CCC error"),
        RuntimeError("an error CCC did not classify"),
        AssertionError("anything else is an error too"),
    ],
    ids=lambda e: type(e).__name__,
)
def test_anything_else_ccc_errors_on_is_a_terminal_breach_and_never_a_pass(error):
    for repairable in (False, True):
        verdict = to_cns_result(_att(), error, repairable=repairable)
        assert verdict.outcome is BREACH
        assert verdict.blocking()
        assert verdict.reason.startswith(type(error).__name__)


def test_a_repair_cannot_turn_a_pass_into_anything_else():
    assert to_cns_result(_att(), None, repairable=True).outcome is PASS


def test_an_outcome_that_is_not_an_exception_is_refused_rather_than_read_as_success():
    with pytest.raises(TypeError):
        to_cns_result(_att(), "updated artifact")


def test_a_refusal_from_a_bug_in_the_operation_is_not_translated(monkeypatch):
    w = _world()
    att = attempt(
        "accept", _id(w.proposal), actor=w.human, reason="r", authorization_basis="b",
    )

    def boom(self, *args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(CCCSystem, "accept", boom)
    with pytest.raises(RuntimeError):
        CccGate(w.system).check(att)


def test_a_native_value_error_is_a_terminal_breach_through_judge_never_a_pass():
    w = _world()
    att = attempt(
        "attach_evidence", _id(w.proposal), _id(w.fact2), actor=w.human,
        rationale="too strong", support_strength=1.5,
    )
    verdict = judge(w.system, att)
    assert verdict.outcome is BREACH
    assert verdict.blocking()
    assert verdict.reason == "ValueError: support_strength must be between 0 and 1"
    assert verdict.binds(att.subject, attempt_digest(att))


# What is bound.


def test_the_judged_content_is_a_stable_canonical_mapping():
    att = attempt(
        "accept", "artifact_x", actor=Actor.human("h", "Ada"), reason="r",
        authorization_basis="b",
    )
    assert att.content == {
        "operation": "accept",
        "arguments": {
            "artifact_id": "artifact_x",
            "actor": {"actor_id": "h", "kind": "HUMAN", "label": "Ada"},
            "reason": "r",
            "authorization_basis": "b",
            "evidence_ids": [],
        },
    }
    assert attempt_digest(att) == cns_gate.subject_digest(att.content)


def test_positional_and_keyword_spellings_and_defaults_digest_alike():
    human = Actor.human("h")
    a = attempt("accept", "artifact_x", actor=human, reason="r", authorization_basis="b")
    b = attempt(
        "accept", artifact_id="artifact_x", actor=human, reason="r",
        authorization_basis="b", evidence_ids=(),
    )
    assert attempt_digest(a) == attempt_digest(b)


@pytest.mark.parametrize(
    "change",
    [
        {"artifact_id": "artifact_y"},
        {"actor": Actor.model("h")},
        {"actor": Actor.human("someone-else")},
        {"reason": "another reason"},
        {"authorization_basis": "another basis"},
        {"evidence_ids": ("artifact_z",)},
    ],
    ids=lambda c: next(iter(c)),
)
def test_changing_any_part_of_the_attempt_changes_the_digest(change):
    base = dict(
        artifact_id="artifact_x", actor=Actor.human("h"), reason="r",
        authorization_basis="b",
    )
    assert attempt_digest(attempt("accept", **base)) != attempt_digest(
        attempt("accept", **{**base, **change})
    )


def test_a_different_operation_with_the_same_arguments_digests_differently():
    kwargs = dict(actor=Actor.human("h"), reason="r", authorization_basis="b")
    assert attempt_digest(attempt("accept", "artifact_x", **kwargs)) != attempt_digest(
        attempt("reject", "artifact_x", **kwargs)
    )


def test_operations_that_forward_their_arguments_are_bound_to_real_names():
    """adopt_discovery, advance_discovery, canonicalize and the other forwarding
    operations take ``*args, **kwargs`` on the facade; the digest must not depend on
    how a caller spells them."""
    human = Actor.human("h")
    a = attempt(
        "adopt_discovery", "discovery_x", actor=human, reason="r", authorization_basis="b",
    )
    b = attempt(
        "adopt_discovery", discovery_id="discovery_x", actor=human, reason="r",
        authorization_basis="b",
    )
    assert attempt_digest(a) == attempt_digest(b)
    assert a.content["arguments"]["discovery_id"] == "discovery_x"

    c = attempt(
        "advance_discovery", "discovery_x", stage=AnalysisStage.MANDATE, actor=human,
        reason="r",
    )
    d = attempt(
        "advance_discovery", discovery_id="discovery_x", stage=AnalysisStage.MANDATE,
        actor=human, reason="r", evidence_ids=(), human_event=False,
        authorization_basis=None,
    )
    assert attempt_digest(c) == attempt_digest(d)

    e = attempt(
        "canonicalize", "term_x", actor=human, source_material=("artifact_x",),
        reason="r", authorization_basis="b",
    )
    f = attempt(
        "canonicalize", term_id="term_x", actor=human, source_material=["artifact_x"],
        reason="r", authorization_basis="b",
    )
    assert attempt_digest(e) == attempt_digest(f)

    s = attempt(
        "supersede_term", "term_x", definition="d", actor=human,
        source_material=("artifact_x",), reason="r", authorization_basis="b",
    )
    u = attempt(
        "supersede_term", term_id="term_x", definition="d", actor=human,
        source_material=["artifact_x"], reason="r", authorization_basis="b",
    )
    assert attempt_digest(s) == attempt_digest(u)
    assert s.content["arguments"]["term_id"] == "term_x"

    g = attempt(
        "resolve_uncertainty", "uncertainty_x", choice="a", actor=human, reason="r",
        authorization_basis="b",
    )
    h = attempt(
        "resolve_uncertainty", uncertainty_id="uncertainty_x", choice="a", actor=human,
        reason="r", authorization_basis="b",
    )
    assert attempt_digest(g) == attempt_digest(h)


def test_no_judged_operation_is_digested_as_opaque_args_and_kwargs():
    w = _world()
    for _, make, _, _ in SCENARIOS:
        assert not {"args", "kwargs"} & set(make(w).content["arguments"])


def test_an_actor_field_is_bound_as_what_it_is_not_as_its_text():
    """A missing label and the text "None" are different content."""
    none = attempt("ingest", "c", actor=Actor("a", Actor.human().kind, None))  # type: ignore[arg-type]
    text = attempt("ingest", "c", actor=Actor("a", Actor.human().kind, "None"))
    assert none.content["arguments"]["actor"]["label"] is None
    assert attempt_digest(none) != attempt_digest(text)


def test_a_bool_and_an_int_are_different_content():
    human = Actor.human("h")
    as_int = attempt("ingest", "c", actor=human, presentation_priority=1)
    as_bool = attempt("ingest", "c", actor=human, presentation_priority=True)
    assert attempt_digest(as_int) != attempt_digest(as_bool)


def test_floats_are_bound_by_value_and_distinct_from_ints():
    human = Actor.human("h")

    def digest(value):
        return attempt_digest(attempt("ingest", "c", actor=human, confidence=value))

    assert digest(0.5) != digest(0.9)
    assert digest(0.5) == digest(0.5)
    assert digest(1) != digest(1.0)
    assert digest(0.0) == digest(-0.0)
    assert attempt("ingest", "c", actor=human, confidence=0.5).content["arguments"][
        "confidence"
    ] == 0.5


def test_a_verdict_does_not_bind_to_another_attempt_or_another_label():
    w = _world()
    att = attempt(
        "accept", _id(w.proposal), actor=w.human, reason="r", authorization_basis="b",
    )
    other = attempt(
        "accept", _id(w.proposal), actor=w.human, reason="r", authorization_basis="c",
    )
    verdict = judge(w.system, att)
    assert verdict.binds("accept", attempt_digest(att))
    assert not verdict.binds("accept", attempt_digest(other))
    assert not verdict.binds("reject", attempt_digest(att))
    assert not verdict.binds("", "")


def test_a_named_subject_is_what_the_verdict_binds_to():
    w = _world()
    att = dataclasses.replace(
        attempt("accept", _id(w.proposal), actor=w.human, reason="r", authorization_basis="b"),
        subject="review-7",
    )
    verdict = judge(w.system, att)
    assert verdict.subject == "review-7"
    assert verdict.binds("review-7", attempt_digest(att))
    assert not verdict.binds("accept", attempt_digest(att))


def test_an_attempt_keeps_a_copy_so_what_is_digested_is_what_is_run():
    w = _world()
    metadata = {"note": "original"}
    att = attempt("ingest", "c", actor=w.human, metadata=metadata)
    digest = attempt_digest(att)
    metadata["note"] = "changed after the attempt was built"
    assert attempt_digest(att) == digest
    assert att.kwargs["metadata"] == {"note": "original"}

    # Positional arguments are copied too, whatever their type.
    parts = ["part one"]
    positional = attempt("ingest", parts, actor=w.human)
    digest = attempt_digest(positional)
    parts.append("part two")
    assert attempt_digest(positional) == digest
    assert positional.args == (["part one"],)


def test_an_attempt_changed_after_it_was_built_is_not_run_or_judged():
    """The kwargs mapping is read-only but what is inside it is not; changing it
    must not make ``run`` execute something that was never digested."""
    w = _world()
    att = attempt(
        "canonicalize", w.term.term_id, actor=w.human,
        source_material=[_id(w.proposal)], reason="r", authorization_basis=GOOD,
    )
    digest = attempt_digest(att)
    assert judge(w.system, att).outcome is RETRY  # a machine-proposed source
    att.kwargs["source_material"][0] = _id(w.fact)  # now a human fact
    with pytest.raises(AttemptChanged):
        judge(w.system, att)
    with pytest.raises(AttemptChanged):
        att.run(w.system)
    with pytest.raises(AttemptChanged):
        CccGate(w.system).check(att)
    assert attempt_digest(att) == digest  # the content is still what was built
    assert w.system.store.terms[w.term.term_id].status.value != "CANONICAL"


def test_the_content_of_an_attempt_cannot_be_edited_through_the_property():
    att = _att()
    att.content["arguments"]["reason"] = "edited"
    assert att.content["arguments"]["reason"] == "r"
    assert attempt_digest(att) == attempt_digest(_att())


def test_an_attempt_can_be_copied_and_pickled_and_stays_the_same_attempt():
    att = _att()
    for clone in (copy.copy(att), copy.deepcopy(att), pickle.loads(pickle.dumps(att))):
        assert clone is not att
        assert clone.operation == att.operation
        assert clone.subject == att.subject
        assert clone.content == att.content
        assert attempt_digest(clone) == attempt_digest(att)
    named = dataclasses.replace(att, subject="review-7")
    assert pickle.loads(pickle.dumps(named)).subject == "review-7"


def test_content_ccc_accepts_but_cns_cannot_bind_is_refused_not_left_unbound():
    human = Actor.human("h")
    for extra in (
        {"confidence": float("nan")},
        {"confidence": float("inf")},
        {"confidence": float("-inf")},
        {"metadata": {"tags": {1, 2}}},
        {"metadata": {"blob": b"bytes"}},
        {"metadata": {1: "a", "1": "b"}},
    ):
        with pytest.raises(TypeError):
            attempt("ingest", "c", actor=human, **extra)


def _nested(levels: int):
    value: object = "leaf"
    for _ in range(levels):
        value = [value]
    return value


def test_content_that_would_crash_the_digest_later_is_refused_at_build():
    """Valid text, integers and nesting that CCC itself accepts, but that the
    digest cannot take, are TypeError when the attempt is built: never a ValueError
    or RecursionError from ``judge``, where a caller would read it as a refusal."""
    human = Actor.human("h")
    cycle: list = []
    cycle.append(cycle)
    for kwargs in (
        {"reason": "lone surrogate \ud800"},
        {"authorization_basis": "\udc80"},
        {"actor": Actor.human("lone \ud800 surrogate")},
        {"reason": {"\ud800": "a key"}},
    ):
        base = dict(actor=human, reason="r", authorization_basis="b")
        with pytest.raises(TypeError):
            attempt("decide", "c", **{**base, **kwargs})
    for extra in (
        {"presentation_priority": 10 ** 5000},
        {"presentation_priority": -(10 ** 5000)},
        {"presentation_priority": 1 << MAX_INT_BITS},
        {"metadata": {"deep": _nested(MAX_DEPTH)}},
        {"metadata": {"deep": _nested(480)}},
        {"metadata": {"cycle": cycle}},
    ):
        with pytest.raises(TypeError):
            attempt("ingest", "c", actor=human, **extra)


def test_the_largest_content_the_connector_accepts_is_judged_without_error():
    w = _world()
    widest = (1 << MAX_INT_BITS) - 1
    for extra in (
        {"presentation_priority": widest},
        {"presentation_priority": -widest},
        {"metadata": {"deep": _nested(MAX_DEPTH - 1)}},
        {"metadata": {"text": "unicode \u00e9\u4e2d\U0001f600 and a long " + "x" * 100000}},
    ):
        att = attempt("ingest", "c", actor=w.human, **extra)
        verdict = judge(w.system, att)
        assert verdict.outcome is PASS
        assert verdict.binds(att.subject, attempt_digest(att))
        assert _native(att, w.system) is None


def test_a_store_ccc_cannot_snapshot_is_not_judged_on_a_guess():
    import datetime

    w = _world()
    w.system.ingest(
        "a record whose metadata JSON cannot render", actor=w.human,
        metadata={"when": datetime.datetime(2026, 1, 1)},
    )
    att = attempt(
        "accept", _id(w.proposal), actor=w.human, reason="r", authorization_basis="b",
    )
    with pytest.raises(PreflightError) as caught:
        judge(w.system, att)
    assert isinstance(caught.value.__cause__, TypeError)
    # It is not a refusal: a caller's `except (TypeError, ValueError)` must not eat it.
    assert not issubclass(PreflightError, (TypeError, ValueError, CCCError, KeyError))
    # CCC itself is unaffected: the real operation still decides.
    assert _native(att, w.system) is None


def test_the_snapshot_is_private_while_it_exists_and_gone_when_the_check_ends(
    tmp_path, monkeypatch
):
    """The snapshot holds the live store's content. It sits in a directory only the
    user can enter, and is removed whatever the check ends in: each verdict, a
    crash of the attempt itself, and a store that cannot be snapshotted."""
    import datetime

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    modes = []
    real_save = CCCStore.save

    def spy(self, path=None):
        modes.append(stat.S_IMODE(Path(path).parent.stat().st_mode))
        return real_save(self, path)

    monkeypatch.setattr(CCCStore, "save", spy)
    w = _world()
    crash = attempt(
        "advance_discovery", w.pattern.discovery_id, stage=AnalysisStage.MANDATE,
        actor=w.human, reason="mandate", evidence_ids=None, human_event=True,
        authorization_basis=GOOD,
    )
    checks = [
        (attempt("reject", _id(w.proposal), actor=w.human, reason="r",
                 authorization_basis=GOOD), PASS),
        (attempt("accept", _id(w.proposal), actor=w.model, reason="r",
                 authorization_basis=GOOD), BREACH),
        (attempt("accept", _id(w.proposal), actor=w.human, reason="r",
                 authorization_basis=""), RETRY),
        (crash, TypeError),
    ]
    for att, expected in checks:
        if expected is TypeError:
            with pytest.raises(TypeError):
                judge(w.system, att)
        else:
            assert judge(w.system, att).outcome is expected
        assert list(tmp_path.iterdir()) == []
    w.system.ingest("unrenderable", actor=w.human, metadata={"when": datetime.datetime(2026, 1, 1)})
    with pytest.raises(PreflightError):
        judge(w.system, checks[0][0])
    assert list(tmp_path.iterdir()) == []
    assert len(modes) >= 5
    assert set(modes) == {0o700}


def test_a_snapshot_that_cannot_be_reloaded_is_preflight_error_even_for_the_repair_probe(
    monkeypatch,
):
    """Not a refusal and not a failed repair: nothing could be judged, so the
    caller is told, whichever of the two reloads fails."""
    w = _world()
    retry = attempt(
        "accept", _id(w.proposal), actor=w.human, reason="r", authorization_basis="",
    )
    assert judge(w.system, retry).outcome is RETRY
    real_load = CCCStore.load.__func__
    for failing_call in (1, 2):  # the attempt's own copy, then the probe's
        calls = []

        def flaky(cls, path, calls=calls, failing_call=failing_call):
            calls.append(path)
            if len(calls) == failing_call:
                raise OSError("the snapshot went away")
            return real_load(cls, path)

        monkeypatch.setattr(CCCStore, "load", classmethod(flaky))
        with pytest.raises(PreflightError) as caught:
            judge(w.system, retry)
        assert isinstance(caught.value.__cause__, OSError)
        assert len(calls) == failing_call
        assert not issubclass(PreflightError, (TypeError, ValueError, CCCError, KeyError))


def test_a_store_too_deep_to_snapshot_is_preflight_error_not_a_recursion_error():
    w = _world()
    w.system.ingest("deeply nested", actor=w.human, metadata={"deep": _nested(2000)})
    att = attempt(
        "accept", _id(w.proposal), actor=w.human, reason="r", authorization_basis="b",
    )
    with pytest.raises(PreflightError):
        judge(w.system, att)


def test_a_malformed_attempt_is_a_caller_error_not_a_verdict():
    with pytest.raises(TypeError):
        attempt("accept")  # required arguments missing
    with pytest.raises(TypeError):
        attempt("accept", "artifact_x", actor=Actor.human("h"), reason="r",
                authorization_basis="b", no_such_argument=1)
    for name in ("save", "load", "derive", "infer", "record", "resolve", "no_such_method", ""):
        with pytest.raises(ValueError):
            attempt(name)


def test_the_enum_arguments_digest_as_their_values():
    human = Actor.human("h")
    att = attempt(
        "classify", "artifact_x", EpistemicStatus.EVIDENCE, actor=human, reason="r",
    )
    assert att.content["arguments"]["status"] == "EVIDENCE"


# The gate and the chain.


def test_a_ccc_gate_satisfies_the_cns_gate_protocol():
    gate = CccGate(CCCSystem())
    assert isinstance(gate, cns_gate.Gate)
    assert gate.name == GATE_NAME
    assert gate.position is cns_gate.GatePosition.ALPHA


def test_a_ccc_gate_refuses_a_candidate_that_is_not_an_attempt():
    gate = CccGate(CCCSystem())
    for candidate in ("accept", {"operation": "accept"}, None, b"bytes"):
        with pytest.raises(TypeError):
            gate.check(candidate)


def test_a_ccc_gate_judges_the_same_way_as_judge():
    w = _world()
    gate = CccGate(w.system)
    for _, make, _, _ in SCENARIOS:
        att = make(w)
        assert gate.check(att) == judge(w.system, att)


def test_the_chain_is_admission_only_and_says_so():
    chain = cns_chain(CCCSystem())
    assert chain.misplaced() == ()
    assert len(chain.alpha) == 1
    assert chain.omega == ()
    assert chain.complete() is False  # CCC judges admission, not a produced result


def test_the_chain_runs_through_cns_resolution():
    w = _world()
    chain = cns_chain(w.system)
    (gate,) = chain.alpha
    admitted = gate.check(attempt(
        "accept", _id(w.proposal), actor=w.human, reason="reviewed",
        authorization_basis="explicit human adoption", evidence_ids=(_id(w.fact),),
    ))
    gated = gate.check(attempt(
        "accept", _id(w.proposal), actor=w.human, reason="reviewed",
        authorization_basis="",
    ))
    blocked = gate.check(attempt(
        "classify", _id(w.simulation), HIST, actor=w.human, reason="relabel",
    ))
    assert admitted.outcome is PASS
    assert gated.outcome is RETRY
    assert blocked.outcome is BREACH
    assert cns_gate.resolve([admitted]) is PASS
    assert cns_gate.resolve([admitted, gated]) is RETRY
    assert cns_gate.resolve([admitted, gated, blocked]) is BREACH
    assert cns_gate.unbound([admitted, gated, blocked]) == ()


def test_the_connector_is_the_one_place_that_needs_cns():
    assert issubclass(CnsNotInstalled, ImportError)
