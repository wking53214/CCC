# CCC — Cognitive Continuity Constitution

Dependency-free **memory of claims over time** that keeps a machine from rewriting what a human actually thought: who originated each claim, human-only promotion to fact, and the human's right to erase. Optional pack for [`observe-perceive`](https://github.com/wking53214/observe-perceive). Not a standalone product. 213 test functions measured in this tree (README previously approximated ~135–142).

## 1. Pipeline Position & Role

**OPTIONAL AUDIT/MEMORY** after a decision. The gate records into CCC through `orchestrator_ccc_adapter.py`. Nothing in the gate requires it.

Related epistemic posture: [`Conservation_Kernel`](https://github.com/wking53214/Conservation_Kernel). Complementary extraction target: [`HERALD`](https://github.com/wking53214/HERALD) (claims from documents).

## 2. Full System Scope & Architectural Depth

Executable constitutional model for AI continuity: provenance, epistemic status, human authority, and state carried forward in time. Distinguishes accumulation, interpretation, modification, and authority so a later claim can be checked against earlier ones (recurrence, contradiction, silent promotion).

Package `ccc/` + `tests/`. Stdlib only. Adapter after orchestrator decision; skip-if-absent.

## 3. What It Does NOT Do / Non-Goals

- Does not authorize or execute.
- Does not replace Conservation Kernel verification of a single transformation.
- Does not replace a ticket DB or vector search as a product.

## 4. Brutally Honest Current Status & Gaps

Commercial red team: **FEATURE** (recurrence detection; the measurement now lives in [CCCb](https://github.com/wking53214/CCCb), the guard stays here). Unfrozen 2026-09-11; findings not superseded. One xfail historically. Continuity across *processes* still depends on whatever persistence the adapter is given — not a distributed store. Human-sovereignty rules are code invariants in this package, not an identity provider.

## 5. Core Invariants & Guarantees

Fail-closed on unconstitutional promotions (AI→human authority conversion is in the GEMS/CCC shared doctrine). Recurrence is explicit. Stdlib-only so the suite runs with no sibling.

## 6. Inputs, Outputs & Type Contracts

**Text matching is plugged in, not built in.** Deciding whether a machine
finding is a re-submission or a recurrence of an earlier one needs a
measurement of how alike two texts are. That measurement lives in
[CCCb](https://github.com/wking53214/CCCb) (split out of this repo at
`d039efd`) and plugs in the way Ecology's semantic provider does:
`CCCSystem(text_matcher=cccb.TextMatcher())`. CCC keeps the rules: a
re-observation is linked and never counted as an occurrence, and a machine may
raise an anomaly to a pattern but never to a mandate. Without a matcher,
`record_external_finding` refuses loudly; nothing else in CCC needs one. CCC
imports nothing from CCCb (`ccc/text_matching.py`, `tests/test_text_matching.py`).
Install for development and tests: `pip install -e '.[dev,match]'`.

**Private sources are the caller's statement.** CCC names no repositories. The
application that records machine findings states which sources are private:
`CCCSystem(private_source_markers=(...))`, matched as substrings of each
finding's `source_material`. A finding citing one is refused unless
`allow_private_source=True`. Until the list is stated, every machine finding is
refused (`ccc.errors.PrivateSourcesNotStated`); an empty list states there are
none. That way the guard cannot be lost by forgetting to configure it.


Adapter in observe-perceive. Extra pin: `cognitive-continuity-constitution @ git+…/CCC@2cf7aa19`. Ecology duck-types a FindingRecord toward CCC (`finding.py`) without importing this package.

## 7. Stack Integration Topology

```text
observe-perceive decision → orchestrator_ccc_adapter → CCC (opt)
HERALD / TIE / Ecology may feed claim-like records; no hard imports
```

Apache-2.0.

## 8. Connecting to CNS (optional)

CCC stands alone: no runtime dependency, nothing imported from CNS when the
package loads, and the whole suite passes without CNS installed. If CNS is
present, `ccc.cns_connector` expresses an attempted transition as a CNS gate
result, so it can be resolved alongside gates from other repositories.

```bash
pip install -e '.[cns]'      # from a checkout
```

```python
from ccc import Actor, CCCSystem
from ccc.cns_connector import CccGate, attempt

system = CCCSystem()
proposal = system.derive("a machine inference", actor=Actor.model("m"))
gate = CccGate(system)

by_model = gate.check(attempt(
    "accept", proposal.artifact_id, actor=Actor.model("m"),
    reason="consensus", authorization_basis="machine consensus",
))
by_model.outcome   # TERMINAL_BREACH: a model attempting human authority is blocked

by_human = gate.check(attempt(
    "accept", proposal.artifact_id, actor=Actor.human("h"),
    reason="reviewed", authorization_basis="",
))
by_human.outcome   # RETRY: supply the authorization basis and this call is admitted
by_human.reason    # "CCC-PROVENANCE-002: user provenance requires ..."
```

`check` runs the attempt on a scratch copy of the store (CCC's own JSON
snapshot round trip), so the live system, its audit trail and its rule
decisions are left exactly as they were. The real operation still enforces the
same rules inline when you perform it; the connector never replaces that, and a
test proves it does not change what CCC decides.

| CCC | CNS |
|---|---|
| where it judges | `ALPHA`: the judged transitions evaluate their rules before they change any record, so a refusal means the transition never starts (a test checks that a refusal changes no record). CCC has no outcome end, so `cns_chain(system).complete()` is `False` by design. `validate_constitution()` is a read-only report that gates nothing, and is not mapped. |
| the attempt is admitted (the call returns) | `PASS` |
| `ConstitutionViolation` that a human supplying what it asks for would get admitted (checked, see below) | `RETRY` |
| any other `ConstitutionViolation`: a model, system or external actor attempting a human-only operation (CCC's own "blocked"), or a refusal no human input reaches (erased material, machine consensus promoted to human-established fact, a simulation promoted to history, a claim attached to itself) | `TERMINAL_BREACH` |
| `InvalidTransition`, `NotFound`, `ValueError`, `KeyError` | `TERMINAL_BREACH` |
| any other exception | not translated, it propagates: never a `PASS` |
| `reason` | CCC's own text, `"<rule_id>: <reason>"` |
| judged content | `subject` label (default the operation name) plus `subject_digest` of the attempted call: the operation and every argument, bound to the real signature with defaults applied |

**How `RETRY` is decided.** Not from a rule's name or from the prose of its
registry entry. After a refusal, the connector runs the same operation, by the
same actor, on the same target, again on a second scratch copy, with only the
human inputs CCC's rules ask for added: a non-empty `authorization_basis`,
`human_event=True` where the operation takes one, and a human-established
record standing as the evidence root (as `evidence_ids`, as `source_material`,
and for `classify` attached to the artifact). If CCC admits that call the
verdict is `RETRY`; otherwise it is `TERMINAL_BREACH`, including when CCC cannot
run the call at all even with those inputs added (an argument of the wrong type).
The probe never changes the actor, so a model that attempts a human-only
operation is blocked whatever it adds, and the human who could do it is a
different actor making a different call, with a verdict of their own. The
stand-in root exists on the scratch copy only; `RETRY` says a human-established
record in that role would be enough, and a real human has to have or make one.

The judged transitions are `ccc.cns_connector.TRANSITIONS` (22 operations: those
that move material toward human authority, promote an epistemic status, rewrite
history, or resolve something that belongs to a human). Left out, on purpose:
`derive` (it ingests first and attaches evidence second, so a refusal can follow
a change), the aliases `record`, `infer` and `interpret`, the `resolve`
dispatcher (its three targets are judged directly), and the operations that only
record something new (`detect_conflict`, `detect_inflection`, `ask`, `simulate`,
`propose_term`, road signs, threads, branches). `attempt()` raises `ValueError`
for anything outside the set.

The digest binds the attempted call, not the store's state at the time. Arguments
must be strings, numbers, booleans, `None`, sequences and mappings of those, plus
`Actor` and enums. Anything else raises `TypeError` when the attempt is built,
rather than yielding an unbound verdict, and so does anything the digest could not
take later: NaN or an infinity, text with a lone surrogate, an integer wider than
2048 bits, and nesting (or a cycle) deeper than 64 containers. CCC itself accepts
some of these. An attempt keeps its own copy of its arguments; if a nested value is
changed afterwards, `judge` and `Attempt.run` raise `AttemptChanged` instead of
running something that was not digested.

Each check costs one snapshot of the store, O(store): a 5000-artifact store takes
about 1.5 to 2 seconds where the real operation takes about 0.2 milliseconds. The
snapshot is a JSON file of the whole store, live content included, written to a
private temporary directory (mode 0700) and removed when the check ends. A store
CCC cannot snapshot (metadata JSON cannot render, nesting too deep) cannot be
preflighted: `judge` raises `PreflightError`, which is neither a `ValueError` nor a
`TypeError`, so it cannot be mistaken for a refusal.

Without CNS installed, `judge`, `CccGate`, `cns_chain`, `attempt_digest` and
`to_cns_result` raise `CnsNotInstalled` (an `ImportError`) with the install command,
as does an installed CNS too old to bind verdicts to what they judged. `attempt`,
`Attempt.run`, `cns_available` and `TRANSITIONS` work either way, and nothing else in
CCC changes. CI installs only `pytest` and `ruff`, so the connected test module
(`tests/test_cns_connector.py`) skips there and runs wherever the extra is
installed; the independence tests run everywhere and never skip.

### Answering CNS's record lookup (`ccc.record_status`)

A second, separate service for CNS, and it needs no CNS at all. Rule 2 of the
Triad governance design is "no CCC record, no use": before CNS lets Triad output
into a decision path, it asks CCC whether that exact output was recorded. CNS asks;
only CCC reads its own store to answer. `MachineRecords(system).status(source,
candidate_id, text_digest)` answers `held`, `absent`, `altered`, `erased` or
`redacted`. Only records created by the named machine actor count, the fingerprint
is recomputed from the stored text, and a human erasure or redaction of any matching
record wins over every other copy. It is a read: no record, audit event or rule
decision is written. Tests: `tests/test_record_status.py`, which run in CI.
