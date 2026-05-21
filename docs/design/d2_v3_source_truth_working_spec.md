# D.2 v3 Source-Truth Working Spec (Started 2026-05-22)

## Purpose

This document starts D.2 v3 using a source-truth-first method.
The goal is to resolve the 4 known BLOCKERs without introducing new
assertion-based errors.

## Guardrails

1. No hardcoded biological values if source artifacts exist.
2. No hallucinated behavior. Unknowns remain unknown until evidence is extracted.
3. `*_flat.mat` fixture evidence has priority over paper-summary narratives.
4. D.2 work in this phase is design-only.

## Inputs (Source of Truth)

1. `data/karr_fixtures/per_process/RibosomeAssembly_flat.mat`
2. `data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat`
3. Current D.2 design doc: `docs/design/d2_complex_assembly.md`
4. Handover and checkpoint context in `docs/agent_checkpoints/...`

## BLOCKER Resolution Plan

### BLOCKER #1: Ribosome cost data

Requirement:
1. Model ribosome assembly explicitly as 30S, 50S, then 70S.
2. Derive energy/cofactor costs from ribosome process source artifacts.

Prohibited:
1. Deriving the full algorithm from `karr_protein_complexes.json` alone.
2. Using a blanket "6x" rule without source-backed derivation.

Evidence to capture:
1. Step definitions for 30S/50S/70S assembly.
2. Per-step cost vectors and relevant kinetics references.

### BLOCKER #2: Scope ownership

Requirement:
1. Produce an explicit process-ownership histogram for complex formation.
2. Define a D.2 whitelist and explicit exclusion list by process ID/name.

Prohibited:
1. Collapsing all non-ribosome complexes into D.2 by default.

Evidence to capture:
1. Distinct formation-process IDs and counts.
2. Excluded process IDs for division/replication/regulation/condensation ownership.

### BLOCKER #3: Emit/update conservation

Requirement:
1. Emit contract must include positive product deltas and negative consumed-part deltas.
2. Design must make ownership of intermediate counts explicit.

Prohibited:
1. "Product-only" emits that create mass by omission.

Evidence to capture:
1. Formal delta schema examples for subcomplex consumption.
2. Conservation checks tied to the emit contract.

### BLOCKER #4: Oracle target mismatch

Requirement:
1. D.2 mature-only outputs validate against mature-only mass targets.
2. Per-complex assertions require stable IDs (`complex.wholeCellModelIDs` in archive layer).

Prohibited:
1. Comparing mature-only outputs against all-forms aggregate targets.

Evidence to capture:
1. Mature-only target fields and units.
2. Archive-field additions needed for per-complex asserts.

## v3 Deliverable Structure

1. Evidence table: claim -> source path -> extracted value -> confidence.
2. Scope contract: includes, excludes, and rationale.
3. Algorithm contract: assembly and emit/update invariants.
4. Oracle contract: mature-only checks and per-complex checks.
5. Supersession note preserving v2 as historical context.

## Open Items (Runtime-gated)

1. Re-extract the concrete value tables from the two `_flat.mat` files.
2. Insert exact source paths and values into the evidence table.
3. Run the critique pass and attach critique outcomes.

Until those are extracted, this spec is intentionally conservative and non-numeric.

## Immediate Run Command

From WSL project root:

```bash
cd /mnt/e/opencell
source .venv-wsl/bin/activate
python scripts/d2_extract_v3_evidence.py
```

Expected outputs:
1. `artifacts/d2_v3_evidence.json`
2. `artifacts/d2_v3_evidence.md`
