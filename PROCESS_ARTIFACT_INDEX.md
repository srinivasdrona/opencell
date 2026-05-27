# PROCESS_ARTIFACT_INDEX — Single Source of Truth

**Created**: 2026-05-26 20:34 IST · session `5c51d44b-5a9f-4b23-85ff-0fddaadf2212`
**Decision backing this file**: DECISIONS.md → `2026-05-26 | opencell | audit-fire-moratorium-and-canonical-status-index`

## ⛔ READ THIS BEFORE FIRING ANY AUDIT SESSION

Before launching any codex audit / class-A / class-B / dead-process session on any process listed below, you MUST:

1. **Look up the process row** in this file.
2. **Open** the listed `findings.json` (5–8 entries each, file:line-cited) and `STATUS.md`.
3. **Open** the corresponding row in `consolidated/findings_index.csv` to find the layer + Track-A PR.
4. **Only fire a fresh audit if**:
   - the process is on the GAP list (bottom of this file), OR
   - the prior STATUS pre-dates a code change that materially altered the process

**Default action**: trust the prior finding and route to the appropriate Track-A PR. Re-deriving a finding that's already on disk wastes 200–400K tokens per session.

---

## Shared paths

- **Class-A worktree root**: `E:\opencell-worktrees\swarm-class-a-<Process>\`
- **Findings JSON**: `<wt>\opencell\validation\swarm\class_a\<process_lowercase_or_snake>\findings.json`
- **STATUS**: `<wt>\STATUS.md`
- **Karr extracts** (28 files): `E:\opencell-worktrees\p3-karr-light-docstrings\docs\karr_extracts\process\NN_<Process>.md`
- **Phase-B design docs** (11 files): `E:\opencell-worktrees\p3-karr-light-docstrings\docs\design\pb_turn<N>_<process>.md`
- **Karr fixtures** (JSON+NPZ+MAT): `E:\opencell-worktrees\p3-karr-light-docstrings\data\karr_fixtures\per_process\<Process>.json`
- **Consolidated audit**: `E:\opencell-worktrees\p3-karr-light-docstrings\opencell\validation\swarm\consolidated\CONSOLIDATED_AUDIT_REPORT.md`
- **Findings index CSV** (R01–R19 + S01–S10): `E:\opencell-worktrees\p3-karr-light-docstrings\opencell\validation\swarm\consolidated\findings_index.csv`
- **Wave-1 dead-process STATUS** (3): `E:\opencell-worktrees\swarm-dead-{protein_processing_i,rna_processing,rc_transcription}\STATUS_dead_*.md`
- **Wave-2-v2 consolidator output** (7, expected): `E:\opencell-worktrees\swarm-dead-consolidator\STATUS_dead_*_consolidated.md`
- **rc_translation STATUS**: `E:\opencell-worktrees\swarm-dead-rc_translation\STATUS_dead_request_calculator_translation.md`
- **Probe baseline** (200 ticks, seed 42): `E:\opencell\artifacts\probe_full_traces_20260526_190830\`
- **Karr 2012 MATLAB mirror**: `E:\opencell-mirrors\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\<Process>.m`
- **wcEcoli mirror**: `E:\opencell-mirrors\wcEcoli\models\ecoli\processes\`
- **Probe state machine summary**: `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\PROCESS_STATUS_ALL_29.md`
- **Companion CSV (per-process paths)**: `E:\opencell\PROCESS_ARTIFACT_INDEX.csv`

---

## Master index — 28 Karr processes

Legend: ✅ exists · ⚠️ partial/needs-check · ❌ missing/gap · 🟢 alive · 🔴 dead · 🟡 partial

| # | Process | Findings | STATUS | Karr ext | PB des | Fixture | Probe | Audit→PR | Deep STATUS |
|--:|---|:-:|:-:|:-:|:-:|:-:|:-:|---|---|
| 01 | Metabolism | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R08/L2→**A2**, S05/L1→def | — |
| 02 | ReplicationInitiation | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R15/L5→**A1** | — |
| 03 | Replication | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R14/L5→**A1** | — |
| 04 | DNADamage | ✅ | ✅ | ✅ | — | ✅ | 🟡 86/200 | R04/L2→**deferred** | — |
| 05 | DNARepair | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R05/L5→**A1** | — |
| 06 | DNASupercoiling | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R06/L3→**A4**, S07/L5→**A1** | — |
| 07 | ChromosomeCondensation | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R01/L5→**A1** | — |
| 08 | ChromosomeSegregation | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R02/L5→**A1** | — |
| 09 | Transcription | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R16/L2→**A2**, S03/L0→**A5** | — |
| 10 | TranscriptionalRegulation | ✅ | ✅ | ✅ | pb_turn3 | ✅ | 🟢 | (none) | — |
| 11 | RNAProcessing | ✅ | ✅ | ✅ | pb_turn4 | ✅ | 🔴 | R13/L5→**A1** + ID-fix | **Wave-1**: `swarm-dead-rna_processing` → (e) downstream gate (gene-ID vs TU-ID mismatch) |
| 12 | RNAModification | ✅ | ✅ | ✅ | pb_turn5 | ✅ | 🟡 1/200 | S10/L5→**A1** | — |
| 13 | RNADecay | ✅ | ✅ | ✅ | — | ✅ | 🟢 | (none) | — |
| 14 | tRNAAminoacylation | ✅ | ✅ | ✅ | pb_turn1 | ✅ | 🟡 1/200 | R18/L5→**A1** | — |
| 15 | Translation | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R17/L2→**A2**, S04/L0→**A5** | — |
| 16 | ProteinProcessingI | ✅ | ✅ | ✅ | pb_turn6 | ✅ | 🔴 | R12/L5→**A1** + seed-fix | **Wave-1**: `swarm-dead-protein_processing_i` → (c) wrong wiring; MG_106_DIMER not seeded in `protein.counts`; runtime-injection proof |
| 17 | ProteinProcessingII | ✅ | ✅ | ✅ | pb_turn7 | ✅ | 🔴 | S08/L5→**A1** | **Wave-2-v2**: 🟡 running (consolidator PID 33776) |
| 18 | ProteinModification | ✅ | ✅ | ✅ | pb_turn8 | ✅ | 🔴 | R11/L5→**A1** | **Wave-2-v2**: 🟡 running |
| 19 | ProteinFolding | ✅ | ✅ | ✅ | pb_turn9 | ✅ | 🟢 | R10/L5→**A1** | — |
| 20 | ProteinActivation | ✅ | ✅ | ✅ | pb_turn11 | ✅ | 🟢 | (none) | — |
| 21 | ProteinDecay | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R09/L2→**A3**, R19/L4→**A3** | **Wave-2-v2**: 🟡 running (decay_light variant) |
| 22 | ProteinTranslocation | ✅ | ✅ | ✅ | pb_turn10 | ✅ | 🔴 | S01/L3→**A4**, S09/L5→**A1** | **Wave-2-v2**: 🟡 running |
| 23 | MacromolecularComplexation | ✅ | ✅ | ✅ | — | ✅ | 🟢¹ | R07/L6→**A3**, S02/L4→**A3** | **Wave-2-v2**: 🟡 running (semantic-dead despite syntactic-alive) |
| 24 | RibosomeAssembly | ✅ | ✅ | ✅ | pb_turn2 | ✅ | 🔴 | (none in audit) | **Wave-2-v2**: 🟡 running |
| 25 | FtsZPolymerization | ✅ | ✅ | ✅ | — | ✅ | 🟢 | (none) | — |
| 26 | Cytokinesis | ✅ | ✅ | ✅ | — | ✅ | 🟢 | R03/L5→**A1** | — |
| 27 | HostInteraction | ✅ | ✅ | ✅ | — | ✅ | 🔴 | (none) | **GAP** — defer per audit-fire-moratorium decision |
| 28 | TerminalOrganelleAssembly | ✅ | ✅ | ✅ | — | ✅ | 🔴 | (none) | **GAP** — defer per audit-fire-moratorium decision |

¹ MacromolecularComplexation: probe reports 200/200 nonempty (passes syntactic check) but R07+S02 prove biologically zero (consume-with-zero-demand). The probe counts dict-length, not biology. Consolidator will reconcile.

## Request-calculator layer (8 Steps, not in 28-process taxonomy)

| Calculator | Probe | Verdict source | Verdict | Fix scope |
|---|:-:|---|---|---|
| request_calculator_metabolism | 🟢 | — | likely fine (A2 dependent) | — |
| request_calculator_transcription | 🟡¹ | **Wave-1** `swarm-dead-rc_transcription\STATUS_*.md` | **(b) Buggy** — `×Step.timestep=0` | 5–15 LOC, `karr_request_calculators.py` |
| request_calculator_translation | 🟡¹ | **Wave-2-v2 greenfield** `swarm-dead-rc_translation\STATUS_*.md` (commit 6165f99) | **(b) Buggy** — same pattern | 5–15 LOC, `karr_request_calculators.py:629` |
| request_calculator_trna | 🟡¹ | — | likely (b), same pattern | shared PR |
| request_calculator_rna_pathway | 🟡¹ | — | likely (b), same pattern | shared PR |
| request_calculator_protein_pathway | 🟡¹ | — | likely (b), same pattern | shared PR |
| request_calculator_ribasm | 🟡¹ | — | likely (b), same pattern | shared PR |
| request_calculator_pd | 🟡¹ | — | likely (b), same pattern | shared PR |
| request_calculator_d2 | 🟡¹ | — | likely (b), same pattern | shared PR |

¹ All RCs report 201/201 nonempty in probe but return `{wid: 0.0}` dicts. Probe drops zero leaves at CSV-write → header-only CSV. Same "syntactic-alive, semantic-dead" pattern as MacromolecularComplexation.

**Recommended consolidation**: ONE shared PR adding a `_safe_dt(self, timestep)` helper + applying it to all 8 RC sites. ~30 LOC total.

---

## Track-A PR rollup (from CONSOLIDATED_AUDIT_REPORT.md)

| PR | Scope | LOC | Processes touched |
|---|---|---|---|
| **A1** | L5 strict-zero contract — kill zero-grant helper fallbacks | 180–260 | 14 processes (ChromCond, ChromSeg, Cyto, DNARepair, DNASupercoil, RNAProc, RNAMod, tRNAAmino, Repl, ReplInit, PP1, PP2, PModif, PFold, PTransloc) |
| **A2** | L2 allocator enrollment for direct shared-substrate traffic | 220–320 | Metabolism, Transcription, Translation |
| **A3** | L4/L6 default-key / consume-with-zero-demand fixes | 120–200 | ProteinDecay, MacromolecularComplexation |
| **A4** | L3 resource-vector completeness (ATP→ATP+GTP+H2O) | 120–190 | DNASupercoil, ProteinTransloc |
| **A5** | L0 runtime-identity for TX/TL wrapper-vs-canonical class | 70–130 | Transcription, Translation |
| **RC-shared** | `_safe_dt` helper + 8 call-site fixes | ~30 | all 8 request_calculators |

Total: **740–1130 LOC across 6 PRs**.

---

## Wave-1 / Wave-2-v2 fired-session inventory

| Wave | Process | PID | Worktree | STATUS file | Verdict | Tokens |
|---|---|--:|---|---|---|--:|
| W1 | ProteinProcessingI | (completed) | swarm-dead-protein_processing_i | STATUS_dead_protein_processing_i.md (16 KB) | **(c) Wrong wiring** | ~? |
| W1 | RNAProcessing | (completed) | swarm-dead-rna_processing | STATUS_dead_rna_processing.md (13 KB) | **(e) Downstream gate** | 414K |
| W1 | RC-Transcription | (completed) | swarm-dead-rc_transcription | STATUS_dead_request_calculator_transcription.md (13 KB) | **(b) Buggy** | 190K |
| W2v2 | rc_translation | 4296 done | swarm-dead-rc_translation | STATUS_dead_request_calculator_translation.md (13 KB) | **(b) Buggy** | 180K |
| W2v2 | 7-process synthesis | **33776 running** | swarm-dead-consolidator | STATUS_dead_*_consolidated.md × 7 (pending) | TBD | budget 300K |

---

## True coverage gaps

Use this list to scope any future audit work:

1. **HostInteraction** — 0/200 probe, zero audit coverage. **DEFERRED** per moratorium decision (peripheral to E.2 central dogma).
2. **TerminalOrganelleAssembly** — 0/200 probe, zero audit coverage. **DEFERRED** per moratorium decision.
3. **DNADamage** — 86/200 probe. Likely Poisson (stochastic firing). **30-min triage**, not a full audit.
4. **RNAModification** — 1/200 probe. Likely downstream-gated by RNAProcessing. **30-min triage** after A1 lands.
5. **tRNAAminoacylation** — 1/200 probe. Likely downstream-gated by tRNA pipeline. **30-min triage** after A1 lands.

These 5 are the only legitimate reasons to fire any new audit work. Everything else routes to A1–A5 + RC-shared PR.

---

## Update protocol

When new artifacts land:
- Update the row in the master table (don't append new STATUS files separately)
- Cross-link any new STATUS file in the **Deep STATUS** column
- Refresh `PROCESS_ARTIFACT_INDEX.csv` from `scripts/...` (TBD; or rebuild via the powershell snippet at top of session)
- Bump the timestamp at the top of this file

Do NOT create more `STATUS_<purpose>.md` files in fresh worktrees unless this index can point to them as the canonical location for that process. The 477-file STATUS corpus exists because we stopped doing this.
