# Phase D.2 design-doc agent — status

**Branch:** `agent/d2-design-doc`
**Commit SHA:** `fa59925` (`Phase D.2 design doc: ProteinComplexAssembly spec`)
**Parent:** `d8201fc` (main)
**Pushed?** No. **Merged?** No.

## What was produced

One file: `docs/design/d2_complex_assembly.md` (~28 KB, 496 lines, 8 sections).

Contents:

1. **Data inventory** — full audit of `data/karr_fixtures/karr_protein_complexes.json`: 201 complexes, 482 monomer wids, 722 metabolite wids, 6 compartments. 172 use monomers, 36 use sub-complexes (DAG), 22 use metabolite cofactors, 7 carry activation rules (full 6-rule corpus enumerated), 20 emit negative-coef byproducts (H⁺/AMP/Mg²⁺).
2. **Karr MATLAB algorithm** — summary of `MacromolecularComplexation.m` (392 LOC, Monte-Carlo collision-theory mass-action over independent networks) + `RibosomeAssembly.m` (370 LOC, all-or-nothing with GTP/H₂O cost). Notes the two are collapsed into one Vivarium Process for D.2.
3. **Process API sketch** — `defaults`, `ports_schema()` (5 ports: monomers / subcomplexes / metabolites / rnas / complexes_out + stimuli), `next_update()` skeleton in fenced markdown blocks. No production code.
4. **Oracle plan** — anchor checks against `data.states.State_Mass.dump.complex.counts[matureIndexs, :]` shape `[1206, 6] → [201, 6]`. Concrete tolerances: 70S ribosome ±10 %, RNAP ±15 %, holoenzyme ±20 %, gyrase ±25 %, total complex mass ±15 %. Median over N=50 seeds.
5. **Closed-loop integration plan** — ASCII wiring diagram (M3 → monomers → D.2 → complexes), steady-state coupling argument (D.2 is monomer-starved, not rate-limited), conceptual `topology.yaml` deltas. NO chassis touch.
6. **Phenotype impact** — closes the ~25 % p10 dry-mass gap; converts p5/p6/p7 from hard-coded constants into live state; adds new p8 (free 30S/50S pool).
7. **Risk register** — 6 ranked risks: R1 M3↔D.2 bootstrap circularity (high), R2 activation-rule grammar drift, R3 sub-complex DAG cycle, R4 negative-coefficient byproduct accounting, R5 MC stochasticity flake, R6 perf.
8. **Open questions** — 5 questions for human (Q1 oracle path confirmation, Q2 folding/activation scope, Q3 init-conditions source, Q4 stimulus stubs, Q5 file path).

## Decisions made

- **Collapse `MacromolecularComplexation` + `RibosomeAssembly` into one Vivarium Process.** Both are "fast assembly to subunit-limit" with separate metabolite-cost lines. Collapsing reduces process count; behaviour at steady state is identical.
- **Activation rules ship as a 30-line mini-parser with stimuli pinned to baseline-TRUE values.** Defers Phase G stimulus response.
- **Sub-complex DAG handled by topological sort at construction time, not at runtime.**
- **Subunits keyed by `(wid, compartment)` tuples** (because `formation_compartment_wid` ≠ subunit compartments in general).
- **Negative coefficients = byproducts** emitted to the listed compartment (matches Karr convention).

## Surprises

- `total_subunits min` came out as **−23** in the fixture before I realised 20 complexes carry **negative** coefficients (byproduct accounting like `H, -9.0` for FtsZ-9-mer GDP hydrolysis, `AMP, -1.0` for acyl-ACP variants). This is documented as gotcha #1 (§1) and risk R4. Karr's `complexComposition` matrix in the MATLAB source filters these out (it's monomer + RNA only, summed across compartments) — meaning the byproduct accounting in D.2 must be a **separate balance term**, not a Monte-Carlo network row.
- `data.states.State_ProteinComplex` in the archive does **NOT** expose a top-level `counts` field — the fitted complex counts actually live under `data.states.State_Mass.dump.complex.counts` shape `[1206, 6]` (1206 = 201 × 6 forms). Documented as Q1 in the open-questions list because it should be confirmed by sanity check.
- A parallel agent (`agent/p10-mass-partition`) was actively running `git checkout`s on the same working tree mid-session. **My initial commit landed on the wrong branch** (`agent/p10-mass-partition` instead of `agent/d2-design-doc`). Recovery: ref-update the two branches atomically (`git update-ref refs/heads/agent/d2-design-doc fa59925; git update-ref refs/heads/agent/p10-mass-partition d8201fc`) and clean the doc file out of the shared working tree so the p10 agent sees a clean status. Verified: p10 branch is back at d8201fc with only its own untracked scratch files; d2-design-doc branch holds the commit. **No data loss, no contamination of p10's branch.**

## Open questions for the human

1. **Q1 (Oracle path)** — confirm `State_Mass.dump.complex.counts[matureIndexs, :]` is the canonical oracle, or should we re-run `dump_karr_mat_inventory.py` with payload sampling to verify against MATLAB's `simulation.state('ProteinComplex').counts(matureIndexs,:)`?
2. **Q2 (Scope)** — D.2 is **assembly only**. Should `ProteinFolding` (misfolded → mature) and `ProteinActivation` (inactivated ↔ mature) be folded into D.2 or split into D.3 / D.4? Current doc assumes split.
3. **Q3 (Init source)** — D.2 cold start from Karr fitted complex counts (archive read at runtime) vs. one-step assembly on chassis-init monomers? Doc recommends the former for v1.
4. **Q4 (Stimuli)** — antibiotic / temperature / G6P / PI inputs needed for the 7 activation-rule complexes. Stub at baseline-TRUE for v1; defer real wiring to Phase G stimulus response.
5. **Q5 (Path)** — confirm `opencell/processes/protein_complex_assembly.py` as the implementation file location.

## Constraints respected

- ✅ Document only — no code under `opencell/`.
- ✅ No fixture changes.
- ✅ No chassis touch.
- ✅ No tests modified.
- ✅ Did not touch `scripts/build_karr_archive.py` or `data/karr_archive/`.
- ✅ Did not touch m2/p10 territory (`scripts/karr_native_ingest_m2.py`, M2 chassis, m2 fixture, `karr_phenotype_targets.json`, `phenotypes.py`, `tests/phaseE/test_karr_phenotypes.py`).
- ✅ Did not push, did not merge.

## Next action for human

Review `docs/design/d2_complex_assembly.md` on branch `agent/d2-design-doc`. When approved, kick off D.2 implementation agent with this doc as input.
