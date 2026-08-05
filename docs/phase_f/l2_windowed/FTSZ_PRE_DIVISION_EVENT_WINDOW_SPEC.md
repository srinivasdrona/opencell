# FtsZPolymerization pre-division event-window evidence — spec

STATUS: branch-local spec for `agent/l2-event-ftsz-20260805`. Documents the
mechanism in `scripts/l2_event/ftsz_pre_division_evidence.py` and its tests
(`tests/scripts/test_ftsz_pre_division_evidence.py`). Supersedes
`docs/phase_f/l2_windowed/FTSZ_WINDOWED_PROFILE_SPEC.md` for CATALOG
CONFORMANCE only -- that document's N=1, non-division-anchored diagnostic
(`tests/vivarium/test_karr_ftsz_polymerization_honest_canary.py`) remains
in the tree as valid, separate evidence.

## 1. Contract

The live, unedited `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` row for
`FtsZPolymerization` is authoritative and is not edited by this work:

```yaml
  - name: FtsZPolymerization
    oc_module: opencell/vivarium/karr_ftsz_polymerization.py
    bucket: EVENT_CLASS
    harness_type: event_class
    in_scope_L2_2: true
    M_ticks: 200
    N_seeds: 50
    event_density: sparse
    input_channels: [substrates, enzymes, monomers]
    output_channels: [substrates, monomers]
    primary_channel: monomers
    karr_artifact: per_process_traces_v2
    seed_window:
      tick_range_from_division: [-200, 0]
      rationale: "FtsZ polymerization is biologically active only in the pre-division window"
```

`scripts/l2_event/ftsz_pre_division_evidence.py` builds a process-local
(not registry-wired) evidence path directly against this row: discover real
on-disk `[-200, 0]`-relative, 200-tick, 50-seed windows; validate them
mechanically; replay them honestly (no hint); detect real activity; project
the declared `monomers` primary channel; and report an honest
ensemble-completeness verdict that fails closed when fewer than 50
qualifying seeds exist.

It is deliberately NOT wired into `scripts/l2_event/registry.py`/`runner.py`
and does not edit `docs/phase_f/l2_event/event_registry.yaml` (FtsZ's row
there stays `in_scope_v4: false`) or `docs/phase_f/l2_event/
evidence_index.json`. Promoting this into the generic event-class gate
pipeline is a separate, explicit registry-owning decision, out of scope
here.

## 2. Discovery and dedup

`discover_candidate_paths()` globs `per_process_traces_v2_event_s{seed:03d}/
FtsZPolymerization_200ticks.mat` across a 3-root fallback
(`DEFAULT_DATA_ROOTS`: worktree-local -> `E:/opencell` -> `/mnt/e/opencell`),
mirroring `tests/vivarium/l2_replay_common.py`'s `resolve_trace_path` --
raw `.mat` traces are `.gitignore`d, so a fresh worktree never has them
locally; the main checkout is the one physical location they are extracted
into.

`audit_pre_division_evidence()` hashes (sha256) every discovered candidate
before validating it: an identical trace filed under two seed directories
is flagged in `duplicate_seeds` and only the first-seen seed counts toward
the ensemble. A duplicated trace can never increase `len(found_seeds)`.

## 3. Window-contract validation

`validate_seed_window()` calls the shared, unmodified
`scripts.l2_event.window_loader.load_event_window()` (the M4 stride-1
metadata-contract loader), then layers FtsZ-specific checks that the
generic loader has no way to know about (it does not read the catalog):

* `process_name` matches `"FtsZPolymerization"`.
* `grid.seed` matches the seed implied by the directory name (a mislabeled
  or misplaced extraction output is refused, not silently trusted).
* `n_ticks == 200` (catalog `M_ticks`).
* `window_anchor is not None` -- the window must be division-anchored, not
  a fixed `tick_end`-only window (which cannot represent "ends at
  division").
* `window_anchor - tick_start + 1 == 200` exactly -- catches BOTH
  post-division leakage (span > 200: a tick beyond division crept in) and
  truncation (span < 200: the window starts too late, missing part of
  `[-200, 0]`).

Any violation raises `FtsZWindowContractError`; the seed is recorded in
`rejected_windows` with the exact reason and does not count toward
`found_seeds`.

## 4. Activity detection is NOT the monomer projection

`next_update`'s `discretize_enzymes`/`apply_substrate_limits` are
mass-preserving by construction (the v3.9 full-ODE-port fix note in the
catalog): FtsZ polymerization only redistributes existing subunits across
oligomer states (monomer -> dimer -> ... -> 9-mer), so
`dot(process.n_monomers, enzyme_delta)` is a CONSERVED invariant -- it reads
~0 whether or not real polymerization activity occurred that tick. Using
it as the activity signal would silently report "no activity" during heavy
polymerization, failing the "at least one real activity transition per
accepted seed" requirement.

The real activity signal is `enzyme_delta_l1()`: the raw per-species
enzyme-count-delta L1 norm for a tick (i.e. did FtsZ actually redistribute
any subunits this tick, regardless of whether the redistribution is
monomer-mass-neutral). `first_activity_transition()` is the preregistered
rule -- fixed before any seed's numbers are inspected -- returning the
index of the first tick with nonzero `enzyme_delta_l1`, computed
independently for the Karr side (`states_after - states_before` from the
trace) and the OC side (the real, honest, no-hint `next_update` delta).
`None` is a real finding (no transition in this window) and is never
coerced into a fabricated tick.

## 5. Monomer primary-channel statistic

The catalog declares `primary_channel: monomers`, but `next_update` emits
no `monomers` port (`ports_schema()` has none). This is resolved as a
read-only POST-UPDATE PROJECTION -- `project_monomer_total(process,
counts) = dot(process.n_monomers, counts)` -- rather than either
fabricating a fake port or ignoring the catalog's declared channel.
Because this quantity is conserved by construction (§4), the meaningful
per-tick statistic is the OC-vs-Karr DISCREPANCY in the projected delta
(`monomer_l1_mean`/`monomer_l1_max` per seed, aggregated in the audit
report's `monomer_primary_statistic`): both sides should individually be
~0, so a nonzero gap between them is a real defect (OC's discretization
diverging from Karr's), not distributional noise.

## 6. No-hint / no-oracle guards

`compute_seed_evidence()` asserts `not state.get("trace_hint")` both before
and after overlay, and wraps every `next_update` call in
`forbid_sut_oracle_file_io()` (defense in depth; production code under
`opencell/vivarium/` never opens the oracle itself). Only the canonical
fixture (`FtsZPolymerization_flat.mat`, loaded once at process
construction) is read from disk by the SUT.

## 7. Ensemble-completeness verdict

`audit_pre_division_evidence()` never reports `SUFFICIENT_ENSEMBLE` for
`len(found_seeds) < 50` -- there is no partial-credit branch (mirrors the
existing honest canary's `classify_ensemble_support`). When insufficient,
`deficit = 50 - len(found_seeds)` and `resumable_extraction_command()`
prints the exact, resumable MATLAB invocation
(`scripts/matlab/extract_ftsz_pre_division_window_seeds.m`) needed to close
the gap -- re-running it skips any seed whose output already exists.

## 8. Current real-world result (2026-08-05)

Zero `per_process_traces_v2_event_s*/FtsZPolymerization_200ticks.mat` files
exist in any worktree or the main checkout at the time of writing (verified
by exhaustive filesystem inventory across `E:\opencell-worktrees\*` and the
main checkout). Running `audit_pre_division_evidence()` against
`DEFAULT_DATA_ROOTS` therefore reports:

```
status=INSUFFICIENT_ENSEMBLE deficit=50/50
Resumable extraction command:
  matlab -batch "addpath(genpath('scripts/matlab')); extract_ftsz_pre_division_window_seeds(0, 49)"
```

MATLAB is available only on the Windows side (`E:\MATLAB\bin\matlab.exe`),
not inside WSL. A comparable division-anchored extraction for
RibosomeAssembly (`scripts/matlab/full_cycle_event_scan_v2.m`'s log) took
~104 minutes for a much shorter tick budget than a 50-seed x 200-tick FtsZ
division search would require; running the full extraction was out of
scope for this session per the task's explicit allowance to surface the
exact command and deficit instead of running it. This is the expected,
correct output of a fail-closed audit against a genuinely empty ensemble --
not a defect to be worked around by fabricating seeds or relabeling N=0/N=1
as sufficient.

## 9. What this is not

* Not a gate: no W1/Wasserstein threshold or split-half null is computed or
  invented here (future work, same as the superseded canary's own
  disclaimer).
* Not a re-extraction: no MATLAB/Octave process is invoked by importing or
  running this module; it only discovers/validates whatever already exists
  on disk and prints the command a human/CI job would run to close the
  gap.
