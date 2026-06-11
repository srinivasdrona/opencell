## Beat 1 - SUT inspection + wiring design

- SUT class: `MacromolecularComplexationProcess` from `opencell/vivarium/karr_macromolecular_complexation.py`.
- Process attributes:
  - `substrate_wids`: present, length 210.
  - `monomer_wids`: not present on the SUT class.
  - `complex_wids`: present, length 147.
- Fixture cross-check:
  - `substrateWholeCellModelIDs` is the live mixed substrate pool. Empirical split from fixture index arrays: 208 monomer WIDs + 2 RNA WIDs + 0 metabolite WIDs = 210 total.
  - Design consequence: catalog `monomers` must be synthesized as the substrate-vector projection onto the 208 monomer positions; do not revive the old `enzymes` / `boundEnzymes` pass-through surface.
- v2 ensemble cross-check:
  - On-disk 50-seed ensemble exists under `E:\opencell\data\m1_sources\karr_native\per_process_traces_v2_s{000..049}\MacromolecularComplexation_100ticks.mat`.
  - Raw v2 trace channel keys are `substrates`, `complexs`, `enzymes`, `boundEnzymes`; there is no raw `monomers` dataset.
  - Current helper root resolution only sees the worktree-local `data/` tree, which is incomplete here (`per_process_traces_v2_s001` only). Beat 2 will switch the loader to resolve the populated main-repo `karr_native` root so `load_karr_oracle("MacromolecularComplexation")` returns `canonical_seed_count=50`.
- `next_update` write surface:
  - Writes `substrates` deltas and `complex.counts` deltas.
  - Does not write a standalone monomer store; projected `monomers` must therefore be read back from the substrate pool subset.
  - No `_maybe_replay_from_hint` or `trace_hint` replay path exists in the SUT. Dispatcher will still leave `trace_hint` empty defensively, mirroring the RNADecay / ProteinDecay shallow pattern.
- Duplicate-WID probe on primary channel `complexs`:
  - `complex_wids` length 147, duplicate count 0.
  - Round-trip overlay/project probe on tick-0 `complexs` returned `max_abs_diff=0.0`, `mismatch_count=0`.
  - Design consequence: no positional shadow store handling is needed for `complexs`.
- Wiring design for Beats 2-3:
  - Add a cached `_macromol_process(seed)` factory and annotate the cached process with helper-only `monomer_wids` / monomer-index metadata derived from the fixture.
  - Extend the v2 oracle formatter with a Macromol branch that keeps `substrates` + `complexs` raw and derives `monomers` from the substrate monomer subset.
  - Add `_run_macromol_tick(seed, tick, state)` that overlays `oracle_before_substrates`, overlays `oracle_before_monomers` onto the same substrate store via a store-path override, overlays `oracle_before_complexs`, keeps `trace_hint` empty, and returns projected `substrates` / `monomers` / `complexs`.
  - Add runner wiring for `MacromolecularComplexation` in `_process_sample_process`, `_observable_wids`, and the per-tick sample-state branch.

## Beat 2 - pending

## Beat 3 - pending

## Beat 4 - pending

## Beat 5 - pending

verdict: IN_PROGRESS
