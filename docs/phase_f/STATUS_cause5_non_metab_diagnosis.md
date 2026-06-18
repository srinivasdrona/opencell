# STATUS: CAUSE_5 diagnosis for ChromosomeCondensation + ReplicationInitiation (non-Metabolism)

## Scope and constraints
- Pair investigated: `ChromosomeCondensation + ReplicationInitiation`
- Seed: `rng_seed=0`
- Mode: `disable_trace_hints=True` for L2.5 DS pair replay
- This was diagnosis-only. No changes were made to process, harness, or test files.

## Read-set accounting
Planned read-set in task brief was 5 files. I exceeded by 1 mandatory path:
- Extra read path: `docs/phase_f/L2_5_HARNESS_DESIGN.md`
- Reason: task requires quoting CAUSE_5 definition verbatim from authoritative spec section 5 before analysis.

## Authoritative CAUSE_5 definition (verbatim)
From `docs/phase_f/L2_5_HARNESS_DESIGN.md` section 5 (D3):

> `CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE: process fails in isolated replay against own trace.`

## Tick-0 forensic table (WID from first failure)
Failure record first WID is `MG_469_1MER_ATP` on RI observable `enzymes` (index 1).

| WID | Condensation tick-0 L2.1 | ReplicationInitiation tick-0 L2.1 | Pair assertion surface (delta mode) | Isolated RI assertion surface (absolute mode) |
|---|---|---|---|---|
| `MG_469_1MER_ATP` (`enzymes`) | Not present in Condensation observables (no direct touch) | `before=2`, `after=0`, `delta=-2` | `karr_compare=-2`, `oc_compare=0`, `oc_counterfactual_compare=0` | `karr_compare=0` (absolute target), `oc_compare=2`, `oc_counterfactual_compare=2` |

Supporting tick-0 context for same WID in RI:
- `boundEnzymes` for `MG_469_1MER_ATP`: `before=23`, `after=25`, `delta=+2`
- This is a free->bound transfer in RI trace at tick 0; Condensation is not the source.

## Multi-trace adjudication: (a)/(b)/(c)
1. Composition-only baseline artifact check:
- `MG_469_1MER_ATP` is absent from Condensation observable WID lists at tick 0.
- Pair failure still reports `isolated_replay_result=diverges_from_oracle`.
- Therefore this is not explained by Condensation upstream state pollution alone.

2. Isolated replay check (D3 CAUSE_5 criterion):
- Isolated `ReplicationInitiation` replay (`under_test_processes=['ReplicationInitiation']`, `disable_trace_hints=True`) emits `CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE` at tick 0 on the same WID/observable.
- This satisfies CAUSE_5 definition directly.

3. Harness misclassification check:
- CAUSE code derives from explicit branch: isolated match => CAUSE_4, isolated diverges => CAUSE_5 (`tests/vivarium/l2_2_replay_common_v2.py:1498-1503`).
- Here isolated diverges on RI itself; this is not a CAUSE_4-only condition.

## Verdict
**Verdict: (a) composed process is wrong due real intrinsic no-hints replay divergence in ReplicationInitiation on the L2.5 no-hints surface.**

This case is not (b): isolated replay already diverges.
This case is not (c): CAUSE_5 assignment matches D3 discriminator logic.

## Specific fix path
Likely repair target is RI no-hints channel writeback parity (analogous class to Metabolism, different channel):

- `opencell/vivarium/karr_replication_initiation.py:288-293`
  - No-hints path is selected whenever trace hints are absent.
- `opencell/vivarium/karr_replication_initiation.py:354-401`
  - No-hints path mutates internal free/bound state and emits `chromosome`, `protein`, and `substrates`, but does not emit `enzymes`/`boundEnzymes` deltas.
- `opencell/vivarium/karr_replication_initiation.py:573-629`
  - Hint-assisted path emits explicit `enzymes` and `boundEnzymes` deltas from trace hints.

Observed effect at tick 0:
- Karr expects `enzymes[MG_469_1MER_ATP]` delta `-2` and `boundEnzymes[MG_469_1MER_ATP]` delta `+2`.
- No-hints RI step leaves `enzymes` unchanged (`0` delta on compare surface), causing isolated CAUSE_5.

Concrete fix direction:
1. In no-hints path, emit replay-faithful `enzymes` and `boundEnzymes` deltas derived from internal `_free_dnaa_*` / `_bound_*` transitions, not only `protein`/`chromosome` channels.
2. Preserve existing `protein`/`chromosome` updates for current runtime behavior, but make observable channels consistent with L2.1 replay expectations.
3. Re-run pair and isolated RI no-hints replay after patch.

## Generalizability vs Metabolism prior case
- Metabolism prior diagnosis was `(a)` via no-hints substrate writeback gap (`karr_metabolism.py:355-357`).
- This non-Metabolism case is also `(a)` and appears to be the same higher-level class: **no-hints path emits an incomplete observable channel set compared to replay surface**.
- Difference in mechanism:
  - Metabolism: missing `substrates` writeback in no-hints static dispatch.
  - ReplicationInitiation: missing `enzymes`/`boundEnzymes` writeback in no-hints path.
- Claim boundary: this supports class-level generalization beyond Metabolism, but does not yet prove all non-Metabolism CAUSE_5 emitters share this exact mechanism.

## Commands run
```powershell
bin\oc-py.cmd _probe_cause5_cond_repinit.py
bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k "ChromosomeCondensation+ReplicationInitiation" --tb=long
bin\oc-pytest.cmd tests/vivarium/test_karr_replication_initiation_l2_replay.py -v
```

## Probe output (verbatim)
```text
=== CAUSE_5 PROBE: ChromosomeCondensation + ReplicationInitiation ===
TRACE_PATHS
  ChromosomeCondensation: /mnt/e/opencell/data/m1_sources/karr_native/per_process_traces_v2/ChromosomeCondensation_100ticks.mat
  ReplicationInitiation: /mnt/e/opencell/data/m1_sources/karr_native/per_process_traces_v2/ReplicationInitiation_100ticks.mat
TARGET_WID MG_469_1MER_ATP
TICK 0 TRACE_FORENSICS MG_469_1MER_ATP
  ChromosomeCondensation: WID not present in process observables
  ReplicationInitiation: observable=enzymes idx=1 before=2 after=0 delta=-2 touches_tick0=yes
  ReplicationInitiation: observable=boundEnzymes idx=1 before=23 after=25 delta=2 touches_tick0=yes
PAIR_REPLAY_RESULT
  status=structured_failure
  pair_record cause=CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE tick=0 process=ReplicationInitiation observable=enzymes index=1 compare_mode=delta isolated_replay_result=diverges_from_oracle
  mismatch_wid=MG_469_1MER_ATP
  target_wid=MG_469_1MER_ATP target_idx=1 karr_compare=-2.0 oc_compare=0.0 oc_counterfactual_compare=0.0
PAIR_FAILURE_RECORD_JSON
{"cause_code": "CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE", "compare_mode": "delta", "composition_order": ["ChromosomeCondensation", "ReplicationInitiation"], "diff": 2.0, "index": 1, "isolated_replay_result": "diverges_from_oracle", "karr_val": -2.0, "master_index": 3, "master_wids": ["MG_213_214_298_6MER", "MG_213_214_298_6MER_ADP", "MG_469_1MER_ADP", "MG_469_1MER_ATP", "MG_469_2MER_1ATP_ADP", "MG_469_2MER_ATP", "MG_469_3MER_2ATP_ADP", "MG_469_3MER_ATP", "MG_469_4MER_3ATP_ADP", "MG_469_4MER_ATP", "MG_469_5MER_4ATP_ADP", "MG_469_5MER_ATP", "MG_469_6MER_5ATP_ADP", "MG_469_6MER_ATP", "MG_469_7MER_6ATP_ADP", "MG_469_7MER_ATP", "MG_469_MONOMER"], "master_wids_hash": "0594b5b999fe35b7d016b3a2864722d4152e2a87293eadb0a881b458cbc68964", "observable": "enzymes", "oc_val": 0.0, "oracle_type": "distributional", "owner_manifest_observable_owner": "ChromosomeCondensation", "owner_wid": null, "process": "ReplicationInitiation", "process_wid": "MG_469_1MER_ATP", "process_wid_to_master_idx": {"ChromosomeCondensation": {"MG_213_214_298_6MER": 0, "MG_213_214_298_6MER_ADP": 1}, "ReplicationInitiation": {"MG_469_1MER_ADP": 2, "MG_469_1MER_ATP": 3, "MG_469_2MER_1ATP_ADP": 4, "MG_469_2MER_ATP": 5, "MG_469_3MER_2ATP_ADP": 6, "MG_469_3MER_ATP": 7, "MG_469_4MER_3ATP_ADP": 8, "MG_469_4MER_ATP": 9, "MG_469_5MER_4ATP_ADP": 10, "MG_469_5MER_ATP": 11, "MG_469_6MER_5ATP_ADP": 12, "MG_469_6MER_ATP": 13, "MG_469_7MER_6ATP_ADP": 14, "MG_469_7MER_ATP": 15, "MG_469_MONOMER": 16}}, "raw_vectors": {"karr_after": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "karr_compare": [0.0, -2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "oc_after_step": [0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "oc_compare": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "oc_counterfactual": [0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "oc_counterfactual_compare": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, "shared_observable_mutators": ["ChromosomeCondensation", "ReplicationInitiation"], "tick": 0, "upstream_processes": ["ChromosomeCondensation"], "wid_lists_by_process": {"ChromosomeCondensation": ["MG_213_214_298_6MER", "MG_213_214_298_6MER_ADP"], "ReplicationInitiation": ["MG_469_1MER_ADP", "MG_469_1MER_ATP", "MG_469_2MER_1ATP_ADP", "MG_469_2MER_ATP", "MG_469_3MER_2ATP_ADP", "MG_469_3MER_ATP", "MG_469_4MER_3ATP_ADP", "MG_469_4MER_ATP", "MG_469_5MER_4ATP_ADP", "MG_469_5MER_ATP", "MG_469_6MER_5ATP_ADP", "MG_469_6MER_ATP", "MG_469_7MER_6ATP_ADP", "MG_469_7MER_ATP", "MG_469_MONOMER"]}}
ISOLATED_RI_REPLAY_RESULT
  status=structured_failure
  isolated_record cause=CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE tick=0 process=ReplicationInitiation observable=enzymes index=1 compare_mode=absolute isolated_replay_result=diverges_from_oracle
  mismatch_wid=MG_469_1MER_ATP
  target_wid=MG_469_1MER_ATP target_idx=1 karr_compare=0.0 oc_compare=2.0 oc_counterfactual_compare=2.0
ISOLATED_RI_FAILURE_RECORD_JSON
{"cause_code": "CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE", "compare_mode": "absolute", "composition_order": ["ReplicationInitiation"], "diff": 2.0, "index": 1, "isolated_replay_result": "diverges_from_oracle", "karr_val": 0.0, "master_index": 1, "master_wids": ["MG_469_1MER_ADP", "MG_469_1MER_ATP", "MG_469_2MER_1ATP_ADP", "MG_469_2MER_ATP", "MG_469_3MER_2ATP_ADP", "MG_469_3MER_ATP", "MG_469_4MER_3ATP_ADP", "MG_469_4MER_ATP", "MG_469_5MER_4ATP_ADP", "MG_469_5MER_ATP", "MG_469_6MER_5ATP_ADP", "MG_469_6MER_ATP", "MG_469_7MER_6ATP_ADP", "MG_469_7MER_ATP", "MG_469_MONOMER"], "master_wids_hash": "bd9f9b66eebe65361bf6132ef2661e89b8d8ffd227870b65587a66f5aa5abfd5", "observable": "enzymes", "oc_val": 2.0, "oracle_type": "distributional", "owner_manifest_observable_owner": "ReplicationInitiation", "owner_wid": "MG_469_1MER_ATP", "process": "ReplicationInitiation", "process_wid": "MG_469_1MER_ATP", "process_wid_to_master_idx": {"ReplicationInitiation": {"MG_469_1MER_ADP": 0, "MG_469_1MER_ATP": 1, "MG_469_2MER_1ATP_ADP": 2, "MG_469_2MER_ATP": 3, "MG_469_3MER_2ATP_ADP": 4, "MG_469_3MER_ATP": 5, "MG_469_4MER_3ATP_ADP": 6, "MG_469_4MER_ATP": 7, "MG_469_5MER_4ATP_ADP": 8, "MG_469_5MER_ATP": 9, "MG_469_6MER_5ATP_ADP": 10, "MG_469_6MER_ATP": 11, "MG_469_7MER_6ATP_ADP": 12, "MG_469_7MER_ATP": 13, "MG_469_MONOMER": 14}}, "raw_vectors": {"karr_after": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "karr_compare": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "oc_after_step": [0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "oc_compare": [0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "oc_counterfactual": [0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "oc_counterfactual_compare": [0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, "shared_observable_mutators": ["ReplicationInitiation"], "tick": 0, "upstream_processes": [], "wid_lists_by_process": {"ReplicationInitiation": ["MG_469_1MER_ADP", "MG_469_1MER_ATP", "MG_469_2MER_1ATP_ADP", "MG_469_2MER_ATP", "MG_469_3MER_2ATP_ADP", "MG_469_3MER_ATP", "MG_469_4MER_3ATP_ADP", "MG_469_4MER_ATP", "MG_469_5MER_4ATP_ADP", "MG_469_5MER_ATP", "MG_469_6MER_5ATP_ADP", "MG_469_6MER_ATP", "MG_469_7MER_6ATP_ADP", "MG_469_7MER_ATP", "MG_469_MONOMER"]}}
```

## Additional test observations
- `tests/vivarium/test_l25_deterministic_stochastic_pairs.py -k "ChromosomeCondensation+ReplicationInitiation"` fails with the same structured CAUSE_5 payload at tick 0 (`process_wid=MG_469_1MER_ATP`).
- `tests/vivarium/test_karr_replication_initiation_l2_replay.py -v` passes (`1 passed`), which is not contradictory: it is a different replay surface/test contract from the L2.5 no-hints DS integrated replay path diagnosed here.
