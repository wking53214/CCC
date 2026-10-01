# CCC — Cognitive Continuity Constitution

Dependency-free **recurrence / continuity memory** for governed claims. Optional pack for [`observe-perceive`](https://github.com/wking53214/observe-perceive). Not a standalone product. ~135–142 tests.

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

Commercial red team: **FEATURE** (recurrence detection). Unfrozen 2026-09-11; findings not superseded. One xfail historically. Continuity across *processes* still depends on whatever persistence the adapter is given — not a distributed store. Human-sovereignty rules are code invariants in this package, not an identity provider.

## 5. Core Invariants & Guarantees

Fail-closed on unconstitutional promotions (AI→human authority conversion is in the GEMS/CCC shared doctrine). Recurrence is explicit. Stdlib-only so the suite runs with no sibling.

## 6. Inputs, Outputs & Type Contracts

Adapter in observe-perceive. Extra pin: `cognitive-continuity-constitution @ git+…/CCC@2cf7aa19`. Ecology duck-types a FindingRecord toward CCC (`finding.py`) without importing this package.

## 7. Stack Integration Topology

```text
observe-perceive decision → orchestrator_ccc_adapter → CCC (opt)
HERALD / TIE / Ecology may feed claim-like records; no hard imports
```

Proprietary. Copyright (c) 2026 William N. King. All rights reserved. See LICENSE.
