# L2 Isolated-Fidelity Audit (v6 Karr Processes)

Date opened: 2026-05-28
Branch: `audit/l2-isolated-fidelity-sweep` (TBD; doc currently parked on `audit/l1-green`)
Scope: 28 v6 Karr processes after `karr_transcriptional_regulation` (#29) lands;
27 if audited pre-landing. Excludes `karr_cell_cycle_coordinator` (SHIM, no
Karr counterpart).

## What L2 means (locked, see `plan.md` L-axis discipline 2026-05-27)

> **L2 — Isolated fidelity:** Process in isolation reproduces its Karr
> per-tick oracle (substrate-delta replay over the ≥100t `.npz` fixture),
> responds correctly to ≥6 perturbations, hardcode-clean.

L2 is **per-process** and **stand-alone**: each Karr process is driven by its
own pre-recorded substrate state at tick `t`, runs one `next_update()`, and
its emitted deltas are compared to Karr's recorded deltas at tick `t+1`. No
upstream producers, no `KarrAllocationStep` mediation. This is the strongest
single-process correctness contract before integration.

## Why L2 matters now

L1 (FIRING/GATED + dimer-port sub-check) confirms a process *can* run and
reads the right ports. It does NOT confirm the math is right. Two failure
modes L1 misses:

- **Silent reduction**: process uses a coarse approximation of Karr's
  per-reaction stochastic step. L1-green, L2-RED.
- **Stoichiometry / rate drift**: hand-translated constants diverge from the
  fixture-recorded ones. L1 doesn't compare deltas.

## Five-gate methodology

| Gate | Name | Definition | Evidence |
|---|---|---|---|
| **G1** | Fixture present | `data/karr_fixtures/per_process/<Process>.{json,npz,flat.mat}` exist, npz has ≥100 ticks, header keys include `time`, `substrate_counts_pre`, `substrate_counts_post`, `enzyme_counts_pre` (or fixture-specific equivalent) | `ls` + `npz.files` |
| **G2** | Replay test wired | `tests/vivarium/test_karr_<process>_replay.py` (or equivalent) loads the npz, builds a one-process Vivarium engine, drives it tick-by-tick, asserts delta == Karr delta within configured tolerance | grep `replay`, file existence |
| **G3** | Replay PASSES on first ≥100t window | Test runs green; per-tick L1/L∞ tolerance documented in test docstring; tolerance reflects an explicit budget, not "whatever it happens to pass at" | `pytest -k replay` + tolerance literal in test |
| **G4** | ≥6 perturbations covered | Beyond replay, a perturbation suite exists: enzyme-knockout, enzyme-overexpress, substrate-starvation, substrate-flood, allocator-zero, dt-perturbation. Each perturbation has a documented expected-response direction (e.g. "rate ↓ when essential enzyme knocked"). | grep `perturbation` / `parametrize`; count |
| **G5** | Hardcode-clean | No magic constants in process code that should derive from fixture. All rate constants, stoichiometry, MWs, KM values trace to fixture-loaded structures. `grep -E "= [0-9]+\.[0-9e+-]+" opencell/vivarium/karr_<process>.py` flags candidates; each must have a comment citing fixture key or Karr extract section. | grep + manual review |

Verdict per process: **GREEN** (all 5 PASS), **PARTIAL** (G1+G2 present but
G3/G4/G5 fail), **MISSING** (no G2 replay test exists), **N/A** (SHIM).

## Pre-audit inventory (Table 2 from ALL_29 → fixture column)

All 27 Karr-in-v6 processes have G1 fixtures present per
`docs/phase_e/PROCESS_STATUS_ALL_29.md` Table 2. tx-reg (#29) ships its own
fixture in the impl branch. So **G1 is expected to be uniformly GREEN**. The
real audit work is G2-G5.

## Per-process status table (initial — all rows UNKNOWN pending fanout)

| # | Process | G1 fixture | G2 replay test | G3 replay PASS | G4 perturbations ≥6 | G5 hardcode-clean | L2 verdict |
|---:|---|---|---|---|---|---|---|
| 1 | `karr_replication` | ? | ? | ? | ? | ? | UNKNOWN |
| 2 | `karr_replication_initiation` | ? | ? | ? | ? | ? | UNKNOWN |
| 3 | `karr_dna_supercoiling` | ? | ? | ? | ? | ? | UNKNOWN |
| 4 | `karr_chromosome_condensation` | ? | ? | ? | ? | ? | UNKNOWN |
| 5 | `karr_chromosome_segregation` | ? | ? | ? | ? | ? | UNKNOWN |
| 6 | `karr_dna_damage` | ? | ? | ? | ? | ? | UNKNOWN |
| 7 | `karr_dna_repair` | ? | ? | ? | ? | ? | UNKNOWN |
| 8 | `karr_ftsz_polymerization` | ? | ? | ? | ? | ? | UNKNOWN |
| 9 | `karr_cytokinesis` | ? | ? | ? | ? | ? | UNKNOWN |
| 10 | `karr_terminal_organelle_assembly` | ? | ? | ? | ? | ? | UNKNOWN |
| 11 | `karr_cell_cycle_coordinator` | — | — | — | — | — | N/A (SHIM) |
| 12 | `karr_host_interaction` | ? | ? | ? | ? | ? | UNKNOWN |
| 13 | `karr_rna_decay` | ? | ? | ? | ? | ? | UNKNOWN |
| 14 | `karr_rna_processing` | ? | ? | ? | ? | ? | UNKNOWN |
| 15 | `karr_rna_modification` | ? | ? | ? | ? | ? | UNKNOWN |
| 16 | `karr_trna_aminoacylation` | ? | ? | ? | ? | ? | UNKNOWN |
| 17 | `karr_ribosome_assembly` | ? | ? | ? | ? | ? | UNKNOWN |
| 18 | `karr_protein_processing_i` | ? | ? | ? | ? | ? | UNKNOWN |
| 19 | `karr_protein_processing_ii` | ? | ? | ? | ? | ? | UNKNOWN |
| 20 | `karr_protein_folding` | ? | ? | ? | ? | ? | UNKNOWN |
| 21 | `karr_protein_modification` | ? | ? | ? | ? | ? | UNKNOWN |
| 22 | `karr_protein_translocation` | ? | ? | ? | ? | ? | UNKNOWN |
| 23 | `karr_protein_activation` | ? | ? | ? | ? | ? | UNKNOWN |
| 24 | `karr_protein_decay_light` | ? | ? | ? | ? | ? | UNKNOWN |
| 25 | `karr_macromolecular_complexation` | ? | ? | ? | ? | ? | UNKNOWN |
| 26 | `karr_metabolism` | ? | ? | ? | ? | ? | UNKNOWN |
| 27 | `karr_transcription` | ? | ? | ? | ? | ? | UNKNOWN |
| 28 | `karr_translation` | ? | ? | ? | ? | ? | UNKNOWN |
| 29 | `karr_transcriptional_regulation` | (lands w/ #29 impl) | ? | ? | ? | ? | UNKNOWN |

## Fanout plan (when starting the L2 sweep)

1. **Stage 0 — Inventory (cheap, fully scriptable):** for each process, run a
   probe that checks G1 (npz keys + tick count) and G2 (does a replay test
   file exist? what does it cover?). Fill the G1/G2 columns above. Output:
   `L2_INVENTORY_PROBE_RESULTS.csv` committed to this branch.

2. **Stage 1 — Replay scaffolding for processes missing G2:** for each
   process where G2 = MISSING, generate a minimal replay test from a shared
   template (`docs/prompts/L2_REPLAY_TEMPLATE.md` — to be authored). Fanout
   codex agents with strict scope: one test file per agent, no production
   code edits.

3. **Stage 2 — Run G3:** execute all replay tests, capture pass/fail +
   tolerance budget used.

4. **Stage 3 — G3-RED triage:** each failing replay gets a per-process bug
   class assignment (analogous to dimer-port). Expect 3-5 new bug classes
   from this sweep based on prior P2/Class-A audit findings.

5. **Stage 4 — G4 perturbations:** parametrize ≥6 perturbations per process.

6. **Stage 5 — G5 hardcode sweep:** grep for magic numbers, audit each.

## Inputs / references

- L-axis definition: `plan.md` 2026-05-27 lock, `### L-axis discipline`.
- L1 dimer-port audit (methodology template):
  `docs/phase_e/L1_DIMER_PORT_AUDIT.md`.
- Process tracker: `docs/phase_e/PROCESS_STATUS_ALL_29.md` (Table 1 = L-axis
  status by process; Table 2 = artifact links incl. G1 fixtures).
- Critique pipeline reference: `docs/prompts/CRITIQUE_DIMER_PORT.md`
  (template; will fork to `docs/prompts/CRITIQUE_L2_ISOLATED_FIDELITY.md`).
- Per-process P2 A/B/C STATUS docs (under
  `E:/opencell-worktrees/p2-karr-divergence-audit/`) — useful prior art for
  what divergences are already known.

## Open questions for the operator before fanout begins

1. **Tolerance budget**: should G3 use a uniform per-tick L∞ tolerance across
   all processes, or per-process tolerances calibrated from Karr's own
   intrinsic seed-to-seed variance? Recommendation: per-process, calibrated
   from `manifest.json` seed variance in the ensemble.
2. **Perturbation taxonomy**: the 6 perturbation types above are a starting
   set. Should we lock those or let each process declare its own?
   Recommendation: lock 6 as baseline, allow additions.
3. **Sequencing**: by Karr submodel cluster (DNA / RNA / Protein /
   Metabolism / Division) or by current ensemble FIRING-status (FIRING
   first, since they have observable behavior)?
   Recommendation: FIRING-first — yields fastest signal on real production
   risk, since GATED processes are dark in current ensemble anyway.

## Provenance

Skeleton authored 2026-05-28 during the L1-closure session
(`l1-dimer-port-complete` tag + tx-reg impl r3 in flight). Inventory and
audit fanout to follow once L1 is fully green (tx-reg lands).
