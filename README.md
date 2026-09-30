# Cognitive Continuity Constitution (CCC)

> **Unfrozen 2026-09-11.** CCC is an optional recurrence and continuity
> memory for the governed action gate in
> [observe-perceive](https://github.com/wking53214/observe-perceive), not a
> product on its own. It is dependency-free and passes its own suite with
> no sibling present (142 tests plus 1 expected failure). The gate records into it through an
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
Current validation: **142 pytest passing, 1 expected failure**; harness **62 total — 44 PASS, 0
FAIL, 0 ERROR, 0 SKIPPED, 18 UNSPECIFIED**; demonstration runs end to end.

[`IMPLEMENTATION.md`](IMPLEMENTATION.md) is the detailed report, including the
"Partially implemented", "Not implemented", "Known limitations", and
"Unresolved questions" sections. In short: the JSON snapshot is recoverable
persistence, not a tamper-evident ledger; SHA-256 content digests detect
ordinary changes but are not signatures or authorization; and semantic truth
still requires human and evidence inputs — the system enforces labels and
transitions, not epistemology.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
