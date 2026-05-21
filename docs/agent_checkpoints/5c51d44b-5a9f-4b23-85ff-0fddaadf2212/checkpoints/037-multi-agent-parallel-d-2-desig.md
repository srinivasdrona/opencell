<overview>
OpenCell — open-source Python whole-cell M. genitalium simulation on vivarium-core, ported from Karr 2012's MATLAB WholeCell model. This session continued past MATLAB-eviction work into multi-agent parallel workflow: shipped the Karr full-mat catalog, m2-per-condition snapshots, p10 mass partition, and a Phase D.2 design doc; established a worktree-based concurrency convention; and arrived at an open architectural decision (Q1 oracle target for D.2) where the user asked for an external GPT-5.4 critique of my reasoning.
</overview>

<history>

1. **MATLAB eviction completion** — sealed prior work
   - Seeded `data/karr_archive/fixture_hashes.json` via `validate_karr_archive.py --update --skip-rerun`
   - Cleaned scratch files
   - Committed everything as `f06b8a0` ("MATLAB eviction: Karr archive replaces direct .mat reads")
   - Surfaced backlog: m2-per-condition-snapshots, e2-decision-point, per-AA mapping

2. **User: "does it make sense to get the full set of files moved to Python?"**
   - Discussed pros/cons of full vs whitelist Python extraction
   - Recommended keep whitelist + add lightweight catalog (no payloads)

3. **User: "spin up agent for catalog work in background and pickup next scientific todo"**
   - Launched `karr-mat-catalog` background agent
   - Picked `m2-per-condition-snapshots` as next, but user said make this background too
   - Launched `m2-per-condition-snapshots` background agent
   - I picked `e2-decision-point` (analytical, no chassis touch) for myself
   - Wrote E.2 decision artifact at `C:\Users\sdrona\.copilot\session-state\<sid>\files\e2_decision.md`: recommended sequence **D.2 → v2 chassis swap → M5**

4. **`karr-mat-catalog` agent completed** (~245s)
   - Committed `d8201fc` on main: `scripts/dump_karr_mat_inventory.py` + `data/karr_archive/full_inventory.json` (4,837 leaves) + `full_inventory_summary.md`
   - Confirmed: ~5% of total fields (238) are currently consumed; 95% catalogued

5. **User: "this is the working method we will use: any work that does not touch the chassis can be spun up as parallel"**
   - Discussed parallel-agent budget: practical 3-5 concurrent, binding constraint is file-disjointness in shared working tree

6. **User: "why do we have wcEcoli ingestion survey as one of the todos?"**
   - Explained: Phase 6 stretch goal, gated on M7
   - User: "demote everything beyond M7 as parking-lot note"
   - Marked 7 stretch todos as `blocked` with `PARKING-LOT (post-M7 stretch)` prefix: e1-wcecoli-survey, e2-ecoli-port, l1/l2/l3 methodology, z1/z2 stretch

7. **User: "get a couple of background agents on work items not touching chassis"**
   - User asked where to read agent progress first
   - Established convention: feature branches + status file at `~/.copilot/session-state/<sid>/files/agent_<name>_status.md`
   - Launched two more agents: `d2-design-doc` and `p10-mass-partition`

8. **`m2-per-condition-snapshots` agent completed** (~1244s)
   - Branch `m2-per-condition-snapshots` @ `9f8b186`
   - Approach: derived per-condition counts by scaling fitted-mean snapshot by `expression[:, c] / expression[:, mean]` per gene
   - 600 passed + 2 xfailed (was 599+3); lifted xfail on `test_compute_baseline_demand_respects_condition`

9. **User: "merge that and sync E:\opencell\plan.md"**
   - Merged m2 to main as `0fb5df3`
   - Synced E:\opencell\plan.md (was dated 2026-04-25 with 478 tests; ported full Current Status block from C-drive working copy)
   - Committed plan sync as `d935ad4`
   - Restored to `agent/p10-mass-partition` branch so running agents see expected tree

10. **User: "what else are the todos on the main chassis branch?"**
    - Found stale items: `e1b-mass-integrator` and `matlab-full-eviction` were `in_progress` but actually done; `m3-transcription` and `m4-translation` used pre-pivot numbering for what shipped as M2/M3
    - Proposed cleanup

11. **`d2-design-doc` agent completed** (~522s)
    - Branch `agent/d2-design-doc` @ `fa59925`: `docs/design/d2_complex_assembly.md` (496 lines)
    - **Branch-switch race occurred**: initial commit landed on wrong branch because p10 agent ran git checkout mid-session in shared tree. d2 agent recovered atomically with `git update-ref`. **No data loss but confirms concurrency hazard.**
    - 5 open questions for human surfaced

12. **User: "I agree with (a) Git worktrees"**
    - Adopted convention: each future agent gets `E:\opencell-worktrees\<agent-name>` worktree
    - Did SQL cleanup: closed 4 stale todos, added `d2-complex-assembly` and `v2-chassis-swap` with proper deps
    - Critical path now 7 pending: d2 → (v2-swap, m5) → m6, m7 → l4-paper

13. **User: "critique the d2 design doc before starting the work"**
    - Launched sync rubber-duck agent
    - **Recommendation: rework before implementation.** 3 BLOCKERs, 4 HIGH, 4 MEDIUM:
      - BLOCKER: ribosome-cost data missing from fixture (only in MATLAB source)
      - BLOCKER: oracle path wrong (`State_Mass.dump.complex.*` not `fittedConstants.states.ProteinComplex.*`); anchor counts wrong (snapshot has e.g. ribosome=56 all bound, mature=0)
      - BLOCKER: MC algorithm collapse changes physics (Karr's MC is network-level, doc's is per-complex)
      - HIGH: activation rules internally inconsistent; chassis store mismatch; cold-start hack ≠ stability; scope creep with folding/activation
      - Two real human decisions needed: Q1 (oracle target: mature-only vs bound+free) and Q2 (scope: include folding/activation)

14. **`p10-mass-partition` agent completed** (~1648s)
    - Branch `agent/p10-mass-partition` @ `0c48ce0`
    - p10 split into 3 archive-derived sub-targets + 1 consistency guard
    - **p10b protein flips green** (27.7% of cellDry); p10a (RNA) and p10c (residual) stay xfail
    - Substrate sub-target NOT created — `snapshot_substrates` units don't decode to cellular counts; documented as blocker
    - Merged to main; suite verified: **602 passed + 4 xfailed** (was 600+2)

15. **User Q: "pros and cons of mature-only vs integrated bound+free?"**
    - Provided detailed comparison table; recommended (b) for v1, migrate to (a) after v2-swap + M5

16. **User Q: "what happens if we stay with mature-only and continue building? Be objective."**
    - Provided detailed objective answer:
      - Mature-only test is degenerate at steady state (mature ≈ 0 in working cell)
      - Hidden failure mode: silent under-production passes test but starves consumers
      - 8-14 weeks of untested D.2 code before any direct signal
      - Distinction: interface contract (mature-only correct) vs validation oracle (must be non-zero quantity)
      - Recommended: mature-only interface + bound+free / mass / rate oracle for v1

17. **User: "critique this reasoning with GPT5.4"** ← CURRENT REQUEST, NOT YET STARTED
    - Need to launch a sub-agent (likely rubber-duck or general-purpose with model override `gpt-5.4`) to critique my objective reasoning about mature-only vs bound+free

</history>

<work_done>

**Commits landed on main this session (in order):**
- `f06b8a0` MATLAB eviction (archive + 8 ingest scripts refactored)
- `d8201fc` Karr full-mat catalog (4,837 leaves catalogued)
- `0fb5df3` Merge: m2 per-condition snapshots
- `d935ad4` plan.md sync
- `<merge>` Phase E.1c p10 mass partition

**Test status evolution:** 599+3 → 600+2 (m2) → 602+4 (p10 partition)

**Files created:**
- `data/karr_archive/full_inventory.json` (1.5 MB, 4837 leaves)
- `data/karr_archive/full_inventory_summary.md`
- `data/karr_archive/fixture_hashes.json` (CI drift detector seed)
- `scripts/dump_karr_mat_inventory.py`
- `scripts/validate_karr_archive.py`
- `scripts/build_karr_archive.py`
- `opencell/_karr_archive.py`
- `data/karr_archive/README.md`
- `docs/design/d2_complex_assembly.md` (on branch `agent/d2-design-doc`, NOT on main)
- `C:\Users\sdrona\.copilot\session-state\<sid>\files\e2_decision.md`
- `C:\Users\sdrona\.copilot\session-state\<sid>\files\agent_d2_design_doc_status.md`

**Files modified on main:**
- All 8 `scripts/karr_native_ingest_*.py` (use load_karr_archive)
- `opencell/m2/transcription.py` (per-condition column logic)
- `opencell/vivarium/karr_m2.py`, `karr_composite.py` (consumers)
- `opencell/analysis/phenotypes.py` (m2 per-condition + p10 sub-extractors)
- `data/karr_fixtures/karr_phenotype_targets.json` (p10 sub-targets added)
- `tests/phaseE/test_karr_phenotypes.py` (4 new sub-target tests)
- `tests/vivarium/test_karr_m2_chassis.py`, `test_karr_pool_replenishment.py`
- `data/karr_fixtures/karr_native_m2.{json,npz}` (counts_mature[525,3])
- `E:\opencell\plan.md` (sync to current state)
- `C:\Users\sdrona\.copilot\session-state\<sid>\plan.md` (working scratchpad)
- `scripts/matlab/README.md` (bootstrap-only banner)

**SQL todo cleanup:**
- 4 stale closed: `e1b-mass-integrator`, `matlab-full-eviction`, `m3-transcription` (rename note: shipped as M2), `m4-translation` (rename note: shipped as M3)
- 7 stretch parked as `blocked PARKING-LOT (post-M7)`: e1-wcecoli-survey, e2-ecoli-port, l1/l2/l3, z1/z2
- 2 added: `d2-complex-assembly`, `v2-chassis-swap`
- Dep graph rebuilt: d2 → v2 → (m6, m7); d2 → m5 → l4-paper

**Active agent state at compaction:**
- All agents completed. No agents running.
- Branches still extant: `agent/d2-design-doc` (unmerged, awaiting design v2 after rubber-duck rework), `agent/p10-mass-partition` (already merged), `m2-per-condition-snapshots` (already merged).

</work_done>

<technical_details>

**Concurrency hazard with shared working tree:** Multiple background agents in the same `/mnt/e/opencell` shared working tree caused a real branch-switch race during the d2 + p10 parallel run. d2's commit landed on p10's branch because p10 ran `git checkout` between d2's checkout and commit. d2 recovered atomically with `git update-ref`. **Adopted convention going forward: every background agent gets its own `E:\opencell-worktrees\<agent-name>` worktree on `agent/<name>` branch.**

**E.2 decision (D.2 → v2 chassis swap → M5):** Sequenced based on yield-per-effort matrix in `files/e2_decision.md`. D.2 first because it's a hard prerequisite for both M5 (replisome) and "fully real" v2 mechanics (RNAP/ribosome are complexes). Single-pick alternative would be v2-swap for biggest immediate phenotype delta (4 circular → real).

**Karr complex state-form distinction:**
- `mature` = assembled and free in cytosol, idle
- `bound` = actively engaged (translating mRNA, transcribing, replicating)
- Snapshot is dominated by bound forms (ribosome 56/56 bound, RNAP 40/40 bound, gyrase mostly bound) because healthy cells don't have idle ribosomes
- This makes mature-only validation oracle degenerate (compares to ~0)

**Rubber-duck D.2 critique findings:** Real oracle path is `data.states.State_Mass.dump.complex.{counts, matureIndexs, boundIndexs, dryWeight}` (which is NOT currently exposed in `_karr_archive` — needs ARCHIVE_SPEC extension). Complex mass is ~38% of cellDry, not the 25% in original doc. 20 complexes carry negative-coefficient byproducts (PAP/PPI/PI/ZN/H/AMP/Mg etc.) — must be emitted to substrate path, no silent drops. Karr's MC is network-level, not per-complex.

**Per-condition m2 snapshot derivation:** Single fitted-mean snapshot scaled by `expression[:, c] / expression[:, mean]` ratios per gene. No raw per-condition State_Rna dumps exist in archive. Fully data-derived; scales mechanically.

**p10 partition results:**
- p10a RNA = 4.35% of cellDry, xfail
- p10b protein = 27.7% of cellDry, **green** (matches chassis)
- p10c residual = 67.95%, xfail (DNA + complexes + lipid + substrate pool init)
- substrate sub-target NOT created — `snapshot_substrates` units don't decode

**Plan.md divergence pattern:** C-drive scratchpad (`C:\Users\sdrona\.copilot\session-state\<sid>\plan.md`) is the working source-of-truth; E:\opencell\plan.md is the canonical committed plan. They diverge during work; sync at meaningful milestones (just did one as `d935ad4`).

**Open user-facing question:** "what happens if we stay with mature-only?" — I answered objectively (degenerate test, 8-14 wk untested D.2 window, hidden failure mode), distinguishing interface contract (mature-only is correct) from validation oracle (needs non-zero quantity). User now wants this reasoning critiqued by GPT-5.4.

**Available model overrides for sub-agents:** `claude-sonnet-4.6` (default), `claude-opus-4.7`, `gpt-5.4`, `gpt-5.3-codex`, `gpt-5.2-codex`, `gpt-5.2`, etc. — passed as `model` parameter in task tool.

</technical_details>

<important_files>

- `E:\opencell\plan.md`
  - Repo canonical plan, just synced. Contains current status (602+4, MATLAB eviction + m2-per-condition + p10 partition), full phase narrative, E.2 decision link.
  - Last updated commit: `d935ad4`

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`
  - Working scratchpad; mirrors E-drive state plus richer in-progress notes.
  - Updated at line ~404 (Current Status block)

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\e2_decision.md`
  - 7237-char decision artifact for E.2: D.2 → v2 → M5 sequence with yield-per-work matrix.

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\agent_d2_design_doc_status.md`
  - D.2 design agent's report; lists 5 open questions, branch race recovery details.

- `docs/design/d2_complex_assembly.md` (on branch `agent/d2-design-doc` @ `fa59925`, NOT on main)
  - 496-line D.2 design doc; flagged by rubber-duck for rework. Read with: `git show agent/d2-design-doc:docs/design/d2_complex_assembly.md`
  - 3 BLOCKERs: ribosome cost path, oracle path/anchors, MC algorithm collapse
  - 4 HIGH issues; 4 MEDIUM; 5 open questions

- `data/karr_archive/karr_archive_manifest.json`
  - Lists what's currently in archive. Does NOT yet expose `State_Mass.dump.complex.*` arrays which D.2 oracle needs. Will need ARCHIVE_SPEC extension before D.2 implementation.

- `data/karr_archive/full_inventory.json`
  - 4,837-leaf full catalog (no payloads); use to discover any field path before re-running MATLAB.

- `data/karr_fixtures/karr_protein_complexes.json`
  - 201-complex composition fixture (D.0). Used by D.2. Note: `chaperones` field for `MG_392_393_21MER` looks corrupted per rubber-duck (contains metabolites not chaperones).

- `data/karr_fixtures/karr_phenotype_targets.json`
  - 13 phenotypes now (10 original + 3 p10 sub-targets).

- `opencell/analysis/phenotypes.py`
  - Phenotype extractors. Modified for per-condition + p10 sub-targets in this session.

- `tests/phaseE/test_karr_phenotypes.py`
  - 13 phenotype tests; 4 new from p10 partition.

- `scripts/build_karr_archive.py`
  - ARCHIVE_SPEC dict at top defines all consumed Karr fields. Will need extension for D.2 (ribosome assembly costs from `RibosomeAssembly.m`, complex State_Mass paths).

- `opencell/_karr_archive.py`
  - Namespace loader; `_StructArray`, `_NestedStructArray.per_parent(i)` for nested struct arrays.

</important_files>

<next_steps>

**Immediate (current request — NOT started before compaction):**
- User asked: "critique this reasoning with GPT5.4"
- The "reasoning" being critiqued: my objective answer about mature-only vs bound+free oracle for D.2 (last assistant turn before user's request)
- Action: launch a sub-agent (likely rubber-duck) with `model: gpt-5.4` override, providing as context: (1) the rubber-duck's original D.2 critique, (2) my mature-only-vs-bound+free comparison, (3) my objective reasoning answer, (4) the question — is my reasoning sound, am I missing anything, are there cases where mature-only IS testable that I dismissed?
- Then surface findings to user; user will decide Q1 (oracle target) and Q2 (scope: folding/activation in D.2 or split)

**After Q1/Q2 resolved:**
- Spin up D.2 design-v2 agent in worktree `E:\opencell-worktrees\d2-design-v2` with: original doc + rubber-duck critique + Q1/Q2 answers + ARCHIVE_SPEC extension list (ribosome costs, State_Mass.dump.complex paths)
- Re-critique design v2
- Implement D.2 in worktree

**Open todos on critical path (7 pending):**
- `d2-complex-assembly` (next, awaiting design rework)
- `v2-chassis-swap` (deps: d2)
- `m5-replication-cellcycle` (deps: d2)
- `m6-regulation` (deps: v2-swap)
- `m7-karr-validation` (deps: v2-swap)
- `l4-methods-paper` (deps: m5)
- `m1-extract-per-process-fixtures` (independent, non-chassis, agentable)

**Worktree convention to apply going forward:**
- `git worktree add E:\opencell-worktrees\<agent-name> -b agent/<agent-name>` before launching each agent
- Agent operates entirely within its worktree
- Merge to main from main checkout
- `git worktree remove` after merge

</next_steps>