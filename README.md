# Cognitive Continuity Constitution (CCC)

> **Unfrozen 2026-09-11.** CCC is an optional recurrence and continuity
> memory for the governed action gate in
> [observe-perceive](https://github.com/wking53214/observe-perceive), not a
> product on its own. It is dependency-free and passes its own suite with
> no sibling present (157 tests plus 1 expected failure; the optional
> CNS-connected test module skips). The gate records into it through an
> adapter after a decision; nothing in the gate requires it.
>
> The 90-day freeze set on 2026-09-08 is lifted early, by the owner's
> decision. It was set on the evidence available that day, which
> predates two things that change the picture: the private `CNS`
> package, one measured schema that the library's repositories join
> on rather than re-typing, and `ghost_tools`' kernel scan, which
> measures duplication and drift against it. Neither existed when the
> freeze was written.
>
> The commercial reading above is **not** superseded. Everything the
> audit established about this repo still holds, including anything it
> says is missing; lifting the freeze removes a restriction on effort,
> not a finding. See
> `docs/audit/COMMERCIAL_RED_TEAM_2026-09-08.md` in observe-perceive, Parts 19 and 35,
> for what the freeze was based on.

## Executable constitutional governance for AI continuity

CCC is a dependency-free Python implementation of a constitutional governance
model for AI systems. It preserves the distinctions that become critical when
an AI system accumulates information, generates interpretations, modifies
knowledge, interacts with human authority, and carries state forward through
time.

The implementation focuses on five foundational concerns:

- provenance;
- epistemic state;
- evidence;
- human authority;
- historical continuity.

Rather than treating these as informal conventions, CCC represents them as
explicit state, relationships, transitions, validation rules, and auditable
events.

---

## Core principle

An AI system should not be permitted to silently transform:

```text
machine-generated information  ->  human-established fact
inference                      ->  evidence
simulation                     ->  history
interpretation                 ->  fact
proposal                       ->  authority
current state                  ->  rewritten history
```

Each of those transitions is either blocked outright or gated behind an
explicit human action plus a valid evidence root. Machine consensus is never
accepted as a substitute for a human decision.

---

## Run it

Python 3.11+, standard library only (`pytest` is a dev-only dependency).

```bash
python3 -m ccc              # executable demonstration
python3 -m pytest -q        # constitutional test suite
python3 -m ccc.testing      # numbered H01–H62 result harness
```

The demonstration walks through human fact establishment, a machine inference
proposal, blocked model self-promotion, explicit human acceptance (with the
machine origin retained), evidence attachment, human root erasure, transitive
downgrade of the now-unsupported dependent to `THEORY`, and a full audit list.

---

## Public API

The facade is `ccc.CCCSystem`. It preserves immutable artifact identifiers,
explicit provenance and epistemic transitions, separate Chain A (origin) and
Chain B (evidence-support) records, evidence-root cascades, historical
lineage, human resolution, append-only audit events, and JSON snapshots.

State lives in `CCCStore` (immutable dataclasses + explicit identifiers).
`CCCStore.save()` / `load()` provide a JSON snapshot that preserves identity,
lineage, relationships, statuses, tombstones, and audit history. Module
responsibilities are listed in [`IMPLEMENTATION.md`](IMPLEMENTATION.md).

---

## Constitutional source

No ratified CCC document or prior harness history is present in this
repository. Rule traceability therefore identifies the supplied build
directive (`BUILD_DIRECTIVE`) as its source and leaves article identifiers
`null` — it does not invent constitutional article numbers.
`system.rules.trace(rule_id)` returns the implementation → rule → article →
requirement trace.

For the same reason, 18 of the 62 harness rows (H45–H62) are `UNSPECIFIED`:
their historical meanings cannot be recovered from an empty repository, and
the runner never promotes them to `PASS`.

---

## Status

Implemented for the explicit requirements in the build directive.
Current validation: **157 pytest passing, 1 expected failure, 1 module skipped** (774 passing with the optional `cns` extra installed, nothing skipped); harness **62 total: 44 PASS, 0
FAIL, 0 ERROR, 0 SKIPPED, 18 UNSPECIFIED**; demonstration runs end to end.

[`IMPLEMENTATION.md`](IMPLEMENTATION.md) is the detailed report, including the
"Partially implemented", "Not implemented", "Known limitations", and
"Unresolved questions" sections. In short: the JSON snapshot is recoverable
persistence, not a tamper-evident ledger; SHA-256 content digests detect
ordinary changes but are not signatures or authorization; and semantic truth
still requires human and evidence inputs — the system enforces labels and
transitions, not epistemology.

## Connecting to CNS (optional)

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

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
