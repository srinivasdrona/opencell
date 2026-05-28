# MATLAB File Manifest + Coverage Map (Phase E)

Generated: 2026-05-27 (IST)  
Authoring scope: read-only inventory + coverage mapping, no source/test/script edits.

This manifest reconciles two on-disk locations:

| Scope | Path | Notes |
|---|---|---|
| Canonical MATLAB corpus (full) | `E:\opencell\data\m1_sources\` | Full `karr_native`, `WholeCell` (symlink), `WholeCellKB`, supplements. |
| This docs worktree (sparse mirror + extracted fixtures) | `E:\opencell-worktrees\docs-matlab-manifest\data\` | `m1_sources` is sparse here; flattened fixtures/replay archives are present. |

## 1. Inventory (sizes, paths, file classes)

### 1.1 Canonical `m1_sources` inventory (verified)

| Category | Canonical path | Files | Size | Notes |
|---|---|---:|---:|---|
| Karr native `.mat` | `E:\opencell\data\m1_sources\karr_native\**\*.mat` | 58 | 118.66 MB | Includes `cell_cycle_trajectory.mat`, `fitted_constants.mat`, 23 init files, 28 trace files, 5 backup traces. |
| Karr flat `.mat` | `E:\opencell\data\m1_sources\karr_flat\*.mat` | 1 | 0.03 MB | `metabolism_dynamics.mat` only. |
| WholeCell `.m` source | `E:\opencell\data\m1_sources\WholeCell\**\*.m` | 538 | 7.07 MB | `WholeCell` is symlinked to `E:\opencell-mirrors\WholeCell`. |
| WholeCell `.mat` | `E:\opencell\data\m1_sources\WholeCell\**\*.mat` | 55 | 74.01 MB | 28 process fixtures, 16 state fixtures, simulation/KB mats, 1 m2html mat. |
| WholeCell MEX binaries | `E:\opencell\data\m1_sources\WholeCell\**\*.mex*` | 7 | 2.863 MB | Linux/macOS/Windows binaries present. |
| WholeCellKB export | `E:\opencell\data\m1_sources\WholeCellKB\**\*` | 262 | 22.096 MB | HTML/SQL/assets export; includes queryable SQL dump. |
| Suthers 2009 supplements | `E:\opencell\data\m1_sources\suthers2009_s00*` | 5 | 0.25 MB | 4 OLE/BIFF-style files + 1 ZIP-based workbook signature. |
| Karr 2012 supplements | `E:\opencell\data\m1_sources\karr2012_supplement_0*` | 3 | 0.01 MB | Placeholder HTML stubs, not real spreadsheets. |

### 1.2 Worktree-local MATLAB fixtures/sources (not part of canonical `m1_sources`)

| Category | Worktree path | Files | Size | Notes |
|---|---|---:|---:|---|
| Flattened per-process/state fixtures (`*_flat.mat`) | `data/karr_fixtures/per_process/*.mat` | 44 | 12.72 MB | 28 process + 16 state flattened fixtures. |
| Legacy class fixture mats | `data/karr_fixtures/{Host,MetabolicReaction,Time}.mat` | 3 | 0.01 MB | MCOS/opaque class-instance mats. |
| Replay traces (`.npz`) | `data/karr_fixtures/per_process_replay/*.npz` | 37 | 0.209 MB | 28 process replay npz + trajectory/flat-derived extras. |
| Replay manifests (`.json`) | `data/karr_fixtures/per_process_replay/*.json` | 28 | 0.009 MB | Includes source `.mat` provenance paths. |
| Python-native Karr archive | `data/karr_archive/*` | 7 | 2.301 MB | `npz` + string/manifest JSONs + full inventory docs. |
| OpenCell MATLAB scripts | `scripts/matlab/*.m` | 18 | 0.10 MB | Extraction/bootstrap scripts in this repo. |
| Mirrored MATLAB source snippets | `data/karr_fixtures/m_source/*.m` | 6 | 0.02 MB | Select classes used by fixture generation/interpretation. |

### 1.3 Karr native trajectory + initial states

| Subset | Path | Files | Size | Notes |
|---|---|---:|---:|---|
| Cell-cycle trajectory | `E:\opencell\data\m1_sources\karr_native\cell_cycle_trajectory.mat` | 1 | 100.29 MB | Single seed/file currently on disk. |
| Fitted constants | `E:\opencell\data\m1_sources\karr_native\fitted_constants.mat` | 1 | 15.7 KB | Present. |
| Per-process init states | `E:\opencell\data\m1_sources\karr_native\initial_states\*_init.mat` | 23 | 0.36 MB | Expected 28 for 1:1 process coverage; missing 5. |

Expected-by-process init-state gaps (23/28 present):
- `ChromosomeCondensation`
- `DNASupercoiling`
- `ReplicationInitiation`
- `Transcription`
- `Translation`

### 1.4 Karr per-process traces

| Subset | Path | Files | Size | Notes |
|---|---|---:|---:|---|
| Main per-process traces | `E:\opencell\data\m1_sources\karr_native\per_process_traces\*_100ticks.mat` | 28 | 17.91 MB | One file per process name exists. |
| Truncated backup traces | `E:\opencell\data\m1_sources\karr_native\per_process_traces\_truncated_backup\*_100ticks.mat` | 5 | 0.083 MB | Byte-identical duplicates of the same 5 tiny main files. |

Truncated backup set (5):
- `RNADecay_100ticks.mat`
- `ReplicationInitiation_100ticks.mat`
- `Replication_100ticks.mat`
- `Transcription_100ticks.mat`
- `Translation_100ticks.mat`

Full-fidelity/non-truncated traces (23):
- `ChromosomeCondensation`, `ChromosomeSegregation`, `Cytokinesis`, `DNADamage`, `DNARepair`, `DNASupercoiling`, `FtsZPolymerization`, `HostInteraction`, `MacromolecularComplexation`, `Metabolism`, `ProteinActivation`, `ProteinDecay`, `ProteinFolding`, `ProteinModification`, `ProteinProcessingI`, `ProteinProcessingII`, `ProteinTranslocation`, `RNAModification`, `RNAProcessing`, `RibosomeAssembly`, `TerminalOrganelleAssembly`, `TranscriptionalRegulation`, `tRNAAminoacylation`.

Missing trace files from the 28-process set: none.

### 1.5 WholeCell `.m` source coverage by directory

| Directory | `.m` count | Size |
|---|---:|---:|
| `...\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process` | 28 | 966.4 KB |
| `...\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+state` | 16 | 338.5 KB |
| `...\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+analysis` | 37 | 1402.3 KB |
| `...\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+util` | 18 | 422.0 KB |
| `...\WholeCell\src\+edu\+stanford\+covert\+cell\+kb` | 32 | 370.8 KB |
| `...\WholeCell\src\+edu\+stanford\+covert\+util` | 19 | 227.8 KB |
| `...\WholeCell\src_test\+edu\+stanford\+covert\+cell\+sim\+process` | 28 | 1161.0 KB |
| `...\WholeCell\src_test\+edu\+stanford\+covert\+cell\+sim\+state` | 16 | 128.7 KB |

Process class files present (28/28):  
`ChromosomeCondensation.m`, `ChromosomeSegregation.m`, `Cytokinesis.m`, `DNADamage.m`, `DNARepair.m`, `DNASupercoiling.m`, `FtsZPolymerization.m`, `HostInteraction.m`, `MacromolecularComplexation.m`, `Metabolism.m`, `ProteinActivation.m`, `ProteinDecay.m`, `ProteinFolding.m`, `ProteinModification.m`, `ProteinProcessingI.m`, `ProteinProcessingII.m`, `ProteinTranslocation.m`, `Replication.m`, `ReplicationInitiation.m`, `RibosomeAssembly.m`, `RNADecay.m`, `RNAModification.m`, `RNAProcessing.m`, `TerminalOrganelleAssembly.m`, `Transcription.m`, `TranscriptionalRegulation.m`, `Translation.m`, `tRNAAminoacylation.m`.

### 1.6 WholeCell `.mat` files (canonical)

| Folder | `.mat` count | Size | Typical contents |
|---|---:|---:|---|
| `...\WholeCell\src_test\...\process\fixtures` | 28 | 39.25 MB | Per-process MCOS fixtures. |
| `...\WholeCell\src_test\...\state\fixtures` | 16 | 12.80 MB | Per-state MCOS fixtures. |
| `...\WholeCell\data` | 7 | 15.85 MB | `Simulation_fitted*.mat`, `knowledgeBase.mat`. |
| `...\WholeCell\src_test\...\sim\fixtures` | 3 | 6.07 MB | Simulation fixture mats. |
| `...\WholeCell\lib\m2html-1.5\private` | 1 | 0.05 MB | Toolbar image matrix. |

Files >2 MB (loadmat probe intentionally skipped):
- `E:\opencell\data\m1_sources\karr_native\cell_cycle_trajectory.mat`
- `E:\opencell\data\m1_sources\WholeCell\data\knowledgeBase.mat`
- `E:\opencell\data\m1_sources\WholeCell\data\Simulation_fitted.mat`
- `E:\opencell\data\m1_sources\WholeCell\data\Simulation_fitted-R2120.mat`
- `E:\opencell\data\m1_sources\WholeCell\data\Simulation_fitted-R2139.mat`
- `E:\opencell\data\m1_sources\WholeCell\data\Simulation_fitted-R2163.mat`
- `E:\opencell\data\m1_sources\WholeCell\data\Simulation_fitted-R2395.mat`
- `E:\opencell\data\m1_sources\WholeCell\data\Simulation_fitted-R2576.mat`
- `E:\opencell\data\m1_sources\WholeCell\src_test\+edu\+stanford\+covert\+cell\+sim\fixtures\Simulation.mat`
- `E:\opencell\data\m1_sources\WholeCell\src_test\+edu\+stanford\+covert\+cell\+sim\fixtures\Simulation_EndOfCellCycle.mat`
- `E:\opencell\data\m1_sources\WholeCell\src_test\+edu\+stanford\+covert\+cell\+sim\fixtures\Simulation_FitGrowthRate.mat`

### 1.7 WholeCell MEX binaries

| Extension | Count | Size | Platform signal |
|---|---:|---:|---|
| `.mexa64` | 2 | 1.25 MB | Linux x86_64 |
| `.mexglx` | 1 | 0.11 MB | Legacy Linux x86 |
| `.mexmaci64` | 1 | 0.88 MB | macOS x86_64 |
| `.mexw64` | 3 | 0.63 MB | Windows x64 |

### 1.8 WholeCellKB export (queryable sample)

- Path: `E:\opencell\data\m1_sources\WholeCellKB\`
- Total files: 262 (22.096 MB)
- Queryable SQL dump: `public/fixtures/data.sql`
- Verified table presence for TU/gene relations:
  - `public_transcriptionunit`
  - `public_transcriptionunit_genes`
  - `public_gene`
  - `public_transcriptionalregulation`

### 1.9 Suthers 2009 supplements

| File | Size | Signature check | Verdict |
|---|---:|---|---|
| `suthers2009_s001` | 145,920 | `D0 CF 11 E0 ...` | OLE/BIFF container (legacy Excel-like). |
| `suthers2009_s002` | 29,696 | `D0 CF 11 E0 ...` | OLE/BIFF container (legacy Excel-like). |
| `suthers2009_s003` | 50,176 | `D0 CF 11 E0 ...` | OLE/BIFF container (legacy Excel-like). |
| `suthers2009_s004` | 19,456 | `D0 CF 11 E0 ...` | OLE/BIFF container (legacy Excel-like). |
| `suthers2009_s005` | 17,274 | `50 4B 03 04 ...` | ZIP-based workbook container (`.xlsx`-style). |

### 1.10 Karr 2012 published supplements (placeholder verification)

| File | Size | First-200-byte signal | Verdict |
|---|---:|---|---|
| `karr2012_supplement_01.xls` | 1,814 | Starts with `....<html>...Preparing to download...` | Placeholder/stub, not real XLS payload. |
| `karr2012_supplement_02.xls` | 1,817 | Starts with `....<html>...Preparing to download...` | Placeholder/stub, not real XLS payload. |
| `karr2012_supplement_03.xlsx` | 1,817 | Starts with `....<html>...Preparing to download...` | Placeholder/stub, not real XLSX payload. |

### 1.11 OpenCell-side `scripts/matlab/*.m` (one-line each)

| Script | Description |
|---|---|
| `extract_cell_cycle_trajectory.m` | Runs a full Karr WCM cell-cycle reference trajectory extraction. |
| `extract_fitted_constants.m` | Dumps `fitConstants()` output to `fitted_constants.mat`. |
| `extract_initial_states.m` | Captures per-process `initializeState()` snapshots. |
| `extract_karr_m1_dynamics.m` | Extracts dynamic metabolism bound/flux fixtures for M1 validation. |
| `extract_karr_m2v2.m` | Extracts M2v2 transcription/RNAP/TU mapping inputs. |
| `extract_karr_m3v2.m` | Extracts M3v2 translation/ribosome inputs. |
| `extract_karr_mats.m` | Generic WholeCell `.mat` deserializer to scipy-readable MAT v7 structs. |
| `extract_karr_targeted.m` | Pulls targeted M1-relevant subsets from heavy simulation/KB mats. |
| `extract_m3_metabolite_vocab.m` | Exports metabolite vocabulary for `ProteinMonomer.baseCounts` columns. |
| `extract_per_process_fixtures.m` | Flattens 28 process + 16 state MCOS fixture mats. |
| `extract_per_process_traces.m` | Captures frozen-input per-process evolveState traces. |
| `extract_per_process_traces_batch_a.m` | Batch A (processes 1-7). |
| `extract_per_process_traces_batch_b.m` | Batch B (processes 8-14). |
| `extract_per_process_traces_batch_c.m` | Batch C (processes 15-21, protein pipeline). |
| `extract_per_process_traces_batch_d.m` | Batch D (processes 22-28). |
| `extract_protein_complexes.m` | Extracts full protein-complex composition from `knowledgeBase.mat`. |
| `karr_bootstrap.m` | Shared WholeCell simulation bootstrap helper for MATLAB extractors. |
| `regenerate_metabolism_dynamics.m` | Rebuilds `metabolism_dynamics.mat` perturbation oracle. |

### 1.12 OpenCell-side `data/karr_fixtures/m_source/*.m` (one-line each)

| File | Description |
|---|---|
| `CellStateFixture.m` | Class for generating CellState fixture files. |
| `CircularSparseMat.m` | Circular sparse matrix wrapper over SparseMat with index wrapping. |
| `Host.m` | WholeCell `State_Host` state class source. |
| `MetabolicReaction.m` | WholeCell `State_MetabolicReaction` state class source. |
| `Parameter.m` | Knowledge-base parameter class definition. |
| `Time.m` | WholeCell `State_Time` class source. |

### 1.13 `scipy.io.loadmat` probes for all `.mat` files under 2 MB

Probe command family used (WSL venv only):

```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && python -c \"from scipy.io import loadmat; d=loadmat('<path>'); print(sorted(d.keys()))\""
```

Totals:
- Under-2MB `.mat` files probed: **150**
- Above-2MB `.mat` files skipped (size-only listed): **11**
- Distinct probe signatures observed: **4**

| File set (all files in set were probed) | Count | Top-level keys + dtype signature |
|---|---:|---|
| Canonical `karr_native` under-2MB mats + canonical `karr_flat/metabolism_dynamics.mat` | 58 | `ERROR NotImplementedError: Please use HDF reader for matlab v7.3 files, e.g. h5py` |
| WholeCell process/state fixture mats + worktree `{Host,MetabolicReaction,Time}.mat` | 47 | `None:MatlabOpaque[dtype=[('s0','O'),('s1','O'),('s2','O'),('arr','O')]]; __function_workspace__:ndarray[dtype=uint8]; __globals__:list; __header__:bytes; __version__:str` |
| Worktree flattened fixture mats `data/karr_fixtures/per_process/*_flat.mat` | 44 | `__globals__:list; __header__:bytes; __version__:str; data:ndarray[dtype=[('fixture','O')]]` |
| `WholeCell/lib/m2html-1.5/private/m2htmltoolbarimages.mat` | 1 | `__globals__, __header__, __version__, helpIcon/newIcon/onIcon/openIcon/printIcon/saveAsIcon/saveIcon/webIcon/wheelIcon` all `ndarray[dtype=float64]` |

Per-set file membership (for per-file coverage proof):
- 58-file v7.3 set = `fitted_constants.mat` + 23 `initial_states/*_init.mat` + 28 `per_process_traces/*_100ticks.mat` + 5 `_truncated_backup/*_100ticks.mat` + `karr_flat/metabolism_dynamics.mat`.
- 47-file MatlabOpaque set = 28 WholeCell process fixture mats + 16 WholeCell state fixture mats + worktree `data/karr_fixtures/{Host,MetabolicReaction,Time}.mat`.
- 44-file flattened set = worktree `data/karr_fixtures/per_process/*.mat` (28 process flat mats + 16 state flat mats).

## 2. Coverage Map (work-stream -> file)

| Stream | Need | On disk? | Path | Sufficient? |
|---|---|---|---|---|
| RNAProcessing TX-architecture refactor | gene->TU composition mapping | Yes | `data/karr_archive/{karr_archive.npz,karr_archive_manifest.json}` (`rnas_targeted.kb_gene_to_tu_index`, `kb_tu_to_gene_indices`, TU IDs) | Partial: mapping and IDs are present, but not full TU sequence/type labels in one direct field. |
| RNAProcessing TX-architecture refactor | TU sequences + TU type labels (mRNA/rRNA/sRNA/tRNA) | Partial | `E:\opencell\data\m1_sources\WholeCellKB\public\fixtures\data.sql` (`public_transcriptionunit`, `public_transcriptionunit_genes`, `public_gene`) | Partial: derivable from SQL export + joins; not pre-extracted as a ready single matrix in archive. |
| RNAProcessing TX-architecture refactor | `RNAProcessing.m` source (matrix-update logic around reported lines) | Yes | `E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\RNAProcessing.m` | Yes. |
| Track-F PP2 triage | enzyme list + initial counts | Yes | `data/karr_fixtures/per_process/ProteinProcessingII_flat.mat`, `data/karr_fixtures/per_process/ProteinProcessingII.npz` (`fixture__enzymes`, `fixture__boundEnzymes`) | Yes. |
| Track-F PP2 triage | reference 100-tick trace | Yes | `E:\opencell\data\m1_sources\karr_native\per_process_traces\ProteinProcessingII_100ticks.mat` (1,938,368 bytes), plus `data/karr_fixtures/per_process_replay/ProteinProcessingII.npz` | Yes: not in `_truncated_backup`, full-sized main trace exists. |
| Track-F ProteinModification triage | enzyme list + reaction stoichiometry | Yes | `data/karr_fixtures/per_process/ProteinModification_flat.mat`, `data/karr_fixtures/per_process/ProteinModification.npz` (`fixture__enzymes`, `fixture__reactionStoichiometryMatrix`) | Yes. |
| Track-F ProteinModification triage | reference 100-tick trace | Yes | `E:\opencell\data\m1_sources\karr_native\per_process_traces\ProteinModification_100ticks.mat` (1,957,616 bytes), plus replay npz | Yes: full trace present, not backup-only. |
| 28-process fidelity scorecard | 100-tick trace for all 28 processes | Partial | `E:\opencell\data\m1_sources\karr_native\per_process_traces\` | Partial: 28 named files exist, but 5 are tiny/truncated and mirrored in `_truncated_backup`. |
| 28-process fidelity scorecard | per-process init state | Partial | `E:\opencell\data\m1_sources\karr_native\initial_states\*_init.mat` | Partial: 23/28 present; missing 5 (`ChromosomeCondensation`, `DNASupercoiling`, `ReplicationInitiation`, `Transcription`, `Translation`). |
| 28-process fidelity scorecard | replay-ready alternatives in worktree | Partial | `data/karr_fixtures/per_process_replay/*.npz` | Partial: 27/28 replay npz non-empty; `ProteinDecay.npz` is empty (22 bytes). |
| Ensemble statistical validation | multiple-seed `cell_cycle_trajectory` runs | No | Only `E:\opencell\data\m1_sources\karr_native\cell_cycle_trajectory.mat` found | No: single trajectory file only. |

## 3. Gap Analysis — what genuinely requires a MATLAB license

### Bucket A: license required

- Running new WholeCell simulations to produce **new ensemble seeds** or new perturbation sweeps (not already extracted on disk).
- Regenerating missing/truncated artifacts directly from simulator execution (for example, replacing the 5 truncated process traces with full-fidelity captures via MATLAB runs).
- Re-extracting new fields from MCOS class-instance mats when no existing flattened/archive representation covers those fields.

### Bucket B: license-free alternative exists

- Reading process/state source code: already on disk at `E:\opencell\data\m1_sources\WholeCell\src\...` and `E:\opencell-mirrors\WholeCell\...`.
- Most operational data for OpenCell ingestion: already in `data/karr_archive/*` (Python-native).
- PP2/ProteinModification enzyme/stoichiometry/init-state needs: available in flattened per-process fixtures (`data/karr_fixtures/per_process/*`).
- Reference 100-tick process deltas for 27/28 processes: available in replay npz (`data/karr_fixtures/per_process_replay/*.npz`).
- TU/gene relational metadata: queryable from `WholeCellKB/public/fixtures/data.sql` without MATLAB runtime.
- Karr-native v7.3 `.mat` files: `scipy.io.loadmat` fails, but HDF readers (for example `h5py`) are a license-free path.

### Bucket C: not blocked — already complete

- `RNAProcessing.m` source access is complete.
- PP2 and ProteinModification triage prerequisites (enzyme/init + 100-tick trace files) are complete on disk.
- 28 process class source files are present in the WholeCell mirror.
- Karr 2012 supplement placeholders are already diagnosed as stubs (no additional MATLAB action needed there).

## 4. License-Restored Wishlist (prioritized MATLAB commands)

| Priority | Script path | Expected outputs | Est. runtime | Unblocks |
|---|---|---|---|---|
| 1 | `scripts/matlab/extract_per_process_traces_batch_c.m` | Refresh `ProteinProcessingII_100ticks.mat`, `ProteinModification_100ticks.mat` (plus neighboring protein pipeline traces) in `karr_native/per_process_traces/` | 15-25 min | PP2 + ProteinModification urgent triage confidence hardening |
| 2 | `scripts/matlab/extract_per_process_traces_batch_b.m` | Refresh RNA-lane traces (`Transcription`, `RNADecay`, `RNAProcessing`, `RNAModification`, etc.) with focus on replacing tiny/truncated artifacts | 10-20 min | RNAProcessing-adjacent confidence + 28-process scorecard |
| 3 | `scripts/matlab/extract_per_process_traces_batch_a.m` | Refresh DNA-lane traces, especially `Replication` + `ReplicationInitiation` full captures | 10-20 min | 28-process scorecard (removes 2/5 truncated entries) |
| 4 | `scripts/matlab/extract_initial_states.m` | Regenerate `initial_states/*_init.mat`; target missing 5 process init files | 5-10 min | 28-process fidelity completeness |
| 5 | `scripts/matlab/extract_cell_cycle_trajectory.m` (or proposed `extract_cell_cycle_trajectory_ensemble.m`) | Additional `cell_cycle_trajectory_seed<seed>.mat` files | 45-120 min per seed | Ensemble statistical validation |

Suggested command template:

```powershell
matlab -batch "run('scripts/matlab/extract_per_process_traces_batch_c.m')"
```

## 5. Quick-Reference Appendix

### 5.1 One-line probe/load patterns

Flat fixture (`*_flat.mat`) probe:

```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/docs-matlab-manifest && python -c \"from scipy.io import loadmat; d=loadmat('data/karr_fixtures/per_process/ProteinProcessingII_flat.mat'); print(sorted(d.keys()))\""
```

MCOS/opaque fixture probe (WholeCell fixture mats):

```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && python -c \"from scipy.io import loadmat; d=loadmat('/mnt/e/opencell/data/m1_sources/WholeCell/src_test/+edu/+stanford/+covert/+cell/+sim/+process/fixtures/ProteinProcessingII.mat'); print(sorted(d.keys()))\""
```

v7.3 fallback note (when `loadmat` raises NotImplemented):

```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && python -c \"import h5py; f=h5py.File('/mnt/e/opencell/data/m1_sources/karr_native/fitted_constants.mat'); print(list(f.keys())[:20])\""
```

### 5.2 Pointers to prior dead-process diagnosis STATUS files (4)

- `E:\opencell-worktrees\swarm-dead-protein_processing_i\STATUS_dead_protein_processing_i.md`
- `E:\opencell-worktrees\swarm-dead-rna_processing\STATUS_dead_rna_processing.md`
- `E:\opencell-worktrees\swarm-dead-rc_transcription\STATUS_dead_request_calculator_transcription.md`
- `E:\opencell-worktrees\swarm-dead-rc_translation\STATUS_dead_request_calculator_translation.md`

### 5.3 Master 28-process status pointer

- `c:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\PROCESS_STATUS_ALL_29.md`

