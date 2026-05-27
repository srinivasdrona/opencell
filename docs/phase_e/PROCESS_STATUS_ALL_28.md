# All-28 Process Status — 2026-05-26 20:19 IST

Coverage matrix across all 28 Karr M. genitalium processes + 8 request_calculators.
Format extends the wave-2 11-column coverage table.

## Legend

- **Probe state** from `E:\opencell\artifacts\probe_full_traces_20260526_190830\entity_call_stats.csv` (200 ticks, seed 42).
  - ✅ ALIVE = `nonempty_returns == 200`
  - ⚠️ PARTIAL = `1 ≤ nonempty < 200`
  - ❌ DEAD = `nonempty == 0`
- **Class-A** = `swarm-class-a-<P>` worktree exists with `findings.json` + `STATUS.md` (5–8 findings each)
- **PB design** = `docs/design/pb_turnN_<process>.md` exists
- **Audit row** = listed in `findings_index.csv` (R01–R19, S01–S10)
- **Karr fixture** = `data/karr_fixtures/per_process/<P>.json/.npz/.mat` exists
- **Wave-N verdict** = a–f taxonomy from DEAD_PROCESS_TEMPLATE
- **Next** = current routed workstream

## Master matrix — 28 Karr processes

| # | Process | Karr ext | PB des | Class-A | Audit (R/S) | Layer→PR | Karr fxt | Probe | Wave-1 verdict | Wave-2v2 | Next action |
|--:|---|:-:|:-:|:-:|---|---|:-:|:-:|---|:-:|---|
| 01 | Metabolism | ✅ | — | ✅ | R08, S05 | L2→**A2**, L1→def | ✅ | ✅ ALIVE | — | — | A2 PR |
| 02 | ReplicationInitiation | ✅ | — | ✅ | R15 | L5→**A1** | ✅ | ✅ ALIVE | — | — | A1 PR |
| 03 | Replication | ✅ | — | ✅ | R14 | L5→**A1** | ✅ | ✅ ALIVE | — | — | A1 PR |
| 04 | DNADamage | ✅ | — | ✅ | R04 | L2→deferred | ✅ | ⚠️ 86/200 | — | — | scope decision |
| 05 | DNARepair | ✅ | — | ✅ | R05 | L5→**A1** | ✅ | ✅ ALIVE | — | — | A1 PR |
| 06 | DNASupercoiling | ✅ | — | ✅ | R06, S07 | L3→**A4**, L5→**A1** | ✅ | ✅ ALIVE | — | — | A1+A4 PRs |
| 07 | ChromosomeCondensation | ✅ | — | ✅ | R01 | L5→**A1** | ✅ | ✅ ALIVE | — | — | A1 PR |
| 08 | ChromosomeSegregation | ✅ | — | ✅ | R02 | L5→**A1** | ✅ | ✅ ALIVE | — | — | A1 PR |
| 09 | Transcription | ✅ | — | ✅ | R16, S03 | L2→**A2**, L0→**A5** | ✅ | ✅ ALIVE | — | — | A2+A5 PRs |
| 10 | TranscriptionalRegulation | ✅ | pb_turn3 | ✅ | (none) | — | ✅ | ✅ ALIVE | — | — | Phase-B port |
| 11 | RNAProcessing | ✅ | pb_turn4 | ✅ | R13 | L5→**A1** | ✅ | ❌ DEAD | (e) downstream gate (gene-ID vs TU-ID) | — | A1 + ID fix |
| 12 | RNAModification | ✅ | pb_turn5 | ✅ | S10 | L5→**A1** | ✅ | ⚠️ 1/200 | — | — | A1 + downstream of RNAProcessing |
| 13 | RNADecay | ✅ | — | ✅ | (none) | — | ✅ | ✅ ALIVE | — | — | Phase-B port |
| 14 | tRNAAminoacylation | ✅ | pb_turn1 | ✅ | R18 | L5→**A1** | ✅ | ⚠️ 1/200 | — | — | A1; downstream of tRNA pipeline |
| 15 | Translation | ✅ | — | ✅ | R17, S04 | L2→**A2**, L0→**A5** | ✅ | ✅ ALIVE | — | — | A2+A5 PRs |
| 16 | ProteinProcessingI | ✅ | pb_turn6 | ✅ | R12 | L5→**A1** | ✅ | ❌ DEAD | **(c) wrong wiring** — MG_106_DIMER not seeded in protein.counts | — | A1 + seed fix |
| 17 | ProteinProcessingII | ✅ | pb_turn7 | ✅ | S08 | L5→**A1** | ✅ | ❌ DEAD | — | 🟡 **running (consolidator PID 33776)** | consolidator verdict |
| 18 | ProteinModification | ✅ | pb_turn8 | ✅ | R11 | L5→**A1** | ✅ | ❌ DEAD | — | 🟡 **running** | consolidator verdict |
| 19 | ProteinFolding | ✅ | pb_turn9 | ✅ | R10 | L5→**A1** | ✅ | ✅ ALIVE | — | — | A1 PR |
| 20 | ProteinActivation | ✅ | pb_turn11 | ✅ | (none) | — | ✅ | ✅ ALIVE | — | — | Phase-B port |
| 21 | ProteinDecay | ✅ | — | ✅ | R09, R19 | L2→**A3**, L4→**A3** | ✅ | ✅ ALIVE | — | 🟡 **running** (decay_light) | consolidator verdict |
| 22 | ProteinTranslocation | ✅ | pb_turn10 | ✅ | S01, S09 | L3→**A4**, L5→**A1** | ✅ | ❌ DEAD | — | 🟡 **running** | consolidator verdict |
| 23 | MacromolecularComplexation | ✅ | — | ✅ | R07, S02 | L6→**A3**, L4→**A3** | ✅ | ✅ ALIVE¹ | — | 🟡 **running** | consolidator verdict |
| 24 | RibosomeAssembly | ✅ | pb_turn2 | ✅ | (none) | — | ✅ | ❌ DEAD | — | 🟡 **running** | consolidator verdict |
| 25 | FtsZPolymerization | ✅ | — | ✅ | (none) | — | ✅ | ✅ ALIVE | — | — | Phase-B port |
| 26 | Cytokinesis | ✅ | — | ✅ | R03 | L5→**A1** | ✅ | ✅ ALIVE | — | — | A1 PR |
| 27 | HostInteraction | ✅ | — | ✅ | (none) | — | ✅ | ❌ DEAD | — | — | **GAP — no audit, no probe explanation** |
| 28 | TerminalOrganelleAssembly | ✅ | — | ✅ | (none) | — | ✅ | ❌ DEAD | — | — | **GAP — no audit, no probe explanation** |

¹ Probe reports 200/200 nonempty for MacromolecularComplexation but R07+S02 prove the requests are biologically zero (consume-with-zero-demand). The probe's "nonempty" check counts dict length, not biological liveness — so this passes a syntactic check while failing a semantic one. Consolidator will reconcile.

## Request-calculator status (separate layer)

| Calculator | Probe (calls/nonempty) | Wave-1 verdict | Wave-2v2 | Notes |
|---|---|---|:-:|---|
| request_calculator_metabolism | 201/201 | — | — | Likely alive; A2 dependency |
| request_calculator_transcription | 201/201 | **(b) Buggy** — demand × Step.timestep, dt can be 0 | — | Wave-1 STATUS in `swarm-dead-rc_transcription` |
| **request_calculator_translation** | 201/201 | — | 🟡 **running (PID 4296)** | Greenfield — primed with same timestep-zero hypothesis |
| request_calculator_trna | 201/201 | — | — | Likely same pattern; check after rc_translation lands |
| request_calculator_rna_pathway | 201/201 | — | — | Same |
| request_calculator_protein_pathway | 201/201 | — | — | Same |
| request_calculator_ribasm | 201/201 | — | — | Same |
| request_calculator_pd | 201/201 | — | — | Same |
| request_calculator_d2 | 201/201 | — | — | Same |

> Probe-level `nonempty=201` for these is misleading: they return a dict like `{"ATP": 0}` which counts as nonempty by dict-length but is biologically zero. RC-transcription wave-1 confirmed this. After rc_translation lands, decide whether to one-shot-fix all 7 remaining RCs as a single PR (likely 30-line shared guard).

## Verdict rollup

- **Probe-confirmed dead (8)**: ProteinProcessingI/II, ProteinModification, ProteinTranslocation, RibosomeAssembly, MacromolecularComplexation (semantic-dead), RNAProcessing, HostInteraction, TerminalOrganelleAssembly
- **Probe-partial (3)**: DNADamage, RNAModification, tRNAAminoacylation
- **Probe-alive (17)**: the rest
- **Wave-1 verdicts complete (3)**: PP1 (c), RNAProcessing (e), RC-transcription (b)
- **Wave-2 v2 running (8 total)**: 7 via consolidator + 1 greenfield rc_translation
- **Total covered after wave-2 v2 lands**: 3 (W1) + 8 (W2v2) = 11 deep STATUS; remaining 17 are covered by Track-A audit findings + Phase-B design docs

## Coverage gaps (true unknowns)

1. **HostInteraction**: 0/200 nonempty + no class-A findings + no audit row + no PB doc. Needs a dedicated wave-3 audit OR a "is this even wired into v6?" structural check.
2. **TerminalOrganelleAssembly**: same — 0/200 + zero coverage. Same recommendation.
3. **DNADamage 86/200**: not zero, not full — likely stochastic Poisson firing, but needs a 1-tick check.
4. **RNAModification 1/200, tRNAAminoacylation 1/200**: probably one-shot-at-init, but needs confirmation. Both have S10 (RNAModification) coverage; tRNA has R18.
5. **6 processes with no audit row**: TranscriptionalRegulation, RNADecay, ProteinActivation, RibosomeAssembly, FtsZPolymerization, HostInteraction, TerminalOrganelleAssembly. Most are alive and Phase-B-design-doc'd; the dead ones (RibosomeAssembly, HostInteraction, TerminalOrganelleAssembly) are the real gaps.

## Wave-3 — does it need to exist?

**Argument against (currently leading):**
- 22/28 processes are routed: Track-A PRs A1–A5 cover the 17 audit-confirmed findings; consolidator+rc_translation cover the 8 truly-dead ones.
- A "wave-3 fresh audit" would re-derive what's already in `findings.json` files (same mistake we made with wave-2).

**Argument for a small wave-3:**
- HostInteraction + TerminalOrganelleAssembly + RibosomeAssembly are dead and have no audit row. RibosomeAssembly is in W2v2 consolidator (has class-A); HostInteraction + TerminalOrganelleAssembly are truly bare.
- These two are biologically peripheral to E.2's central dogma (TX → TL → folding → modification) — they may be safely deferred to a later milestone.

**Recommendation**: NO wave-3. Instead:
1. Let consolidator + rc_translation land (~60–90 min).
2. Open one 30-min triage task per probe-partial process (DNADamage, RNAModification, tRNAAminoacylation) to confirm "one-shot-at-init" hypothesis.
3. Mark HostInteraction + TerminalOrganelleAssembly as **explicitly deferred** with rationale in DECISIONS.md.
4. Execute Track-A PRs (A1–A5) — that's the scaling step we've been deferring.

## Source artifacts

- `findings_index.csv` (30 rows, R01–R19 + S01–S10): `E:\opencell-worktrees\p3-karr-light-docstrings\opencell\validation\swarm\consolidated\findings_index.csv`
- `CONSOLIDATED_AUDIT_REPORT.md` (Track-A PR scope): same dir
- `entity_call_stats.csv` (probe baseline): `E:\opencell\artifacts\probe_full_traces_20260526_190830\`
- 28 Karr extracts: `E:\opencell-worktrees\p3-karr-light-docstrings\docs\karr_extracts\process\`
- 11 PB design docs: `E:\opencell-worktrees\p3-karr-light-docstrings\docs\design\pb_turn*.md`
- 28 class-A worktrees: `E:\opencell-worktrees\swarm-class-a-*\`
- 28 Karr fixtures (json/npz/mat): `E:\opencell-worktrees\p3-karr-light-docstrings\data\karr_fixtures\per_process\`
- Wave-1 STATUS files (3): `E:\opencell-worktrees\swarm-dead-{protein_processing_i,rna_processing,rc_transcription}\`
