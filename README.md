# CCC: Cognitive Continuity Constitution

**A zero-dependency core for recording claims over time.** CCC has no third-party core runtime dependencies. It records who originated each claim, its provenance and epistemic status, and the lineage that links it to earlier versions. At its public interfaces it enforces explicit human-authority rules: human-only promotion to fact, and a human-only erase operation (not yet grounded in the ≡TACK Constitution; see section 4). Applications can supply identity verification and write-permission controls. Both are optional, and direct access to the underlying store is outside their protection. CCC is a library, not a service or an app. It works on its own and is used by [Link](https://github.com/wking53214/Link), [observe-perceive](https://github.com/wking53214/observe-perceive) and [CNS](https://github.com/wking53214/CNS) (section 1). Test counts are under Release and test status in section 4; CI runs every one of them (section 8 explains the two CI jobs).

## In plain words

Think of CCC as a ledger of claims with a rulebook in front of it. You tell it who is saying something (a person, a model or a system) and what they claim. It keeps the claim, who said it, how well supported it is, and what later replaced or corrected it. If a model tries to pass its own guess off as something a human established, the rulebook refuses. CCC does not check whether a claim is true, and it does not check who a person really is unless your application gives it a way to. Terms are defined in the glossary near the end.

## Quick start

Install from a checkout (no third-party core runtime dependencies):

```bash
pip install -e .
```

Record a human statement and a machine inference, then look at what CCC kept:

```python
from ccc import Actor, CCCSystem

system = CCCSystem()
note = system.ingest("the meeting is on Tuesday", actor=Actor.human("william"))
guess = system.derive("probably moved to Wednesday", actor=Actor.model("assistant"))
print(note.provenance_status, guess.epistemic_status)
# PROVENANCE_UNCERTAIN INFERENCE
```

The human note is `PROVENANCE_UNCERTAIN` because no authorization basis was given (DEC-0003). The guess stays `INFERENCE`; a model cannot promote it. Human operations and the optional controls are covered in section 8.

## Limitations at a glance

- `Actor.human(...)` is a label. CCC holds no identity provider; identity is checked only if the application supplies a `human_verifier`.
- Write permission and `human_verifier` are optional. Without them, the facade does not ask.
- Direct access to `system.store` and the managers bypasses facade-level controls.
- The CNS connector evaluates a scratch copy. A PASS shows the rules admitted the call on that copy, not that the application authorized it.
- Persistence has no digest or version, and the store is not a tamper-evident ledger.

Full list, with status of each: section 4.

## Where this fits

CCC is the last stop of the evidence spine, one of the groups of repos in ≡TACK (≡TACK is the whole library of repos and the company). The spine is five repos that a document passes through in order: HERALD reads it and pulls out claims, TIE records the evidence, Conservation_Kernel judges the root artifact, Governance_Gateway judges the admission door, and CCC decides whether its store takes the document. CNS connects them and is not a sixth stage.

- **What CCC receives:** an attempted write from an application, which may carry a CNS decision in the form of a `write_permission`.
- **What CCC hands on:** one read-only answer, whether an exact machine output was recorded here and in what state, to consumers such as CNS and Link.
- **Shared, not owned by one chain:** Link, observe-perceive and CNS's spine script all use CCC, so it is shared infrastructure and not a stage that belongs to a single chain. Section 1 has the detail.

## CNS connection

- **This repo's side:** `ccc/cns_connector.py`. It is optional: nothing else in `ccc/` imports it, and without CNS only the functions that need CNS raise `CnsNotInstalled`.
- **CNS's side:** `cns_composition/ccc_admission.py` carries the record lookup (an ALPHA gate). CNS's spine script, `chains/evidence_spine.py`, uses this repo's `CccGate`.
- **List status:** two-way in CNS's connection list (`contracts/cns-links.json`, read at CNS `03eca66`). The list names `ccc_admission.py` as CNS's file for CCC.
- **Built:** yes. **Tested:** yes, `tests/test_cns_connector.py` runs in CI with CNS required. **Used by CCC's normal code path:** no. A `CCCSystem` never calls the connector by itself; an application or the CNS spine script has to wire it. Section 8 has the detail.

## 1. Role in the evidence spine of ≡TACK

**Purpose.** CCC is a store of claims over time with a rulebook in front of it. It records who originated each claim (a human, a model, a system or an external source), what epistemic status the claim holds (unknown, evidence, inference, historical, theory and so on), what it rests on, and what later replaced, corrected or erased it. The rules refuse the moves that would let a machine rewrite what a human thought: a model cannot hold human authority, machine consensus cannot become human-established fact, and only an actor labeled human can promote, erase or resolve. "Labeled human" is a classification, not an identity check: the caller supplies an authorization basis, and CCC verifies identity only if the application supplies a `human_verifier`.

**Responsibilities (what CCC itself decides).**
- Whether an attempted transition on its own store is constitutional (`ccc/constitutional_rules.py`, 21 identified rules, each decision audited).
- Provenance and epistemic status of each record, and the evidence links under it (`provenance.py`, `evidence.py`, `epistemic_state.py`).
- History that is never silently overwritten: correction, amendment, supersession, redaction and erasure leave edges and tombstones (`lineage.py`). Negative findings are preserved (rule `CCC-HISTORY-003`).
- Recurrence of machine findings over time (anomaly, pattern, mandate), where only a human can set a mandate (`discovery.py`, `recurring.py`).
- Answering one read-only question for a consumer: was this exact machine output recorded here, and in what state (`ccc/record_status.py`).

**Inputs and outputs.**

| In | Out |
|---|---|
| Calls on `CCCSystem` carrying an `Actor`, content, evidence ids and (for human acts) an `authorization_basis` | An immutable `Artifact` or event, a `RuleDecision` in the rule history (`store.rule_decisions`), an `AuditEvent` in the audit trail (`store.audit_events`) for a consequential operation, or a `ConstitutionViolation` raised before any record changes. The rule history and the audit trail are separate records. |
| An optional `write_permission` callable the application supplies | `WritePermissionRefused` if it answers anything but `True` |
| An optional `human_verifier` callable the application supplies | `HumanVerificationRefused` if it answers anything but `True` |
| A JSON snapshot (`CCCStore.save` / `load`) | The same store back, including the rule history and the audit trail |
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

**Gate positions.** A CNS gate sits at one of two ends of a decision. `ALPHA` runs before the work: if it fails, the work never starts. `OMEGA` runs on the produced result: if it fails, the result does not leave. CCC's connector is an `ALPHA` gate only. It judges an attempted change to the store before any record changes, so a refusal means the change never starts. CCC has no `OMEGA` gate, so the spine does not treat CCC as having an outcome check (`cns_chain(system).complete()` is `False`, as section 8 explains).

**Companions.**
- [CNS](https://github.com/wking53214/CNS): holds the shapes of a decision (gate result, `PASS` / `RETRY` / `TERMINAL_BREACH`) and the spine script. CCC optionally expresses its own refusals in those shapes (`ccc/cns_connector.py`). CNS supplies the `write_permission` that stands a roster decision in front of CCC's doors, and asks CCC for `MachineRecords.status`. CNS does not decide for CCC.
- [CCCb](https://github.com/wking53214/CCCb): CCC's text-matching library, split out of this repository. CCC imports nothing from it; the application passes `cccb.TextMatcher()` in as `text_matcher`. CCC keeps the rules, CCCb keeps the measurement.
- [Link](https://github.com/wking53214/Link): imports `ccc` (`link/admission.py:16-17`) to hand Triad-42 session output to a real `CCCSystem` and read it back through `MachineRecords`. CCC does not know Link exists.
- [HERALD](https://github.com/wking53214/HERALD), [TIE](https://github.com/wking53214/TIE), [Conservation_Kernel](https://github.com/wking53214/Conservation_Kernel), [Governance_Gateway](https://github.com/wking53214/Governance_Gateway): no import in either direction. They reach CCC only through the spine script or an application that wires them.
- [observe-perceive](https://github.com/wking53214/observe-perceive): `orchestrator_ccc_adapter.py` there imports `ccc` lazily (line 53) and `cccb` (line 72). CCC does not import it. The same repo also imports `ccc` from three tests and one example file.

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
| Write permission: a CNS decision stands in front of the machine-side doors | implemented on CCC's side, needs no CNS import | `ccc/permission.py`, `ccc/system.py:51-` (`_asks_permission`), doors at `ccc/system.py:676-1048`; `tests/test_write_permission*.py`, `tests/test_write_funnel.py` |
| Record lookup CNS asks ("no CCC record, no use") | implemented on CCC's side, needs no CNS import; consumer side is in CNS | `ccc/record_status.py:191-235` here, `cns_composition/ccc_admission.py:172` in CNS |
| UAI-1 signed messages for systems outside a process | absent: no `uai` or `cns_interop` reference anywhere in `ccc/` or `pyproject.toml` | grep over `ccc/` and `pyproject.toml` |
| `cns_composition` or `cns_interop` imports | absent: CCC imports neither | grep of `import` lines in `ccc/` |

The connector has no outcome end by design: `cns_chain(system).complete()` is `False`. CCC is judged at the ALPHA gate only.

**Maturity and limits (first measured 2026-10-31 on `origin/main` at `f6e33da`; re-measured 2026-11-04 on main `7d64471` plus the RACE hardening changes; re-measured 2026-11-07 on main `6f80792`).**
- Pinned dependencies installed from their git URLs (CNS tag v2.3.0 = `41592fb`, CCCb `737cf0e`), with `pip install -e .` run first. The 2026-11-07 run used Python 3.13 (CI itself runs 3.11 and 3.12): with CNS, 1341 passed and 7 xfailed; with CNS absent, 776 passed, 4 skipped and 7 xfailed. The `pip install -e .` step matters: some tests start a subprocess in isolated mode, which cannot import `ccc` unless the package is installed. Without it, three tests fail for that reason alone. The 4 skips are the connected modules, which CI runs with `CCC_REQUIRE_CNS=1` so they cannot skip there. `ruff==0.15.22` is clean. The 7 xfails are strict statements of known limits (see "Authority, the matcher and the known limits" in section 7).
- With CCCb not installed, the 10 test modules that need the `match` extra are left out of the run (`tests/conftest.py`), and the run header says how many (`test_determinism`, `test_evidence_integrity_persistence`, `test_external_finding`, `test_matcher_boundary`, `test_recurrence`, `test_recurring_groups`, `test_semantic`, `test_semantic_hardening`, `test_text_matching`, `test_write_permission_doors`). The other 510 tests pass with 4 skipped (measured 2026-11-10 on `f3ce7a3`, Python 3.13).
- Not measured: GitHub Actions itself (only its commands, run locally), and the end-to-end spine result recorded in CNS.
- Version 0.1.0, no tag or release. A system built without `write_permission` or `human_verifier` is not stopped, and nothing can see that from outside. Anyone holding `system.store` can write around both. Continuity across processes depends on the persistence the caller supplies.

## 2. Full System Scope & Architectural Depth

Executable constitutional model for AI continuity: provenance, epistemic status, human authority, and state carried forward in time. Distinguishes accumulation, interpretation, modification, and authority so a later claim can be checked against earlier ones (recurrence, contradiction, silent promotion).

The package is `ccc/` and its tests are in `tests/`. It imports nothing outside the Python standard library. Other repos connect to it from their side; CCC does not import them (section 1).

## 3. What It Does NOT Do / Non-Goals

- Does not authorize or execute.
- Does not replace Conservation Kernel verification of a single transformation.
- Does not replace a ticket DB or vector search as a product.
- Does not decide whether content is true or who a human is (see "Does not own" in section 1).

## 4. Brutally Honest Current Status & Gaps

Commercial red team: **FEATURE** (recurrence detection; the measurement now lives in [CCCb](https://github.com/wking53214/CCCb), the guard stays here). "Commercial red team", "FEATURE" and "Unfrozen 2026-09-11" are labels from the owner's review process. They are not defined in this repository and they are not test results; the tests are in the table below. One xfail historically. Continuity across *processes* still depends on whatever persistence the adapter is given, not a distributed store. Human-sovereignty rules are code invariants in this package, not an identity provider.

Decisions on the constitution's text are kept in [`decisions/`](decisions/). [DEC-0002](decisions/DEC-0002_v1.md) (v1.1 draft, decided provision by provision) leaves Articles I.G, III.F, XI.A, XII.E, XV.A and XVII.A-D UNRESOLVED; I.G and XVII.A-D are nonetheless enforced in this package's code.
**Metadata limits.** Metadata is frozen all the way down through its containers, so a stored record's nested values cannot be changed. Only text, numbers, booleans, enums, lists, sets and mappings are accepted: any other type (a bytearray, a custom object, a date) is refused when it is stored (`TypeError`), and so is metadata nested more than 64 containers deep, or cyclic (`ValueError`). A value that could not be saved never gets into the store.

**Erasure is only partly grounded.** `CCCSystem.erase` lets a human, with a stated basis, wipe a record's text and leave a tombstone; anything built on it is downgraded to `THEORY`. The ≡TACK Constitution v4.0 (Developed Candidate, wking53214/constitution) contains no human right of erasure, and most CCC rules are sourced to the build directive, not to an article. Article XVIII does bear on it: it requires negative findings to be preserved. Rule `CCC-HISTORY-003`, the one rule sourced to an article, makes `erase` and `redact` refuse a negative finding: a record the human rejected, a record material to a conflict (open or resolved), or a record with a `CONTRADICTS` edge. Change course by superseding it. That covers what CCC can see; it does not cover every kind of non-confirmed claim. Erasing an ordinary record is still unratified mechanism, and whether to add an erasure article to the Constitution is the owner's decision.
[DEC-0003](decisions/DEC-0003_v1.md) (2026-10-09) makes a human ingest with no stated authorization basis `PROVENANCE_UNCERTAIN` until a basis is given, rather than `USER_ESTABLISHED`. New records start from [`DEC-TEMPLATE_v1.md`](decisions/DEC-TEMPLATE_v1.md). `CCCSystem.decide` can store the same shape with a decision: the options considered, the one selected, each other option rejected with a reason or deferred (every option not selected must be one or the other), and the assumptions it rests on. A decision recorded without them is stored exactly as before.

### Release and test status

This table is the one place for test results. IMPLEMENTATION.md carries dated copies and points here.

Each measurement below is tied to the commit it was run on. Commands and conditions are in section 1.

| What | State |
|---|---|
| Version | 0.1.0 (`pyproject.toml`, `CCCSystem.version`, and the constitutional rules) |
| Tag and GitHub Release | None yet. Tagging is the owner's decision. |
| CI on main | GitHub Actions run [42645883603](https://github.com/wking53214/CCC/actions/runs/42645883603) on `f3ce7a3` (main after PR #70) succeeded in all four jobs (Python 3.11 and 3.12, with and without CNS). |
| Tests, with CNS | 1351 passed, 7 xfailed on `f3ce7a3` (local run 2026-11-10, Python 3.13, CCCb `737cf0e`, `CCC_REQUIRE_CNS=1`); the same count on `d84dfa1`. Earlier: 1341 passed, 7 xfailed on `6f80792`. |
| Tests, neither CNS nor CCCb | 510 passed, 4 skipped on `f3ce7a3` (local run 2026-11-10, Python 3.13). |
| Tests, without CNS | 776 passed, 4 skipped, 7 xfailed on `6f80792` only. Not re-measured on later commits. |
| CNS suite against CCC | 3019 passed, 0 skipped, run on 2026-11-07 against the CCC code that became `2fd993a` (CNS PR #121 branch). |
| Pins | The optional `cns` extra is pinned to the tag v3.0.0 (`pyproject.toml`). The `match` extra pins `cccb` to commit `737cf0e`. |
| Write permission | Eleven machine-side doors ask the application's `write_permission` first (listed in section 8). The human operations never ask it; they ask the application's `human_verifier`, if one is given. |

## 5. Core Invariants & Guarantees

CCC refuses, before any record changes, a model or machine consensus taking human authority (the rules are in `ccc/constitutional_rules.py`). Recurrence of machine findings is explicit, never silent. The package is stdlib-only, so its core suite runs with no sibling repo installed.

## 6. Inputs, Outputs & Type Contracts

**Recurring groups are listed, read-only.** `CCCSystem.recurring_groups()` lists the groups of linked machine findings CCC has recorded, most serious first: each group's stage, independent occurrences, re-observed duplicates, first and last dates, and `needs_human_review` (a PATTERN with three or more occurrences, the point where CCC raises REPEATED_RETURN road signs). It reads the same links `record_external_finding` writes, so it cannot disagree with CCC's own ladder, and it writes nothing.

**Text matching is plugged in, not built in.** Deciding whether a machine
finding is a re-submission or a recurrence of an earlier one needs a
measurement of how alike two texts are. That measurement lives in
[CCCb](https://github.com/wking53214/CCCb) (split out of this repo at
`9b111e5`) and plugs in the way Ecology's semantic provider does:
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

## 7. How the repos connect

```text
observe-perceive decision -> orchestrator_ccc_adapter -> CCC (optional)
Link: Triad-42 session -> admit_session -> CCC + MachineRecords
CNS spine: HERALD -> TIE -> Conservation_Kernel -> Governance_Gateway -> CCC (write_permission, CccGate)
```

The detail of the spine is in section 1. How CCC is the last hop: the document goes into its store only if the roster allows it. With the roster's guard as its `write_permission`, a direct `ingest` after a roster no is refused, and an approved decision opens `ingest` and `record` once, for the one document it judged. The other doors that ask the permission carry a conclusion, a finding, an observation, a link or a relationship that no seat judges, so under that permission they stay refused after any decision. CNS's spine script (`chains/evidence_spine.py`) names the doors it expects CCC to gate and goes red if the two sets differ in either direction: a door CCC gates that the spine does not name, or a door the spine names that CCC does not gate. CNS's script was reported to give 56 results (52 scenarios plus 4 checks) with 3 recorded GAPs on 2026-11-07 (in the TIE README) and again on 2026-11-08 (in the Conservation_Kernel README). These are CNS-side measurements, quoted here and not re-run for this README. The earlier 30-result, one-GAP figure of 2026-10-30 is superseded.


### Authority, the matcher and the known limits

Three packages, three jobs. **CCC decides**: what is accepted, what a duplicate or a recurrence means, what counts as an occurrence, what may escalate. **CCCb measures** how alike two texts are, and decides nothing. **CNS binds** a verdict to the content it was about, and decides nothing. Neither of the others replaces CCC's authority: a measurement is not corroboration, a binding is correspondence and not truth, and a bound PASS does not admit what CCC's rules refuse.

Install: `pip install -e .` has no dependencies. `.[match]` adds CCCb pinned to one full commit (`737cf0e`, the one that resolves tied candidates in id order). `.[cns]` adds CNS pinned to the tag v3.0.0. A test checks that the `match` pin is exactly one 40-hex commit of CCCb, and a second test runs the installed matcher under several hash seeds to catch a stale install. Installing CCCb from an archive of a commit rather than from git can pick up the stale copy in CCCb's tracked `build/lib/` (it did, in one run of this campaign), so install from the git URL the extra names. Without a matcher, `record_external_finding` raises `TextMatcherMissing` and nothing else changes. Without CNS, only the `ccc.cns_connector` functions that need it raise `CnsNotInstalled`.

What CCC checks on a matcher's answer before it can become a record (`ccc/text_matching.py`): the shape; that every id is one CCC gave it; that every score is a finite number in [0, 1]; that a match length is a positive integer; that a recurrence's best id is in its own cluster. A bad answer raises `ValueError` and nothing is written. CCC does not compare a score with the matcher's threshold; "this is a match" is the matcher's call. A finding whose conclusion or evidence excerpt is blank is refused. `discover` cannot create a record at MANDATE; a human advances a pattern with evidence (`CCC-123-001`). `save` writes a temporary file, syncs it and renames it over the target, so a failed save leaves the previous complete file.

Known limits, each stated as a strict expected failure in the tests so that closing one makes its test say so:

- **A resubmission can count as an independent occurrence.** CCCb needs a 40-character shared span to call two texts duplicates, and its duplicate measure is case- and whitespace-sensitive and sees only the first 50,000 characters. An identical 31-character finding resubmitted three times, an upper-cased copy, a copy with doubled whitespace, or a copy behind 80,000 characters of padding is measured as a recurrence, which CCC counts as an occurrence, so the original can be lifted from ANOMALY to PATTERN by a machine. MANDATE stays human-only. Fixing the measurement is a change in CCCb.
- **A matcher whose `add` fails after a record is written** raises to the caller, but the record stays, and in that process a retry is not seen as a duplicate. A reload re-indexes it.
- **The state file has no digest or version.** An edited file loads as valid, and a repeated event id in the audit, provenance, epistemic or lineage lists is not refused. CCC makes no tamper-evidence claim for the file. An empty file is a fresh store by design.
- **Callers that hold the managers can bypass the facade.** `system.provenance`, `system.discovery.advance` and the other managers are attributes; `human_verifier` guards the facade methods, and `write_permission` guards the doors listed in section 8. Counting occurrences trusts the `relationships` a caller passes to the bare `discover`, and a duplicate is recognised by the words "duplicate detection" in a record's `method`.
- **The CNS connector is ALPHA only** and judges on a scratch copy that carries neither the live `write_permission` nor `human_verifier`: a PASS says CCC's rules admit the call, not that the application's own checks do. The digest binds the call, not the store, so a PASS stays bindable after the state it was judged on has changed, and a hand-built PASS with the right subject and digest binds too. A binding says which content a verdict was about, nothing more. CCC has no outcome (OMEGA) end and does not claim one.

Evidence for all of the above is in `tests/test_matcher_boundary.py`, `tests/test_determinism.py`, `tests/test_evidence_integrity_persistence.py` and `tests/test_integration_ccc_cccb_cns.py` (the last runs the real CCCb and CNS and is skipped only where CNS is absent).

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

## Glossary

- **Actor:** who is making a call: a human, a model, a system or an external source. `Actor.human(...)` is a label, not proof of identity.
- **Provenance status:** where a record came from and what authority it holds, for example `USER_ESTABLISHED`, `ASSISTANT_PROPOSED` or `PROVENANCE_UNCERTAIN`.
- **Epistemic status:** how well supported a claim is, for example `EVIDENCE`, `INFERENCE`, `THEORY`, `UNKNOWN` or `CONFLICTED`.
- **Evidence root:** the earliest records a conclusion rests on, found by following its evidence links back.
- **`write_permission`:** an optional check the application supplies. CCC asks it before the eleven machine-side doors and goes on only if it answers exactly `True`.
- **`human_verifier`:** an optional check the application supplies to confirm that a "human" actor is really that person. Without it, CCC takes the label as given.
- **Attestation:** an HMAC stamp (a keyed fingerprint) on a handed-off record, made with a key the caller supplies. With a key, only stamped records count as `held`.
- **Gate, `PASS`, `RETRY`, `TERMINAL_BREACH`:** CNS's shapes for a decision. `PASS` means admitted, `RETRY` means a human supplying what is missing would be admitted, `TERMINAL_BREACH` means refused with no human input that would help.
- **`ALPHA` and `OMEGA`:** the two gate positions. `ALPHA` runs before the work; `OMEGA` judges the produced result. CCC has `ALPHA` only.

## License

Apache-2.0. Copyright 2026 William N. King. See `LICENSE` and `NOTICE`.
