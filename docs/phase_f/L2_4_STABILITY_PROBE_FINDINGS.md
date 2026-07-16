# L2.4 Stability Probe Findings

## Verdict

**NO** — the capped-baseline autonomous chassis does **not** complete a 100-tick run on seeds 0-3. Every requested run crashes on **tick 1**, so the max stable tick for this probe is **0**. Because no tick completes, the conservation baseline is **not measurable from this run**: there is no RED or GREEN L2.4 conservation verdict yet, only a stability blocker in the existing probe path.

## Commands Used

Allocator state: `opencell/vivarium/karr_allocation_step.py` left exactly as found in the working tree (`git status --short` showed it as modified to the intended capped baseline for this probe).

Commands:

```powershell
bin\oc-py scripts/run_chassis_v6_32400t.py --seed 0 --biological-seconds 100 --conservation-stride 1 --out-dir tmp/l2_4_probe/seed0 --fresh
bin\oc-py scripts/run_chassis_v6_32400t.py --seed 1 --biological-seconds 100 --conservation-stride 1 --out-dir tmp/l2_4_probe/seed1 --fresh
bin\oc-py scripts/run_chassis_v6_32400t.py --seed 2 --biological-seconds 100 --conservation-stride 1 --out-dir tmp/l2_4_probe/seed2 --fresh
bin\oc-py scripts/run_chassis_v6_32400t.py --seed 3 --biological-seconds 100 --conservation-stride 1 --out-dir tmp/l2_4_probe/seed3 --fresh
```

Probe knobs matched the requested shape without adaptation:

- `--biological-seconds 100` -> 100 ticks at the runner's `timestep_s = 1.0`
- `--conservation-stride 1` -> per-tick conservation accounting

## Per-Seed Results

| seed | completed_ticks | max_abs_unattributed_delta | crash? |
|---|---:|---:|---|
| 0 | 0 | N/A | tick 1 crash in `karr_rna_modification.next_update`: `AttributeError: 'numpy.random._generator.Generator' object has no attribute 'random_sample'` |
| 1 | 0 | N/A | tick 1 crash in `karr_rna_modification.next_update`: `AttributeError: 'numpy.random._generator.Generator' object has no attribute 'random_sample'` |
| 2 | 0 | N/A | tick 1 crash in `karr_rna_modification.next_update`: `AttributeError: 'numpy.random._generator.Generator' object has no attribute 'random_sample'` |
| 3 | 0 | N/A | tick 1 crash in `karr_rna_modification.next_update`: `AttributeError: 'numpy.random._generator.Generator' object has no attribute 'random_sample'` |

Evidence that `completed_ticks = 0` for all seeds:

- each `tmp/l2_4_probe/seed*/key_substrates.csv` has exactly 2 lines (header + tick 0 row only)
- each `tmp/l2_4_probe/seed*/replication_events.csv` has exactly 2 lines (header + tick 0 row only)
- each `tmp/l2_4_probe/seed*/conservation.csv` has exactly 1 line (header only)
- no `tmp/l2_4_probe/seed*/manifest.json` was written

## Crash Signature

Traceback tail was identical across seeds 0-3:

```text
File "/mnt/e/opencell/scripts/run_chassis_v6_32400t.py", line 609, in run_full_cycle
  engine.update(timestep_s)
File "/mnt/e/opencell/scripts/run_chassis_v6_32400t.py", line 316, in wrapped_next_update
  update = _original(timestep, states)
File "/mnt/e/opencell/opencell/vivarium/karr_rna_modification.py", line 270, in next_update
  rna_fluxes = self._compute_rna_fluxes(
File "/mnt/e/opencell/opencell/vivarium/karr_rna_modification.py", line 416, in _compute_rna_fluxes
  enzyme_limits = self._stochastic_round_vector(enzyme_limits)
File "/mnt/e/opencell/opencell/vivarium/karr_rna_modification.py", line 511, in _stochastic_round_vector
  draws = self._rng.random_sample(vals.shape)
AttributeError: 'numpy.random._generator.Generator' object has no attribute 'random_sample'
```

Relevant code anchors in the existing probe path:

- `scripts/run_chassis_v6_32400t.py:279` seeds entities with `entity._rng = np.random.default_rng(entity_seed)`
- `opencell/vivarium/karr_rna_modification.py:501` and `:511` call `self._rng.random_sample(...)`

This is reported as observed behavior only; no code was modified in this probe.

## Top-Offender WIDs

No top-offender ranking is available from this run because no conservation sample completed:

| WID | max \|unattributed_delta\| | likely A-bug |
|---|---:|---|
| N/A | N/A | not measurable; every `conservation.csv` contains only the header row because the run crashes on tick 1 |

## Conclusion For L2.4 Design

- The gate's PM assumption that the capped-baseline chassis can run autonomously for 100 ticks does **not** hold in the current probe path.
- Under the design doc's rule, scope would have to drop from 100 ticks to the **max stable tick = 0** unless/until this stability blocker is removed.
- The expected RED conservation signal for L2.4 was **not reached** here. This is **not** evidence of GREEN; it is simply an unmeasured baseline because the run dies before the first per-tick conservation sample is written.
- The capped allocator baseline was preserved exactly as requested; the blocker appears in the autonomous runner's existing RNG interaction with `karr_rna_modification`, not in any changes made during this probe.
