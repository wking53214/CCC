# CCC — Cognitive Continuity Constitution

Dependency-free **memory of claims over time** that keeps a machine from rewriting what a human actually thought: who originated each claim, human-only promotion to fact, and a human-only erase operation (not yet grounded in the ≡TACK Constitution; see section 4). Optional pack for [`observe-perceive`](https://github.com/wking53214/observe-perceive). Not a standalone product. Test counts are under Release and test status in section 4; CI runs every one of them (section 8 explains the two CI jobs).

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

Decisions on the constitution's text are kept in [`decisions/`](decisions/). [DEC-0002](decisions/DEC-0002_v1.md) (v1.1 draft, decided provision by provision) leaves Articles I.G, III.F, XI.A, XII.E, XV.A and XVII.A-D UNRESOLVED; I.G and XVII.A-D are nonetheless enforced in this package's code.
**Erasure is only partly grounded.** `CCCSystem.erase` lets a human, with a stated basis, wipe a record's text and leave a tombstone; anything built on it is downgraded to `THEORY`. The ≡TACK Constitution v4.0 (Developed Candidate, wking53214/constitution) contains no human right of erasure, and most CCC rules are sourced to the build directive, not to an article. Article XVIII does bear on it: it requires negative findings to be preserved. Rule `CCC-HISTORY-003`, the one rule sourced to an article, makes `erase` and `redact` refuse a negative finding: a record the human rejected, a record material to a conflict (open or resolved), or a record with a `CONTRADICTS` edge. Change course by superseding it. That covers what CCC can see; it does not cover every kind of non-confirmed claim. Erasing an ordinary record is still unratified mechanism, and whether to add an erasure article to the Constitution is the owner's decision.
New records start from [`DEC-TEMPLATE_v1.md`](decisions/DEC-TEMPLATE_v1.md). `CCCSystem.decide` can store the same shape with a decision: the options considered, the one selected, each other option rejected with a reason or deferred (every option not selected must be one or the other), and the assumptions it rests on. A decision recorded without them is stored exactly as before.

### Release and test status

Measured 2026-10-30 at main `0228a53`.

| What | State |
|---|---|
| Version | 0.1.0 (`pyproject.toml`, `CCCSystem.version`, and the constitutional rules) |
| Tag and GitHub Release | None yet. Tagging is the owner's decision. |
| CI on main | Green |
| Tests | 409 passed, 1 skipped and 1 xfailed without CNS; 924 passed and 1 xfailed with the `cns` extra installed (parametrized cases counted) |
| Pins | The optional `cns` extra is pinned to the tag v2.2.0. The `cccb` library is pinned to commit `8e3c779`; `cccb` main is two commits ahead, and the only change is its own CNS pin, so the code is the same. |
| Write permission | Nine record-creating doors ask the application's check first (the nine listed in section 8). `decide`, `correct`, `amend`, `supersede` and the other human actions never ask. |

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


Adapter in observe-perceive. Extra pin: `cognitive-continuity-constitution @ git+…/CCC@2cf7aa19`. Ecology duck-types a FindingRecord toward CCC (`finding.py`) without importing this package.

## 7. Stack Integration Topology

```text
observe-perceive decision → orchestrator_ccc_adapter → CCC (opt)
HERALD / TIE / Ecology may feed claim-like records; no hard imports
```

### Place in the evidence spine

The evidence spine is the five repositories a document passes through in order: HERALD reads it and extracts claims, TIE records the evidence, Conservation_Kernel decides whether a root may be admitted, Governance_Gateway judges the admission door, and CCC takes the document into its store. CNS holds the roster that makes the decision, the check that every seat judged the same document, and the one-use guard that lets an approved decision open only the door it judged. `chains/evidence_spine.py` in CNS runs all of it end to end. Measured 2026-10-30 with every repository at main: 30 results, all ok, and exactly one recorded GAP (a kernel built without its guard and called directly), which the script asserts as a stated fact and never skips.

CCC is the last hop: the document goes into its store only if the roster allows it. With the roster's guard as its `write_permission`, a direct `ingest` after a roster no is refused, and an approved decision opens `ingest` and `record` once, for the one document it judged. The other seven gated doors carry a conclusion, a finding or an observation that no seat judges, so they stay refused after any decision. CNS's spine script reads the gated doors off CCC and goes red if CCC gates one the roster's reader does not name.

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
`record_external_finding`, `discover`, `detect_road_sign` and `record_road_sign` each call it once,
first, with a `ccc.permission.WriteRequest` (the method name and the caller's arguments, deep-copied, with no
defaults filled in), and go on only if it returns exactly `True`. Anything else, an error from the check
included, raises `WritePermissionRefused` before CCC touches its store, its rules or its audit trail.

Only those nine ask, and each asks once: `interpret` calls `derive`, which writes the record, and the nested
calls do not ask again, because a one-use permission would be spent by the first yes. `record_road_sign` is the
same act as `detect_road_sign`, and `discover` is the bare way to create what `record_external_finding` creates
under stricter rules, so each of those asks too, or the gate would be one call away from useless. The road
signs and stage moves that `record_external_finding` makes as part of its own work happen under its one ask.
`decide`, `correct`, `amend`, `supersede`, `accept`, `reject`, `redact`, `erase` and the rest never ask, so a
human's action is not held up by a machine's roster. The permission is asked first, so a yes can be spent on a
call that CCC's own rules then refuse; that fails closed, and the caller needs a new permission.

Left open on purpose: `adopt_discovery`, `advance_discovery`, `link_road_sign` and `record_resolution` change a
record that already exists, and `detect_conflict`, `ask`, `attach_evidence` and `relate` create a flag, a
question, a link or a relationship, not a finding or a record of material. Gating those is a separate decision.

Limits: a system built without a check is not stopped, and nothing here can see that. Anyone holding the
system's `store` can also write to it directly, which no check can see. The check is not saved
with the store, so a reloaded system or the connector's scratch copy has none unless given one. Tests:
`tests/test_write_permission.py` (the first five) and `tests/test_write_permission_doors.py` (the other four).

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
