# Cognitive Continuity Constitution — Implementation Report

Status: IMPLEMENTED for the explicit requirements in the supplied build
directive, with the limitations and unresolved source questions below.
Revised 2026-11-07 against main `6f80792`. The original build report
described a larger feature set. Several of those features were removed on
2026-10-06 (see "Buried record types" below), and this revision removes them
from the description.

The GitHub repository `wking53214/CCC` was empty at implementation start. It
had no modules, data models, persistence, governance implementation, tests,
documentation, constitutional text, or harness history. There were therefore
no existing behaviors to merge or silently reinterpret.

## Architecture

`CCCSystem` is the public orchestration facade. State is held by `CCCStore`,
which uses immutable dataclasses and explicit identifiers. `CCCStore.save()`
and `CCCStore.load()` provide the smallest persistence layer needed by the
current in-memory architecture: a JSON snapshot that preserves identity,
lineage, relationships, statuses, and audit history. Saves write a temporary
file, sync it, and rename it over the target, so a failed save leaves the
previous complete file.

The enforcement path is:

```text
CCCSystem operation
    -> write permission check (only on the doors that ask it; see README section 8)
    -> ConstitutionalRuleEngine
    -> domain manager
    -> immutable replacement/event
    -> LineageManager / AuditTrail
    -> CCCStore
```

Modules are separated by responsibility:

- `models.py`: closed vocabularies and immutable domain records.
- `provenance.py`: Chain A origin and explicit provenance transitions.
- `evidence.py`: Chain B support links, roots, trace validation, and cascades.
- `epistemic_state.py`: historical/evidence/inference/interpretation/simulation/theory states.
- `lineage.py`: correction, amendment, supersession, redaction, erasure, adoption, and branch edges.
- `constitutional_rules.py`: versioned, identifiable, auditable rule registry (21 rules) and decisions.
- `human_resolution.py`: neutral uncertainty records and human resolution.
- `road_signs.py`: observable indicators that cannot be conclusions.
- `discovery.py`: machine-attributed discovery and explicit anomaly → pattern → mandate progression.
- `recurring.py`: read-only listing of recurring groups of machine findings.
- `conflict.py`: conflict classification, presentation, and human resolution.
- `query.py`: discoverability and presentation ranking without deletion.
- `audit.py`: append-only in-process consequential transition events.
- `permission.py`: the `write_permission` hook, which the application supplies to stand a decision in front of new records.
- `human_auth.py`: the `human_verifier` hook, which the application supplies to check human operations.
- `record_status.py`: the read-only record lookup CNS asks ("was this exact output recorded here?").
- `text_matching.py`: the seam where an application plugs in a text matcher (CCCb). CCC checks the matcher's answers but imports nothing from CCCb.
- `semantic.py`, `resume_packet.py`, `store.py`, `errors.py`: semantic index, handoff packet, persistence, and error types.
- `cns_connector.py`: optional connector that expresses an attempted transition as a
  CNS gate result. Nothing else in the package imports it, and it imports CNS lazily, only when called.
  A constitutional refusal is `RETRY` only if a human supplying the missing
  authorization basis, human event or evidence root is shown, on a scratch copy of the
  store, to get the same call admitted; otherwise it is `TERMINAL_BREACH`.
- `testing/harness.py`: H01–H62 machine-readable registry and result runner.

## Data model and state transitions

Every `Artifact` has an immutable `artifact_id`, an independent `origin`
actor, `provenance_status`, `epistemic_status`, availability state, source
identifiers, machine processing history, and content digest. The digest is a
SHA-256 fingerprint of the stored UTF-8 content; it is not an identity,
signature, or tamper-proof audit guarantee.

When a human-authored container references machine-originated source
material, the source IDs are retained in `machine_source_ids` and the default
provenance is `PROVENANCE_UNCERTAIN`; the container does not silently become a
legitimate evidentiary root. A caller must explicitly declare an independent
human origin when that is genuinely the record's basis.

The required provenance statuses are closed in `ProvenanceStatus`:

`USER_ESTABLISHED`, `USER_ACCEPTED`, `ASSISTANT_PROPOSED`, `UNRESOLVED`,
`REJECTED`, and `PROVENANCE_UNCERTAIN`.

`REJECTED` is final: no transition leaves it, including to `UNRESOLVED`. A
human who changes course supersedes the record with a new one, and the
rejection stays on record. A record may be superseded only once; superseding
it again is refused and names the existing successor, so a decision's history
is one line, never two competing replacements. Corrections and amendments of
an old version are still allowed. Both rules came from innovation_os's
invariants (2026-10-07).

The required epistemic statuses are closed in `EpistemicStatus`:

`HISTORICAL_RECORD`, `EVIDENCE`, `INFERENCE`, `INTERPRETATION`, `SIMULATION`,
`THEORY`, `UNKNOWN`, and `CONFLICTED`.

Provenance cannot be assigned by mutating a record. The manager validates a
transition, records a `ProvenanceEvent`, replaces the immutable artifact, and
records an `AuditEvent`. A model actor cannot create a human status. A human
adoption event can change the status of a machine-originated proposal while
the artifact's machine origin and processing history remain intact.

Epistemic promotion is separate from provenance. Simulation cannot become
historical record. Inference, interpretation, theory, or conflict cannot be
promoted into evidence/history without a human action and a valid evidence
root. Machine consensus is explicitly rejected as a substitute for either.

Chain A is represented by `origin`, `ProvenanceEvent`, and provenance status.
Chain B is represented by `EvidenceLink`, `evidence_root()`,
`trace_evidence_chain()`, and `validate_evidence_chain()`. A human-originated
artifact can be a valid Chain A origin while remaining insufficient Chain B
support for another claim.

Corrections and supersessions create new artifacts and append lineage edges;
the prior artifact remains queryable. Redaction and erasure change the prior
artifact into an unavailable tombstone and append distinct relationship types.
Erasure/redaction invalidates active evidence links transitively and downgrades
unsupported dependents to `THEORY`.
Erasure and redaction are refused for a negative finding (a rejected record, a
record material to a conflict, or one with a `CONTRADICTS` edge; rule
`CCC-HISTORY-003`, Constitution v4.0 Article XVIII): such a record can be
superseded but never removed.

## Constitutional rule engine

`ConstitutionalRuleEngine` is not a scattered collection of guards. Each rule
contains:

- `rule_id`
- `article` (currently `None` because no CCC source document is present)
- `requirement_id`
- `requirement_text`
- `condition`
- `decision`
- `reason`
- `severity`
- `version`
- `source`

The current source is machine-readable as `BUILD_DIRECTIVE`. Use
`system.rules.trace(rule_id)` to obtain the implementation → rule → article →
requirement trace. The implementation never invents an article number.
`evaluate()` records a decision and raises `ConstitutionViolation` on reject;
`assess()` records a non-raising decision for reports such as evidence-chain
validation.

Human consequence disclosure is informational. Human operations are not
blocked by model recommendations; a model actor is rejected only when it
attempts to exercise human-only authority itself.

## Testing architecture

`tests/test_constitution.py` contains positive and negative/adversarial tests
for provenance, epistemic state, Chain A, Chain B, sovereignty, historical
integrity, erasure cascades, correction, supersession, conflicts, Road Signs,
anomaly → pattern → mandate, simulation, queryability, persistence, and
auditability.

`tests/test_cns_independence.py` proves CCC works with CNS blocked outright (and
with a too-old CNS in front of it) and never skips; `tests/test_cns_connector.py`
covers the optional CNS connector and skips when CNS is not installed. CI runs two
jobs per Python version (3.11 and 3.12). One job runs without CNS, where the connector
module skips by design. The other installs the pinned `cns` extra and sets
`CCC_REQUIRE_CNS=1`, so the connector module must run and cannot skip.

Tests that exercise the text matcher are skipped when CCCb is not installed
(`tests/conftest.py` lists the ten modules). CI installs CCCb, so they run there.

`ccc.testing.harness` maintains exactly H01 through H62. No old harness
registry exists in this repository, so the 18 rows whose meanings cannot be
recovered are explicitly `UNSPECIFIED`; the runner never changes those rows
to PASS. Executable rows include the required adversarial boundaries and emit
`PASS`, `FAIL`, `ERROR`, `SKIPPED`, or `UNSPECIFIED`, plus aggregate counts.

## Demonstration

`python3 -m ccc` demonstrates:

1. human fact establishment;
2. machine inference proposal;
3. machine-generated labeling;
4. blocked model self-promotion;
5. explicit human acceptance;
6. provenance transition with retained machine origin;
7. evidence attachment;
8. human root erasure;
9. dependent downgrade to `THEORY`;
10. complete audit operation list.

## Constitutional requirements implemented

The executable layer implements the explicit requirements for provenance,
origin/evidence separation, epistemic categories and guards, evidence-root
integrity, invalidation/downgrade, human operations, historical lineage,
machine self-ratification protection, uncertainty, Road Signs, the
human-attributed 1 → 2 → 3 method, machine-attributed discovery, conflict
preservation, queryability, audit events, rule evaluation, immutable
identifiers, JSON persistence, a programmatic API, an executable demo, and the
H01–H62 result harness.

### Buried record types

Turning points (inflection), threads and branches, official terms
(canonicalization), and the confirm/refine/42 dialogue loop were removed on
2026-10-06. Nothing in ≡TACK used them, and no article of the ≡TACK
Constitution v4.0 (Developed Candidate) requires CCC to hold them. They are in
wking53214/Graveyard, `ccc/2026-10-06-unused-record-types/`, with how to revive
them. Simulation and constrained modeled trajectories were removed too, but the
`SIMULATION` epistemic status remains. Conflicts and human resolution stay.
State files that hold the buried sections still load, and those sections are
written back unchanged (`ccc.store.RETIRED_SECTIONS`).

## Partially implemented

- Road Sign detection is an explicit observation API. This build does not
  include a natural-language or sensor classifier that automatically discovers
  signs from arbitrary transcripts.
- Discovery is a record-and-validation engine. It does not claim to provide a
  domain-independent ML pattern detector.
- Querying is in-memory over the JSON-backed store and is not an indexed
  multi-user database query service.
- The harness has 36 passing rows, 8 `RETIRED` rows for the features buried on
  2026-10-06, and 18 explicitly `UNSPECIFIED` rows because historical meanings
  are unavailable.

## Not implemented

- No article-level mapping to a ratified CCC text can be implemented until the
  current ratified CCC document is added to the repository or supplied as a
  source artifact. (Constitution v4.0 is in wking53214/constitution; mapping
  CCC rules to its articles is still open.)
- No cryptographically chained or externally append-only audit log is claimed.
- No concurrent multi-process transaction protocol, authentication layer, or
  network API is included. The original build did not require them.

## Known limitations

- The JSON snapshot is recoverable persistence, not a tamper-evident ledger.
- UUID identifiers are immutable within the store but do not prove authorship.
- SHA-256 content digests detect ordinary content changes when compared, but
  do not provide signatures, provenance, or authorization.
- Semantic truth and evidentiary sufficiency still require human/evidence
  inputs; the system enforces labels and transitions rather than pretending to
  solve epistemology automatically.
- The text-matching limits, the write-permission limits and the CNS connector
  limits are stated in README section 7 and section 8.

## Unresolved questions

- What exact ratified CCC article text and article identifiers should replace
  the build-directive source placeholders?
- What historical meanings, if any, should be assigned to H01–H62? The empty
  repository provides no recoverable registry, so those meanings remain
  `UNSPECIFIED` rather than being invented.
- What persistence, identity, retention, and access-control requirements apply
  when this in-memory/JSON implementation is deployed as a shared service?

## Implementation decisions

- Standard-library Python 3.11+ and dataclasses were used because the target
  repository was empty and the smallest maintainable implementation avoids a
  runtime dependency. The optional `cns` and `match` extras are the only
  dependencies, and both are off by default.
- Immutable dataclasses plus replacement events were used instead of mutable
  records so direct provenance/status mutation cannot bypass the managers.
- JSON snapshots preserve tombstones and history instead of deleting erased
  identifiers.
- Missing constitutional articles are represented as `None`, with
  `BUILD_DIRECTIVE` as the source; article numbers were not invented.
- `THEORY` is the downgrade chosen when an evidentiary root disappears and no
  active root remains. This is an implementation decision, not a claim about
  unavailable ratified text.

## Validation commands and results

From the repository root:

```bash
pip install -e .                 # required: subprocess tests import ccc by name
python3 -m compileall -q ccc
python3 -m pytest -q
python3 -m ccc
python3 -m ccc.testing
```

Measured 2026-11-07 on main `6f80792`, Python 3.13:

- pytest, without CNS (CCCb installed): 776 passed, 4 skipped, 7 xfailed;
- pytest, with the pinned CNS (`CCC_REQUIRE_CNS=1`): 1341 passed, 7 xfailed;
- constitutional harness: 62 total, 36 PASS, 8 RETIRED (the features buried on
  2026-10-06), 18 UNSPECIFIED, 0 FAIL, 0 ERROR, 0 SKIPPED;
- demonstration: starts successfully, blocks machine self-promotion,
  accepts explicit human adoption, erases the evidence root, downgrades the
  dependent conclusion, and reports a valid constitutional invariant check.
- ruff (pinned 0.15.22): clean.
