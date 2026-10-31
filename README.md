# CCC: Cognitive Continuity Constitution

Dependency-free **memory of claims over time** that keeps a machine from rewriting what a human actually thought: who originated each claim, human-only promotion to fact, and a human-only erase operation (not yet grounded in the ≡TACK Constitution; see section 4). Optional pack for [`observe-perceive`](https://github.com/wking53214/observe-perceive). Not a standalone product. Test counts are under Release and test status in section 4; CI runs every one of them (section 8 explains the two CI jobs).

## 1. Role in the STACK spine

**Purpose.** CCC is a store of claims over time with a rulebook in front of it. It records who originated each claim (a human, a model, a system or an external source), what epistemic status the claim holds (unknown, evidence, inference, historical, theory and so on), what it rests on, and what later replaced, corrected or erased it. The rules refuse the moves that would let a machine rewrite what a human thought: a model cannot hold human authority, machine consensus cannot become human-established fact, and only a named human can promote, erase or resolve.

**Responsibilities (what CCC itself decides).**
- Whether an attempted transition on its own store is constitutional (`ccc/constitutional_rules.py`, 20 identified rules, each decision audited).
- Provenance and epistemic status of each record, and the evidence links under it (`provenance.py`, `evidence.py`, `epistemic_state.py`).
- History that is never silently overwritten: correction, amendment, supersession, redaction and erasure leave edges and tombstones (`lineage.py`). Negative findings are preserved (rule `CCC-HISTORY-003`).
- Recurrence of machine findings over time (anomaly, pattern, mandate), where only a human can set a mandate (`discovery.py`, `recurring.py`).
- Answering one read-only question for a consumer: was this exact machine output recorded here, and in what state (`ccc/record_status.py`).

**Inputs and outputs.**

| In | Out |
|---|---|
| Calls on `CCCSystem` carrying an `Actor`, content, evidence ids and (for human acts) an `authorization_basis` | An immutable `Artifact` or event, a `RuleDecision` in the audit trail, or a `ConstitutionViolation` raised before any record changes |
| An optional `write_permission` callable the application supplies | `WritePermissionRefused` if it answers anything but `True` |
| An optional `human_verifier` callable the application supplies | `HumanVerificationRefused` if it answers anything but `True` |
| A JSON snapshot (`CCCStore.save` / `load`) | The same store back, including the audit trail |
| A `(source, candidate_id, text_digest)` triple | One word from `MachineRecords.status`: `held`, `absent`, `altered`, `erased`, `redacted`, `rejected`, `superseded` or `unattested` |

**Where it sits.** In the evidence spine CCC is the last hop. A document is read and its claims extracted by [HERALD](https://github.com/wking53214/HERALD), recorded as evidence by [TIE](https://github.com/wking53214/TIE), judged as a root artifact by [Conservation_Kernel](https://github.com/wking53214/Conservation_Kernel), judged again at its admission door by [Governance_Gateway](https://github.com/wking53214/Governance_Gateway), and then CCC judges the attempt to take it into its store. The orchestration lives in [CNS](https://github.com/wking53214/CNS) (`chains/evidence_spine.py`), not here.

```text
 document
    |
 HERALD ---> TIE ---> Conservation_Kernel ---> Governance_Gateway ---> CCC store
 (claims)   (evidence)   (root artifact)         (admission door)       ^   |
                                                                        |   | MachineRecords.status
        CNS: roster, same-document check,                               |   v
        one-use permission  -------- write_permission ------------------+  consumers (CNS, Link)
```

CCC appears in that chain only through two optional seams (sections 7 and 8). Nothing in the spine requires CCC for the other four seats to work.

**Companions.**
- [CNS](https://github.com/wking53214/CNS): holds the shapes of a decision (gate result, `PASS` / `RETRY` / `TERMINAL_BREACH`) and the spine script. CCC optionally expresses its own refusals in those shapes (`ccc/cns_connector.py`). CNS supplies the `write_permission` that stands a roster decision in front of CCC's doors, and asks CCC for `MachineRecords.status`. CNS does not decide for CCC.
- [CCCb](https://github.com/wking53214/CCCb): CCC's text-matching library, split out of this repository. CCC imports nothing from it; the application passes `cccb.TextMatcher()` in as `text_matcher`. CCC keeps the rules, CCCb keeps the measurement.
- [Link](https://github.com/wking53214/Link): imports `ccc` (`link/admission.py:16-17`) to hand Triad-42 session output to a real `CCCSystem` and read it back through `MachineRecords`. CCC does not know Link exists.
- [HERALD](https://github.com/wking53214/HERALD), [TIE](https://github.com/wking53214/TIE), [Conservation_Kernel](https://github.com/wking53214/Conservation_Kernel), [Governance_Gateway](https://github.com/wking53214/Governance_Gateway): no import in either direction. They reach CCC only through the spine script or an application that wires them.
- [observe-perceive](https://github.com/wking53214/observe-perceive): `orchestrator_ccc_adapter.py` there imports `ccc` lazily (line 53) and `cccb` (line 72). CCC does not import it.

**Owns.** Its store, its rulebook, its audit trail, the human-only operations, the guard on private sources, the record lookup that answers CNS, and the two hooks an application attaches (`write_permission`, `human_verifier`).

**Does not own.**
- Whether content is true. CCC records a claim's standing, it does not check the claim.
- Permission to act. Nothing here authorizes or executes anything.
- The decision a CNS roster makes. CCC only refuses a write when the application's check says no.
- Who a human is. `Actor.human("anyone")` is a label; `human_verifier` is where an application checks it, and CCC holds no identity provider or key (`attestation_key` is supplied by the caller).
- The verification of a single transformation (Conservation_Kernel), the admission door (Governance_Gateway), the text measurement (CCCb), and the signed-message protocol UAI-1 (see below).

**Four layers, kept apart.** CNS moves objects, a participant or model may recommend, the responsible system decides, and the receiver's own policy permits. CCC is a responsible system for its own store and a receiver of writes. A model's recommendation to CCC is never an admission: it is refused unless the application's own `write_permission` says yes, and a human act is refused unless a human actor supplies the basis the rules ask for.

**CNS interaction: status.**

| Seam | Status | Evidence |
|---|---|---|
| Gate connector: an attempted transition becomes a CNS `GateResult` at position `ALPHA` | implemented, optional, ALPHA only | `ccc/cns_connector.py:282` (lazy `importlib.import_module("cns.gate")`), `:540` (`GatePosition.ALPHA`), `:643` (`CccGate`), `:705` (`cns_chain`); tests `tests/test_cns_connector.py` |
| Write permission: a CNS decision stands in front of the machine-side doors | implemented on CCC's side, needs no CNS import | `ccc/permission.py`, `ccc/system.py:51-` (`_asks_permission`), doors at `ccc/system.py:673-1048`; `tests/test_write_permission*.py`, `tests/test_write_funnel.py` |
| Record lookup CNS asks ("no CCC record, no use") | implemented on CCC's side, needs no CNS import; consumer side is in CNS | `ccc/record_status.py:189-235` here, `cns_composition/ccc_admission.py:172` in CNS |
| UAI-1 signed messages for systems outside a process | absent: no `uai` or `cns_interop` reference anywhere in `ccc/` or `pyproject.toml` | grep over `ccc/` and `pyproject.toml` |
| `cns_composition` or `cns_interop` imports | absent: CCC imports neither | grep of `import` lines in `ccc/` |

The connector has no outcome end by design: `cns_chain(system).complete()` is `False`. CCC is judged at the ALPHA gate only.

**Maturity and limits (measured 2026-10-31 on `origin/main` at `f6e33da`).**
- With the local sibling checkouts on the path (CNS at v2.3.0 plus 59 later commits, CCCb at `e2b1af0`): 1196 passed, 1 xfailed.
- With CNS hidden and CCCb present: 658 passed, 3 skipped, 1 xfailed. The 3 skips are the connected modules (`test_cns_connector.py`, `test_cns_write_permission_presence.py`, `test_write_request_digest.py`), which CI runs with `CCC_REQUIRE_CNS=1` so they cannot skip there.
- Without CCCb, 7 test modules fail at import (`test_external_finding`, `test_recurrence`, `test_recurring_groups`, `test_semantic`, `test_semantic_hardening`, `test_text_matching`, `test_write_permission_doors`): they need the `match` extra.
- Not re-measured on 2026-10-31: the CI runs on Python 3.11 and 3.12 (these runs used 3.13), and the end-to-end spine result recorded in CNS.
- Version 0.1.0, no tag or release. A system built without `write_permission` or `human_verifier` is not stopped, and nothing can see that from outside. Anyone holding `system.store` can write around both. Continuity across processes depends on the persistence the caller supplies.

## 2. Full System Scope & Architectural Depth

Executable constitutional model for AI continuity: provenance, epistemic status, human authority, and state carried forward in time. Distinguishes accumulation, interpretation, modification, and authority so a later claim can be checked against earlier ones (recurrence, contradiction, silent promotion).

Package `ccc/` + `tests/`. Stdlib only. Adapter after orchestrator decision; skip-if-absent.

## 3. What It Does NOT Do / Non-Goals

- Does not authorize or execute.
- Does not replace Conservation Kernel verification of a single transformation.
- Does not replace a ticket DB or vector search as a product.

## 4. Brutally Honest Current Status & Gaps

Commercial red team: **FEATURE** (recurrence detection; the measurement now lives in [CCCb](https://github.com/wking53214/CCCb), the guard stays here). Unfrozen 2026-09-11; findings not superseded. One xfail historically. Continuity across *processes* still depends on whatever persistence the adapter is given, not a distributed store. Human-sovereignty rules are code invariants in this package, not an identity provider.

Decisions on the constitution's text are kept in [`decisions/`](decisions/). [DEC-0002](decisions/DEC-0002_v1.md) (v1.1 draft, decided provision by provision) leaves Articles I.G, III.F, XI.A, XII.E, XV.A and XVII.A-D UNRESOLVED; I.G and XVII.A-D are nonetheless enforced in this package's code.
**Erasure is only partly grounded.** `CCCSystem.erase` lets a human, with a stated basis, wipe a record's text and leave a tombstone; anything built on it is downgraded to `THEORY`. The ≡TACK Constitution v4.0 (Developed Candidate, wking53214/constitution) contains no human right of erasure, and most CCC rules are sourced to the build directive, not to an article. Article XVIII does bear on it: it requires negative findings to be preserved. Rule `CCC-HISTORY-003`, the one rule sourced to an article, makes `erase` and `redact` refuse a negative finding: a record the human rejected, a record material to a conflict (open or resolved), or a record with a `CONTRADICTS` edge. Change course by superseding it. That covers what CCC can see; it does not cover every kind of non-confirmed claim. Erasing an ordinary record is still unratified mechanism, and whether to add an erasure article to the Constitution is the owner's decision.
New records start from [`DEC-TEMPLATE_v1.md`](decisions/DEC-TEMPLATE_v1.md). `CCCSystem.decide` can store the same shape with a decision: the options considered, the one selected, each other option rejected with a reason or deferred (every option not selected must be one or the other), and the assumptions it rests on. A decision recorded without them is stored exactly as before.

### Release and test status

Measured 2026-10-31 at main `f6e33da` (section 1 has the commands and conditions).

| What | State |
|---|---|
| Version | 0.1.0 (`pyproject.toml`, `CCCSystem.version`, and the constitutional rules) |
| Tag and GitHub Release | None yet. Tagging is the owner's decision. |
| CI on main | Green |
| Tests | 1196 passed and 1 xfailed with CNS and CCCb available; 658 passed, 3 skipped and 1 xfailed with CNS hidden (parametrized cases counted) |
| Pins | The optional `cns` extra is pinned to the tag v2.3.0 (`pyproject.toml`; the comment above it there still says v2.2.0). The `match` extra pins `cccb` to commit `8e3c779`. |
| Write permission | Eleven machine-side doors ask the application's `write_permission` first (listed in section 8). The human operations never ask it; they ask the application's `human_verifier`, if one is given. |

## 5. Core Invariants & Guarantees

Fail-closed on unconstitutional promotions (AI→human authority conversion is in the GEMS/CCC shared doctrine). Recurrence is explicit. Stdlib-only so the suite runs with no sibling.

## 6. Inputs, Outputs & Type Contracts

**Recurring groups are listed, read-only.** `CCCSystem.recurring_groups()` lists the groups of linked machine findings CCC has recorded, most serious first: each group's stage, independent occurrences, re-observed duplicates, first and last dates, and `needs_human_review` (a PATTERN with three or more occurrences, the point where CCC raises REPEATED_RETURN road signs). It reads the same links `record_external_finding` writes, so it cannot disagree with CCC's own ladder, and it writes nothing.

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

**Words shared with Triad-42, different meanings.** "Anomaly / pattern /
mandate" here counts sightings over time, and a mandate is a requirement only a
human may set; in Triad-42 the same words grade findings within one review, and
a "mandate" only obliges the reviewer to look. No shared code. See the
docstring of `ccc/discovery.py`. (CCC's "42" dialogue loop, the other shared
word, is buried; see below.)

**Buried record types.** Turning points (inflection), threads and branches,
simulations, official terms (canonicalization) and the confirm/refine/42
dialogue loop were removed on 2026-10-06: nothing in ≡TACK used them and no
article of the ≡TACK Constitution v4.0 (Developed Candidate) requires CCC to
hold them. They are in wking53214/Graveyard,
`ccc/2026-10-06-unused-record-types/`, with how to revive them. Conflicts and
human resolution of open questions stay: Articles XLV, XLVI and LVI require
conflicts to be preserved until a human resolves them. State files that hold
the buried sections still load, and those sections are written back unchanged
(`ccc.store.RETIRED_SECTIONS`). Artifacts keep their `thread_id` and
`branch_id` fields as plain labels.

**Private sources are the caller's statement.** CCC names no repositories. The
application that records machine findings states which sources are private:
`CCCSystem(private_source_markers=(...))`, matched as substrings of each
finding's `source_material`. A finding citing one is refused unless
`allow_private_source=True`. Until the list is stated, every machine finding is
refused (`ccc.errors.PrivateSourcesNotStated`); an empty list states there are
none. That way the guard cannot be lost by forgetting to configure it.


The adapter that feeds CCC from the gate is `orchestrator_ccc_adapter.py` in observe-perceive; it imports `ccc` itself, CCC does not import it.

## 7. Stack Integration Topology

```text
observe-perceive decision -> orchestrator_ccc_adapter -> CCC (optional)
Link: Triad-42 session -> admit_session -> CCC + MachineRecords
CNS spine: HERALD -> TIE -> Conservation_Kernel -> Governance_Gateway -> CCC (write_permission, CccGate)
```

The detail of the spine is in section 1. How CCC is the last hop: the document goes into its store only if the roster allows it. With the roster's guard as its `write_permission`, a direct `ingest` after a roster no is refused, and an approved decision opens `ingest` and `record` once, for the one document it judged. The other doors that ask the permission carry a conclusion, a finding, an observation, a link or a relationship that no seat judges, so under that permission they stay refused after any decision. CNS's spine script (`chains/evidence_spine.py`) names the doors it expects CCC to gate and goes red if CCC gates one it does not name. The 30-result, one-recorded-GAP figure that script reported on 2026-10-30 is CNS's measurement; it was not re-run for this README.

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

The judged transitions are `ccc.cns_connector.TRANSITIONS` (18 operations: those
that move material toward human authority, promote an epistemic status, rewrite
history, or resolve something that belongs to a human). Left out, on purpose:
`derive` (it ingests first and attaches evidence second, so a refusal can follow
a change), the aliases `record`, `infer` and `interpret`, the `resolve`
dispatcher (its three targets are judged directly), and the operations that only
record something new (`detect_conflict`, `ask`, road signs). `attempt()` raises `ValueError`
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
CCC changes. CI runs two jobs per Python version. **Without CNS** proves CCC stands alone:
the connected test module (`tests/test_cns_connector.py`) skips there by design.
**With CNS** installs the pinned `[cns]` extra and sets `CCC_REQUIRE_CNS=1`, so
the connected module runs, and a missing CNS fails the build instead of
skipping it. The independence tests run in both and never skip.

### Letting an application stand a decision in front of new records (`write_permission`)

CCC's own `ingest` used to ask nobody, so a decision made elsewhere (a CNS roster saying no) could be
sidestepped by calling it directly. `CCCSystem(write_permission=check)` closes that, and needs no CNS: `check` is
any callable the application supplies. `ingest`, `record`, `derive`, `infer`, `interpret`,
`record_external_finding`, `discover`, `detect_road_sign`, `record_road_sign`, `attach_evidence` and `relate` each call it once,
first, with a `ccc.permission.WriteRequest` (the method name and the caller's arguments, deep-copied, with no
defaults filled in), and go on only if it returns exactly `True`. Anything else, an error from the check
included, raises `WritePermissionRefused` before CCC touches its store, its rules or its audit trail.

Only those eleven ask, and each asks once (the private `_ingest` and `_derive`, and the discovery and road sign managers reached as `system.discovery` and `system.road_signs`, ask at the same doors): `interpret` calls `derive`, which writes the record, and the nested
calls do not ask again, because a one-use permission would be spent by the first yes. `record_road_sign` is the
same act as `detect_road_sign`, and `discover` is the bare way to create what `record_external_finding` creates
under stricter rules, so each of those asks too, or the gate would be one call away from useless. The road
signs and stage moves that `record_external_finding` makes as part of its own work happen under its one ask.
`decide`, `correct`, `amend`, `supersede`, `accept`, `reject`, `redact`, `erase` and the rest never ask this check, so a
human's action is not held up by a machine's roster. They ask `human_verifier` instead (`ccc/human_auth.py`): an optional
callable that gets a `HumanRequest` and must answer exactly `True`, else `HumanVerificationRefused` is raised before anything
is written. It is not saved with the store, and with none configured nothing changes. The permission is asked first, so a yes can be spent on a
call that CCC's own rules then refuse; that fails closed, and the caller needs a new permission.

Left open by this check on purpose: `adopt_discovery`, `advance_discovery`, `link_road_sign` and `record_resolution` change a
record that already exists (all but `link_road_sign` ask `human_verifier`, `advance_discovery` only for a MANDATE advance), and `detect_conflict` and `ask` create a flag or a
question, not a finding or a record of material.

Limits: a system built without a check is not stopped, and nothing here can see that. Anyone holding the
system's `store` can also write to it directly, which no check can see. The check is not saved
with the store, so a reloaded system or the connector's scratch copy has none unless given one. Tests:
`tests/test_write_permission.py`, `tests/test_write_permission_doors.py` and `tests/test_write_funnel.py` (which also sweeps for a public method added without a decision about which kind it is).

### Answering CNS's record lookup (`ccc.record_status`)

A second, separate service for CNS, and it needs no CNS at all. Rule 2 of the
Triad governance design is "no CCC record, no use": before CNS lets Triad output
into a decision path, it asks CCC whether that exact output was recorded. CNS asks;
only CCC reads its own store to answer. `MachineRecords(system).status(source,
candidate_id, text_digest)` answers `held`, `absent`, `altered`, `erased`,
`redacted`, `rejected`, `superseded` or (with a key, below) `unattested`. Only records
created by the named machine actor count, and the fingerprint is recomputed from the
stored text. A human erasure or redaction wins over every other copy, and follows the
text as well as the id: the same text handed in again under a new candidate id is still
`erased` or `redacted`. Text a human rejected answers `rejected`, and text with a
successor answers `superseded`, under any id. It is a read: no record, audit event or rule
decision is written. Tests: `tests/test_record_status.py`, which run in CI.

**Who wrote the record.** Without a key, "created by the machine actor" means only that
the record says so: anyone who can call `ingest`, add to the store or edit a saved state
file can write a record that answers `held`. Pass `attestation_key` (bytes, at least 16,
supplied by the caller; CCC holds no key) to `MachineRecords` and to the handoff, and only
records carrying the handoff's HMAC stamp (`ccc.record_status.attest`, over the source, the
candidate id and the fingerprint of the stored text) count. A record with no valid stamp
is never `held`; if no matching record is stamped the answer is `unattested`. With no key
the answer is exactly as unauthenticated as before, and records written before a key was
in use carry no stamp, so they need to be handed off again to be counted.
Tests: `tests/test_record_attestation.py`.
