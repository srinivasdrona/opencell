# STATUS: CAUSE_5 diagnosis for ChromosomeCondensation + Metabolism

## Scope and constraints
- Pair investigated: `ChromosomeCondensation + Metabolism`
- Seed: `rng_seed=0`
- Mode: `disable_trace_hints=True` (same as `test_l25_deterministic_stochastic_pairs.py`)
- This is a diagnosis-only pass. No harness/process/test code was modified.

## Read-set accounting
Planned read-set was the 5 files in the task brief. I exceeded by 1 path for disambiguation:
- Extra read path: `tests/vivarium/test_l25_deterministic_stochastic_pairs.py` (path existence/query only, to validate target test invocation when the initial `-k` search returned no content match).
- Reason: trace path in the task brief pointed to `per_process_traces_v2_s000`, while the active harness resolves to `per_process_traces_v2`; I needed to validate the exact active test target and replay surface before probing.

## Authoritative CAUSE_5 definition (verbatim)
From `docs/phase_f/L2_5_HARNESS_DESIGN.md` section 5 (D3):

> `CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE: process fails in isolated replay against own trace.`

## Tick-0 forensic table (shared substrates)
Harness compare mode for this pair/observable is `delta` (because `substrates` has upstream mutator `ChromosomeCondensation`).
So the assertion surface is:
- asserted: `karr_compare = Metabolism(states_after - states_before)`
- observed: `oc_compare = Metabolism_composed_after - Metabolism_composed_before`

| WID | Condensation L2.1 (before -> after) | Metabolism L2.1 (before -> after) | Metabolism in composition (before -> after) | What test asserted vs observed |
|---|---|---|---|---|
| ADP | `0 -> 3` (delta `+3`) | `3622 -> 0` (delta `-3622`) | `3 -> 3` (delta `0`) | asserted delta `-3622` vs observed delta `0` (diff `+3622`) |
| ATP | `75 -> 72` (delta `-3`) | `0 -> 3626` (delta `+3626`) | `72 -> 72` (delta `0`) | asserted delta `+3626` vs observed delta `0` (diff `-3626`) |
| PI | `0 -> 3` (delta `+3`) | `7246 -> 0` (delta `-7246`) | `3 -> 3` (delta `0`) | asserted delta `-7246` vs observed delta `0` (diff `+7246`) |
| H2O | `756718 -> 756715` (delta `-3`) | `0 -> 9195` (delta `+9195`) | `756715 -> 756715` (delta `0`) | asserted delta `+9195` vs observed delta `0` (diff `-9195`) |
| H | `0 -> 3` (delta `+3`) | `13042 -> 1719` (delta `-11323`) | `3 -> 3` (delta `0`) | asserted delta `-11323` vs observed delta `0` (diff `+11323`) |

Note on AMP (requested cross-check): AMP is **not** a shared Condensation substrate WID; Metabolism AMP at tick 0 is `1449 -> 1449` (delta `0`) and composition also observed delta `0`.

## Multi-trace adjudication: (a)/(b)/(c)
1. Finding: composition mismatch is not a baseline-shift artifact from upstream Condensation deltas.
- Classification: **not (b)**.
- Evidence: harness is already asserting on Metabolism delta (`compare_mode=delta`), not absolute after-state. Upstream +3/-3 on shared currencies does not explain observed `0` delta when Karr delta is large nonzero.

2. Finding: Metabolism fails in isolated replay with no upstream process.
- Classification: **(a) real intrinsic replay failure on the tested no-hints surface**.
- Evidence: isolated run with `under_test_processes=['Metabolism']` also emits `CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE` at tick 0 on `substrates` (`compare_mode=absolute`), e.g. ADP `isolated_oc=3622` vs `isolated_karr=0`, ATP `isolated_oc=0` vs `isolated_karr=3626`.

3. Finding: CAUSE_5 labeling for this pair is consistent with D3, not a CAUSE_4/classifier artifact.
- Classification: **not (c)** for this pair.
- Evidence: the D3 discriminator is exactly "fails in isolated replay against own trace," and that condition holds even without composition.

## Verdict
**Verdict: (a) real bug (process intrinsic replay divergence on no-hints L2.5 surface), not oracle-baseline artifact.**

## Specific fix path (required for verdict (a))
Primary fix target is Metabolism no-hints replay behavior:
- File: `opencell/vivarium/karr_metabolism.py`
- Relevant lines:
  - defaults/static mode gate: around `113-119` (`dynamic_bounds=False` by default)
  - no-hints dispatch: around `355-357` (`if not self.dynamic_bounds: return self._static_update(...)`)
  - static update payload: around `359-376` (returns only `metabolic_reaction.fluxs`, no `substrates` writeback)

Proposed change direction:
1. Add a replay-faithful no-hints path for `substrates` in static mode (or a dedicated replay mode used by L2.5) so `next_update` emits substrate deltas consistent with Karr `states_after - states_before` rather than leaving substrates unchanged.
2. Keep existing central-dogma static/back-compat behavior behind explicit gating so existing non-replay consumers are not regressed.

## Generalizability (other CAUSE_5 pairs)
- This diagnosis is strongly suggestive for other CAUSE_5 pairs where **Metabolism is the failing side** and first mismatch WID is in the energy-currency set (`ATP/ADP/AMP/GTP`): high-turnover currencies are exactly where "observed delta=0 vs expected large nonzero" manifests first.
- I cannot claim universal generalization to all 15 remaining CAUSE_5 pairs without pair-level probes. This result should be treated as:
  - high-confidence template for Metabolism-involved CAUSE_5 pairs,
  - not yet proven for non-Metabolism CAUSE_5 emitters.

## Commands run
```powershell
bin\oc-py.cmd _probe_cause5_cond_metab.py
bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k "ChromosomeCondensation+Metabolism" --tb=long
```

## Probe output (verbatim)
```text
=== CAUSE_5 PROBE: ChromosomeCondensation + Metabolism ===
TRACE_PATHS
  ChromosomeCondensation: /mnt/e/opencell/data/m1_sources/karr_native/per_process_traces_v2/ChromosomeCondensation_100ticks.mat
  Metabolism: /mnt/e/opencell/data/m1_sources/karr_native/per_process_traces_v2/Metabolism_100ticks.mat
SHARED_SUBSTRATE_WIDS ATP,ADP,PI,H2O,H

TICK 0 TRACE_FORENSICS
  ADP: Cond_L2.1 before=0 after=3 delta=3 | Metab_L2.1 before=3622 after=0 delta=-3622
  ATP: Cond_L2.1 before=75 after=72 delta=-3 | Metab_L2.1 before=0 after=3626 delta=3626
  AMP: Cond_L2.1 before=N/A after=N/A delta=N/A | Metab_L2.1 before=1449 after=1449 delta=0

TICK 5 TRACE_FORENSICS
  ADP: Cond_L2.1 before=0 after=0 delta=0 | Metab_L2.1 before=299 after=1 delta=-298
  ATP: Cond_L2.1 before=76 after=76 delta=0 | Metab_L2.1 before=0 after=1104 delta=1104
  AMP: Cond_L2.1 before=N/A after=N/A delta=N/A | Metab_L2.1 before=800 after=0 delta=-800

TICK 10 TRACE_FORENSICS
  ADP: Cond_L2.1 before=0 after=1 delta=1 | Metab_L2.1 before=299 after=0 delta=-299
  ATP: Cond_L2.1 before=46 after=45 delta=-1 | Metab_L2.1 before=0 after=1017 delta=1017
  AMP: Cond_L2.1 before=N/A after=N/A delta=N/A | Metab_L2.1 before=713 after=0 delta=-713

PAIR_FAILURE_RECORD
  cause=CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE tick=0 process=Metabolism observable=substrates compare_mode=delta isolated_replay_result=diverges_from_oracle
PAIR_ASSERTION_SURFACE_TICK0
  ADP: Metab_composed_before=3 Metab_composed_after=3 asserted_delta(karr_compare)=-3622 observed_delta(oc_compare)=0 delta_diff=3622 oc_counterfactual_compare=0
  ATP: Metab_composed_before=72 Metab_composed_after=72 asserted_delta(karr_compare)=3626 observed_delta(oc_compare)=0 delta_diff=-3626 oc_counterfactual_compare=0
  AMP: Metab_composed_before=1449 Metab_composed_after=1449 asserted_delta(karr_compare)=0 observed_delta(oc_compare)=0 delta_diff=0 oc_counterfactual_compare=0
  PI: Metab_composed_before=3 Metab_composed_after=3 asserted_delta(karr_compare)=-7246 observed_delta(oc_compare)=0 delta_diff=7246 oc_counterfactual_compare=0
  H2O: Metab_composed_before=756715 Metab_composed_after=756715 asserted_delta(karr_compare)=9195 observed_delta(oc_compare)=0 delta_diff=-9195 oc_counterfactual_compare=0
  H: Metab_composed_before=3 Metab_composed_after=3 asserted_delta(karr_compare)=-11323 observed_delta(oc_compare)=0 delta_diff=11323 oc_counterfactual_compare=0

ISOLATED_METABOLISM_RECORD
  cause=CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE tick=0 process=Metabolism observable=substrates compare_mode=absolute isolated_replay_result=diverges_from_oracle
  ADP: isolated_oc=3622 isolated_karr=0 diff=3622
  ATP: isolated_oc=0 isolated_karr=3626 diff=-3626
  AMP: isolated_oc=1449 isolated_karr=1449 diff=0
  PI: isolated_oc=7246 isolated_karr=0 diff=7246
  H2O: isolated_oc=0 isolated_karr=9195 diff=-9195
  H: isolated_oc=13042 isolated_karr=1719 diff=11323
```
