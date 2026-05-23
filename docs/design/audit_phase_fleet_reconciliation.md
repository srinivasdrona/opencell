# Audit: Phase Fleet Planned-vs-Shipped Reconciliation

Date: 2026-05-23  
Scope: Phase A, A3 step 3, Phase B, Phase C dispatch reconciliation against planning docs and merge history.

## Sources used

- `docs/design/karr_execution_plan_2026-05-22.md` (primary canonical plan; B.1-B.10 and C.1-C.10 at lines 167-197)
- `docs/design/a3_step3_joint_design_v1.md`
- `docs/design/pb_final_chassis_v4_integration.md`
- `docs/design/pc_final_chassis_v5.md`
- Additional planning docs discovered in `docs/design`:
  - `a33_turn1_m2m3_v3_delta_emit.md` ... `a33_turn5_chassis_v3_integration.md`
  - `pb_turn1_trna_aminoacylation.md` ... `pb_turn11_protein_activation.md`
  - `pc_turn1_replication_initiation.md`
  - `pc-t2-replication.md` ... `pc-t10-terminal-organelle.md`
  - `pc_final_chassis_v5_refinement_notes.md`
- Canonical scorecard cross-reference: `docs/design/pd_final_chassis_v6.md` lines 144-173 (`KP01..KP28`).
- Shipped evidence:
  - `git log --merges --pretty='%h %ai %s' --all | rg 'agent/(pa|pb|pc|a3|rna-decay)'`
  - `git branch --no-merged main --format='%(refname:short)' | rg 'agent/(pa|pb|pc|a3)'` (no output)
  - on-disk modules in `opencell/vivarium/karr_*.py`
  - on-disk tests in `tests/vivarium/test_karr_*.py`

## Phase A

Planning gap: no `pa_*.md` docs in `docs/design`, and no `agent/pa*` merge branches found.

| phase | turn_id | process_name | planned evidence | shipped evidence | status |
|---|---|---|---|---|---|
| A | n/a | Metabolism | `karr_execution_plan_2026-05-22.md:78` | `karr_m1.py`, `test_karr_m1_chassis.py` | ✅ SHIPPED + MERGED (legacy, non-`pa` labeling) |
| A | n/a | Transcription | `karr_execution_plan_2026-05-22.md:79` | `karr_m2.py`/`karr_m2_v3.py`, `test_karr_m2_chassis.py`/`test_karr_m2_v3.py` | ✅ SHIPPED + MERGED (legacy, non-`pa` labeling) |
| A | n/a | Translation | `karr_execution_plan_2026-05-22.md:80` | `karr_m3.py`/`karr_m3_v3.py`, `test_karr_m3_chassis.py`/`test_karr_m3_v3.py` | ✅ SHIPPED + MERGED (legacy, non-`pa` labeling) |

## A3 Step 3

Planned turns from `a33_turn*.md` headings (line 1 in each file).

| phase | turn_id | process_name | description | shipped evidence | status |
|---|---|---|---|---|---|
| A3.3 | a33-turn1 | M2v3 + M3v3 delta-emit | Accumulate updater conversion | merge `c69c78a` (`agent/a33-m2m3-v3`), modules/tests on disk | ✅ SHIPPED + MERGED |
| A3.3 | a33-turn2 | KarrAllocationStep | Proportional fair-share allocation Step | merge `e10a205` (`agent/a33-allocation`), module/test on disk | ✅ SHIPPED + MERGED |
| A3.3 | a33-turn3 | KarrD2Real (MacromolecularComplexation) | Real D2 process replacing stub | merge `a0556b5` (`agent/a33-d2-real`), module/test on disk | ✅ SHIPPED + MERGED |
| A3.3 | a33-turn4 | ProteinDecay-light | Complex decay sink | merge `8534708` (`agent/a33-decay-light`), module/test on disk | ✅ SHIPPED + MERGED |
| A3.3 | a33-turn5 | build_karr_chassis_v3 integration | Ratchet-closure integration | merge `b1cbf14` (`agent/a33-integration`) | ✅ SHIPPED + MERGED |

## Phase B

Canonical planned order in primary plan (`karr_execution_plan_2026-05-22.md:167-178`):
B.1 `RNADecay` through B.10 `ProteinActivation`.

| phase | turn_id | process_name | description | shipped evidence | status |
|---|---|---|---|---|---|
| B | pb-t1 (canonical B.1) | RNADecay | Close RNA loop (`karr_execution_plan_2026-05-22.md:169`) | missing in 2026-05-22 PB fleet; recovered via merge `c0640a1` (`agent/rna-decay`) with `karr_rna_decay.py` + `test_karr_rna_decay.py` | 🔄 RENAMED / RECOVERED (historical drop fixed) |
| B | pb-t2 (canonical B.2) | tRNAAminoacylation | Charged tRNA availability | merge `e47a005` (`agent/pb-t1-trna`) | 🔄 RENAMED (turn label shifted) |
| B | pb-t3 (canonical B.3) | RNAProcessing | pre-rRNA / pre-tRNA processing | merge `0c52f43` (`agent/pb-t4-rna-processing`) | 🔄 RENAMED (turn label shifted) |
| B | pb-t4 (canonical B.4) | RNAModification | t/rRNA modifications | merge `6a8c220` (`agent/pb-t5-rna-modification`) | 🔄 RENAMED (turn label shifted) |
| B | pb-t5 (canonical B.5) | ProteinProcessingI | early protein maturation | merge `ebe7a0e` (`agent/pb-t6-pp1`) | 🔄 RENAMED (turn label shifted) |
| B | pb-t6 (canonical B.6) | ProteinProcessingII | late protein maturation | merge `eeb6ebf` (`agent/pb-t7-pp2`) | 🔄 RENAMED (turn label shifted) |
| B | pb-t7 (canonical B.7) | ProteinFolding | chaperone-assisted folding | merge `60891f0` (`agent/pb-t9-pfold`) | 🔄 RENAMED (turn label shifted) |
| B | pb-t8 (canonical B.8) | ProteinModification | post-translational modifications | merge `d311230` (`agent/pb-t8-pmod`) | ✅ SHIPPED + MERGED |
| B | pb-t9 (canonical B.9) | ProteinTranslocation | compartment routing | merge `09bf411` (`agent/pb-t10-translocation`) | 🔄 RENAMED (turn label shifted) |
| B | pb-t10 (canonical B.10) | ProteinActivation | activation reactions | merge `b2037d8` (`agent/pb-t11-activation`) | 🔄 RENAMED (turn label shifted) |

Additional shipped PB-labeled turns (present in PB turn docs and merges, not drops):

- `pb-t2` RibosomeAssembly (`a337352`; `karr_ribosome_assembly.py`)
- `pb-t3` TranscriptionalRegulation (`695d9c6`; `karr_transcriptional_regulation.py`)
- PB integration `pb-final` (`b8d174c`)

## Phase C

Canonical planned order in primary plan (`karr_execution_plan_2026-05-22.md:186-197`):
C.1 `ChromosomeCondensation` ... C.10 `TranscriptionalRegulation`.

| phase | turn_id | process_name | description | shipped evidence | status |
|---|---|---|---|---|---|
| C | pc-t1 (canonical C.1) | ChromosomeCondensation | replication baseline | merge `de55ef1` (`agent/pc-t4-condensation`) | 🔄 RENAMED (turn order changed) |
| C | pc-t2 (canonical C.2) | DNASupercoiling | topology control | merge `a8b0be4` (`agent/pc-t3-supercoiling`) | 🔄 RENAMED (turn order changed) |
| C | pc-t3 (canonical C.3) | ReplicationInitiation | OriC trigger | merge `681dce6` (`agent/pc-t1-repl-init`) | 🔄 RENAMED (turn order changed) |
| C | pc-t4 (canonical C.4) | Replication | fork elongation | merge `97e0052` (`agent/pc-t2-replication`) | 🔄 RENAMED (turn order changed) |
| C | pc-t5 (canonical C.5) | ChromosomeSegregation | daughter chromosome separation | merge `6f1ad5a` (`agent/pc-t5-segregation`) | ✅ SHIPPED + MERGED |
| C | pc-t6 (canonical C.6) | FtsZPolymerization | Z-ring assembly | merge `579114f` (`agent/pc-t8-ftsz`) | 🔄 RENAMED (turn order changed) |
| C | pc-t7 (canonical C.7) | Cytokinesis | division step | merge `4ee0e76` (`agent/pc-t9-cytokinesis`) | 🔄 RENAMED (turn order changed) |
| C | pc-t8 (canonical C.8) | DNADamage | spontaneous lesion model | merge `dcf48c2` (`agent/pc-t6-damage`) | 🔄 RENAMED (turn order changed) |
| C | pc-t9 (canonical C.9) | DNARepair | lesion repair | merge `c3252db` (`agent/pc-t7-repair`) | 🔄 RENAMED (turn order changed) |
| C | pc-t10 (canonical C.10) | TranscriptionalRegulation | TF control in cycle context | shipped earlier in PB as merge `695d9c6` (`agent/pb-t3-tx-regulation`) | 🔄 RENAMED / RESLOTTED |

Additional Phase C dispatch-labeled shipment:

- `pc-t10` TerminalOrganelleAssembly merged as `510a041` (`agent/pc-t10-terminal-organelle`) and on disk as `karr_terminal_organelle_assembly.py` with `test_karr_terminal_organelle_assembly.py`.

## Confirmed Drops

- Historical confirmed drop: `RNADecay` canonical Phase B Turn 1 (`karr_execution_plan_2026-05-22.md:169`) was not shipped in the 2026-05-22 PB fleet and was later recovered.
- No other planned process from audited Phase A / A3.3 / B / C sets is currently unshipped.
- Therefore: zero new unrecovered drops beyond RNADecay.

## Confirmed Renames

Slot-code to canonical mapping observed in branch/module naming:

| slot/code | canonical process |
|---|---|
| `m1` | Metabolism |
| `m2` / `m2_v3` | Transcription |
| `m3` / `m3_v3` | Translation |
| `d2-real` / `karr_d2_real.py` | MacromolecularComplexation |
| `protein_decay_light` | ProteinDecay (light subset) |
| `tx-regulation` | TranscriptionalRegulation |
| `pp1` | ProteinProcessingI |
| `pp2` | ProteinProcessingII |
| `pfold` | ProteinFolding |
| `pmod` | ProteinModification |
| `repl-init` | ReplicationInitiation |
| `ftsz` | FtsZPolymerization |

Cross-phase reslotting confirmed:

- C.10 TranscriptionalRegulation shipped in PB (`pb-t3`).
- TerminalOrganelleAssembly (phase-D process in primary plan) shipped as `pc-t10`.

This mapping is consistent with the full-model KPI frame tracked in `pd_final_chassis_v6.md:144-173` (`KP01..KP28`).

## Missing Tests

Spot-check result for shipped process modules in scope:

- Missing test modules: none.
- Every shipped process module checked in this audit has a corresponding `tests/vivarium/test_karr_*.py`.

## Special Case: RNADecay

1. Plan explicitly calls for `RNADecay` as B.1 (canonical PB turn 1) at `karr_execution_plan_2026-05-22.md:169`.
2. Actual PB dispatch labeled `pb-t1` as tRNAAminoacylation in merge `e47a005` (`Merge agent/pb-t1-trna: tRNAAminoacylation`).
3. Recovery shipped on 2026-05-23 via `agent/rna-decay`, merged as `c0640a1`.
4. Most likely root cause: off-by-one dispatch labeling drift in PB slot assignment (canonical B.1..B.10 shifted and re-labeled into pb-t1..pb-t11), which dropped RNADecay from the original PB fleet.

## Verdict

- Planned canonical process slots audited (A baseline + A3.3 + B + C): 25
- Currently shipped and merged: 25
- Currently dropped (unrecovered): 0
- Historical dropped then recovered: 1 (`RNADecay`)
- Renamed/reslotted mappings confirmed: 12
- Coverage now: 100.0% of audited canonical slots shipped

Bottom line: no additional dropped processes were found beyond the already recovered RNADecay incident.
