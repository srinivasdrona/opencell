# STATUS: L21 ChromosomeCondensation Geometry Fix

Result: NARROWER BLOCKER

I fixed one proven literal WholeCell mismatch in the tick-0 SMC bind/store
path, but that did not close the row to bit identity / `GENUINE`. The exact
live MATLAB microscope now shows that the next blocker is deeper than binding
geometry: on the hidden tick-0 surface, WholeCell reaches the first bind with
the same local substrates / enzymes / chromosome geometry as our replay, but a
different process-local `randStream.state`.

## What I read

- `SESSION_CONTEXT.md`
- all prior ChromCond status files
- `STATUS_L21_CHROMCOND_RNG_FIX.md`
- `opencell/vivarium/karr_chromosome_condensation.py`
- `tmp/chromcond_tick0_geometry_probe.py`
- `tmp/chromcond_tick0_geometry_probe.m`
- `E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\ChromosomeCondensation.m`
- `E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\ChromosomeProcessAspect.m`
- `E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+state\Chromosome.m`
- the L2 replay / fix helper templates already in `tests/vivarium`

## Proven literal fix

WholeCell samples positions in
`ChromosomeProcessAspect.bindProteinToChromosomeStochastically()` and then calls
`bindProteinToChromosome(..., false, 1, false, ..., checkRegionSupercoiled)`,
which means `isPositionsStrandFootprintCentroid = false`. In the stable bind,
`Chromosome.setSiteProteinBound()` therefore stores those sampled positions
directly and does **not** shift them by the SMC 5'/3' overhang.

Source-backed production change:

- `opencell/vivarium/karr_chromosome_condensation.py`
  - `_smc_centroids_to_start_positions()` now returns the sampled positions
    unchanged instead of subtracting the SMC footprint overhang.

This moved the hidden tick-0 replay from the old incorrect start-position row:

- old OC extras: `[(172645, 0), (188789, 0), (509583, 0)]`

to the source-faithful exact-surface row:

- new OC extras: `[(172960, 0), (189104, 0), (509898, 0)]`

## New microscopes and probes

Added focused helpers:

- `tmp/chromcond_tick0_direct_store_probe.py`
  - runtime proof that direct storage alone moves production to the sampled
    positions, but still not to Karr
- `tmp/chromcond_export_hidden_tick0_surface.py`
  - exports the hidden tick-0 before-state plus validated post-warmup RNG state
    into a MATLAB-restorable artifact
- `tmp/chromcond_tick0_exact_geometry_probe.m`
  - restores the hidden tick-0 surface into a live MATLAB
    `ChromosomeCondensation` instance with `randStream.state = 1279689633`
    and records the bind ledger
- `tmp/chromcond_tick0_exact_geometry_compare.py`
  - compares the exact-surface MATLAB ledger against the current Python replay

## Exact blocker now isolated

Two live MATLAB microscopes now separate the remaining issue:

1. Full WholeCell tick-0 microscope (`tmp/chromcond_tick0_geometry_probe.m`)
   - `preSubstrates = [75, 0, 0, 756718, 0]`
   - `preEnzymes = [5, 3]`
   - `preBoundEnzymes = [0, 78]`
   - `preRandStreamState = 931316785`
   - `actualAddedSmcPosStrnds = [(172652,1), (189030,1), (510536,1)]`

2. Exact hidden-surface replay microscope (`tmp/chromcond_tick0_exact_geometry_probe.m`)
   - `preSubstrates = [75, 0, 0, 756718, 0]`
   - `preEnzymes = [5, 3]`
   - `preBoundEnzymes = [0, 78]`
   - `preRandStreamState = 1279689633`
   - `actualAddedSmcPosStrnds = [(172961,1), (189105,1), (509899,1)]`

Important conclusion:

- the accessible regions, outer exclusions, and binding-region geometry on the
  restored hidden surface are source-faithful
- the first remaining deeper datum is the process-local pre-bind
  `randStream.state`
- local molecule counts and chromosome occupancy/geometry are **not** the next
  divergence anymore

So the remaining blocker is not honestly another geometry formula inside the
tick-0 bind helper. It is the handoff between the validated
`target.initializeState()` warmup endpoint (`1279689633`) and the live
WholeCell first-tick process state (`931316785`).

## Verification

Green:

- `bin\oc-py.cmd tmp/chromcond_postwarmup_handoff_probe.py`
  - now produces `tick0_new_sites_from_postwarmup_rng_only = [(172960, 0), (189104, 0), (509898, 0)]`
- `bin\oc-py.cmd tmp/chromcond_hidden_mismatch_probe.py`
  - hidden tick-0 mismatch moved to:
    - missing: `(172651, 0, 82)`, `(189029, 0, 82)`, `(510535, 0, 82)`
    - extra: `(172960, 0, 82)`, `(189104, 0, 82)`, `(509898, 0, 82)`
- `bin\oc-py.cmd tmp/chromcond_export_hidden_tick0_surface.py`
  - exported the exact hidden tick-0 local state and chromosome surface
- `E:\MATLAB\bin\matlab.exe -batch "run(fullfile('E:/opencell-worktrees/wave-l21-chromcond','tmp','chromcond_tick0_exact_geometry_probe.m'))"`
  - live MATLAB exact-surface bind row:
    `[(172961,1), (189105,1), (509899,1)]`
- `bin\oc-py.cmd tmp/chromcond_nohint_probe.py`
  - first visible mismatch remains tick 15 ATP `42` vs Karr `41`
- `bin\oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation.py -q`
  - `6 passed`
- `bin\oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation_l2_replay.py -q`
  - `1 passed`
- `bin\oc-py.cmd scripts/probe_l2_1_strict_rubric.py --process ChromosomeCondensation`
  - still `FAIL`
  - still `Karr 66%`, `OC 71%`, `OC|Karr 95%`
- `bin\oc-py.cmd -m ruff check opencell/vivarium/karr_chromosome_condensation.py tmp/chromcond_export_hidden_tick0_surface.py tmp/chromcond_tick0_exact_geometry_compare.py`
  - PASS

Not green:

- `bin\oc-py.cmd tmp/chromcond_tick0_exact_geometry_compare.py`
  - first difference is still the auxiliary probe field
    `samples[0].storedPosStrand[0]`
  - MATLAB manual shifted value is `509584`, while production now stores the
    sampled site `509899`; this is expected because the MATLAB probe keeps the
    manual overhang-shift calculation only as a diagnostic
- `bin\oc-py.cmd scripts/l1b_verify_wiring.py --process ChromosomeCondensation --strict-anchors --format plain`
  - FAIL at `check_oc_anchors_resolve`
  - still coming from the pre-existing dirty
    `data/schemas/per_process_wiring/ChromosomeCondensation.yaml`

## Worktree / commit note

- I preserved the dirty worktree.
- This turn's green chunk is the source-backed direct-store fix plus the new
  exact-surface MATLAB microscope/probe artifacts.

## Next step

The next honest target is the now-isolated handoff datum:

1. explain where the live WholeCell first-tick `ChromosomeCondensation`
   `randStream.state` reverts to `931316785` even though the warmup endpoint
   reaches `1279689633`
2. prove whether that state is intentionally not persisted across
   `initializeState()` / `copyFromState()` boundaries or whether another
   WholeCell path resets the process-local stream before tick 0
3. only after that, decide whether the production replay should preserve the
   post-warmup stream, the live first-tick stream, or both at different
   boundaries
