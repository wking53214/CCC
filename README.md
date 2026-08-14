# Cognitive Continuity Constitution

This repository contains a dependency-free executable enforcement layer for
the Cognitive Continuity Constitution requirements supplied in the build
directive.

Run the demonstration from a clean checkout:

```bash
python3 -m ccc
```

Run the constitutional tests and numbered harness:

```bash
python3 -m pytest -q
python3 -m ccc.testing
```

The public facade is `ccc.CCCSystem`. It preserves immutable artifact
identifiers, explicit provenance and epistemic transitions, separate Chain A
and Chain B records, evidence-root cascades, historical lineage, human
resolution, audit events, and JSON snapshots.

No ratified CCC document or prior harness history is present in the GitHub
repository. Rule traceability therefore identifies the supplied build
directive as its source and leaves article identifiers null; it does not
invent constitutional article numbers.
