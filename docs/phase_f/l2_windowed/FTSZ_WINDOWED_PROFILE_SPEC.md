# FtsZPolymerization windowed/continuous fidelity profile — spec

STATUS: branch-local spec for `agent/l2-ftsz-windowed-profile`. Documents the
Turn-1 intent (approved with adjudications) and the Turn-2 implementation.
Does not itself reclassify anything in the live catalog or event registry —
see `proposed_patches/ftsz_polymerization_windowed_v1.catalog_patch.yaml` for
the proposed (unapplied) patch.

## 1. Why FtsZPolymerization must leave `EVENT_CLASS`

`FtsZPolymerization.m` (`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/
+cell/+sim/+process/FtsZPolymerization.m`) is continuous polymer-state ODE
kinetics (activation/exchange/nucleation/elongation reactions integrated by a
custom modified-ODE23S solver every tick), not a binary/sparse firing event.
It has no analog to RibosomeAssembly's "does complex X appear at tick T"
question — every tick in the pre-division window produces a nonzero enzyme
population update. `docs/phase_f/l2_event/event_registry.yaml`'s existing
FtsZ row already carries an M5/Opus5 note making exactly this point
(`in_scope_v4: false`, "SHOULD leave the event-class profile entirely"); this
task acts on that note without editing the note itself or the live registry.

Cytokinesis is explicitly out of scope for this task (adjudication #7 /
non-goal): it remains event-class and consumes explicit ring/geometry state
that FtsZ does not own. No code in this branch touches
`karr_cytokinesis.py` or its tests.

## 2. Gate channels

| channel | role | rationale |
|---|---|---|
| `enzymes` | **primary gate channel** | ODE-integrated every active tick (100/100 in the seed-0 trace); this is the actual polymer-state observable Karr's `diff`/`jacobian` model targets. |
| `substrates` | **secondary/conservation gate channel** | consumed via `applySubstrateLimits`'s GTP/GDP demotion and PI/H2O/H hydrolysis-shortfall bookkeeping (60/100 ticks mutated in the seed-0 trace); gated on exact stoichiometric self-consistency, not a distributional distance. |
| `boundEnzymes` | **diagnostic only** | 0/100 mutated ticks in the real trace and in `fts_z_polymerization.toml`'s `activity_profile` — never active for this process; excluded from the gate per adjudication #4. |
| `ftsz_ring_count`, `complete` | **diagnostic only (OC-only)** | not written by Karr's `FtsZPolymerization.m` at all — these are OC/Cytokinesis-facing derived signals, not primary channels of this process. Excluded from the gate per adjudication #4; promoting either into the gate is exercised as an explicit inversion test (`test_diagnostic_only_channels_excluded_from_gate_set`). |

`GATE_CHANNELS = ("enzymes", "substrates")` is enforced in code
(`tests/vivarium/test_karr_ftsz_polymerization_honest_canary.py`) and is the
single source of truth for this table — the spec text must not drift from
that constant.

## 3. Window / support

- Window: full 100-tick trace (`FtsZPolymerization_100ticks.mat`, seed 0),
  matching the only Design-A per-process trace that exists on disk for this
  process (`data/m1_sources/karr_native/per_process_traces_v2/`). No new
  extraction was performed or is proposed by this task.
- Per-tick metric, not a single end-of-window distributional summary: the
  canary reports L1/L∞ discrepancy between OC's honest-mode `enzymes`/
  `substrates` delta and Karr's per-tick delta at every one of the 100 ticks,
  plus structural-invariant pass/fail per tick.
- Seed count: **N=1** (seed 0). This is the only seed that exists anywhere in
  this repo or any of its worktrees/mirrors for this process (confirmed by
  identical SHA256 of `per_process_replay/FtsZPolymerization.npz` across all
  27 worktrees + main + mirrors during Turn-1 inventory). `required_n_seeds`
  in the (proposed, unapplied) catalog patch is 50, matching the existing
  RibosomeAssembly precedent and Design-A convention.

## 4. Non-vacuity

The canary independently confirms (before any discrepancy computation) that
neither Karr's nor OC's per-tick trajectory is degenerate:

- Karr side: `enzymes` mutated on 100/100 ticks, `substrates` on 60/100 ticks
  in the real trace (matches `fts_z_polymerization.toml`'s
  `activity_profile`).
- OC side (honest mode, no `trace_hint`): `enzymes` nonzero-delta on 100/100
  ticks in the observed run.

A run that silently produced an all-zero/constant OC trajectory would fail
this guard rather than vacuously satisfying "no discrepancy" (see inversion
test `test_constant_trajectory_would_fail_nonvacuity_guard`, which proves the
*Karr-faithful* degenerate case — all-zero enzymes gate — is exactly the
shape the nonvacuity guard exists to reject if it ever showed up
unexpectedly on the honest-mode side).

## 5. Exact structural invariants (no invented tolerance)

Per adjudication #2, no numeric discrepancy threshold is derived from the
ODE solver's `rtol`/`atol` or from any other ad hoc choice. Instead, the
canary enforces invariants that are exactly provable, tick-by-tick, from
`FtsZPolymerization.m`'s own algebra:

1. **Monomer-count conservation**: `dot(n_monomers, enzyme_delta) == 0`
   exactly, every tick, unconditionally. Provable from both
   `discretizeEnzymes`'s internal conservation loop and
   `applySubstrateLimits`'s demotion loops, both of which preserve
   monomer-equivalents by construction.
2. **Substrate stoichiometry self-consistency**, derived from emitted deltas
   alone (not a reimplementation of the internal clamp-loop branching), using
   `PI_delta` as the shortfall proxy (PI has no other source term in this
   process): `H2O_delta == -PI_delta`, `H_delta == PI_delta`,
   `GDP_delta == -dot(n_gdp, enzyme_delta) + PI_delta`,
   `GTP_delta == -dot(n_gtp, enzyme_delta) - PI_delta`, and `PI_delta >= 0`.
3. **Integrality and finiteness**: every emitted enzyme/substrate delta is
   finite and an integer (reuses the shared `assert_delta_integral` helper
   pattern from `l2_replay_common.py`).
4. **Nonnegativity**: resulting enzyme/substrate counts (current + delta) are
   finite and nonnegative.

These are asserted with `==`/exact-integer checks, not `pytest.approx`
tolerances — there is no fudge factor to launder a real bug through.

## 6. Raw per-tick discrepancy telemetry (reported, not gated)

For each of the 100 ticks, the canary computes and writes to
`docs/phase_f/l2_windowed/ftsz_seed0_honest_mode_telemetry.json`:

- `enzymes` L1 and L∞ discrepancy between OC's honest-mode delta and Karr's
  observed delta (WID-aligned via `process.enzyme_wids`).
- `substrates` L1 and L∞ discrepancy (WID-aligned via `process.substrate_wids`).
- Summary stats (mean/max/zero-match-tick-count) per channel.

**Observed real values (seed 0, N=1, 100 ticks, honest ODE mode, no
trace_hint)**:

| channel | L1 mean | L1 max | zero-discrepancy ticks |
|---|---|---|---|
| `enzymes` | 11.69 | 29.0 | 0 / 100 |
| `substrates` | 1.18 | 6.0 | 37 / 100 |

This is real, unmodified, non-fabricated telemetry from one run. It shows
nontrivial divergence between OC's honest BDF-integrated trajectory and
Karr's custom-ODE23S + independent-RNG-stream trajectory. This is expected
given different solvers and different stochastic discretization draws, and
is **explicitly not judged pass/fail** by this task (adjudication #1/#2) —
it is reported as diagnostic evidence for whoever eventually builds the
N=50 gate (§7).

## 7. Future N=50 gate contract (documented now, NOT implemented)

Per adjudication #2, this task does **not** implement a threshold, invented
or otherwise. When 49 additional seeds of `FtsZPolymerization_100ticks.mat`
exist on disk (mirroring the RibosomeAssembly precedent's exact missing-data
shape — see `docs/phase_f/l2_event/RIBOSOME_ASSEMBLY_GATE_ADAPTER_REPORT.md`
for the analogous report structure), the eventual gate must:

- Use a **Karr-only seed-cluster / split-half null**: partition the 50 Karr
  seeds into two halves, compute the chosen distance metric (below) between
  the two Karr-only halves to build an empirical null distribution of
  "how different do two honest Karr runs look from each other", and compare
  the OC-vs-Karr distance against that null — not against a hand-picked
  number.
- Use `wasserstein_over_wid_intersection()` (already implemented in
  `tests/vivarium/l2_replay_common.py`, used elsewhere in this repo for
  analogous distributional gates) as the per-tick-vector W1/multivariate
  component metric, projected onto the WID intersection of OC's and Karr's
  `enzymes`/`substrates` channels.
- Preregister the aggregation (e.g. mean-over-ticks W1, or a specific
  quantile) **before** looking at the N=50 OC-vs-Karr numbers, exactly as
  the split-half null requires to be meaningful.
- Continue to gate `enzymes` as primary and `substrates` as
  secondary/conservation-only (§2) — this task does not revisit that
  channel split.
- Continue to exclude `boundEnzymes`/`ftsz_ring_count`/`complete` from the
  gate (§2) unless a separate, explicit future decision promotes one of
  them, with its own justification.

This is a contract for future work, not a partially-implemented gate. No
threshold, W1 cutoff, or pass/fail number is hardcoded anywhere in this
branch.

## 8. Karr↔OC WID / index mapping (for reference)

- `enzyme_wids` (5): index 0 = free FtsZ monomer, 1 = FtsZ-GDP monomer,
  2 = FtsZ-GTP-activated monomer/nucleus seed, 3.. = growing polymer forms up
  to the 9-mer (`enzyme_index_ftsz`, `enzyme_index_ftsz_gdp`,
  `enzyme_index_ftsz_9mer` name the boundary indices used by the invariant
  checks). `n_monomers` gives the monomer-equivalent weight per index (used
  by the conservation invariant).
- `substrate_wids` = `['GDP', 'GTP', 'PI', 'H2O', 'H']` (indices 0-4). The
  hydrolysis-shortfall compensation vector (both MATLAB and OC) is
  `[+1, -1, +1, -1, +1]` in this exact order applied to
  `[GDP, GTP, PI, H2O, H]` — i.e. GTP genuinely is reduced by the shortfall
  term too, not just GDP/PI/H2O/H (this was mis-stated in an earlier Turn-1
  draft and corrected before this spec was written).
- `boundEnzymes`: present in the catalog's declared state groups but has zero
  mutated ticks in the real trace; not written meaningfully by either side
  for this process.
- **No channel is primary in this profile unless OC's `next_update` actually
  writes it.** The catalog's current `monomers` primary/output channel claim
  fails this test (§9) and is corrected in the proposed patch, not promoted
  into this profile's gate.

## 9. The fictitious `monomers` channel (catalog defect, not fixed here)

`PROCESS_CATALOG.yaml`'s current `FtsZPolymerization` row declares
`primary_channel: monomers` and `output_channels: [substrates, monomers]`.
Both claims are false against the current implementation:

- `fts_z_polymerization.toml`'s `monomers` state group is empty.
- `KarrFtsZPolymerizationProcess.ports_schema()` declares no `monomers` port
  at all.
- `next_update` never emits a `monomers` key.

This task does **not** edit the live catalog (adjudication #3/#6 — central
catalog changes stay serialized for later). The correction is captured as an
unapplied proposed patch:
`proposed_patches/ftsz_polymerization_windowed_v1.catalog_patch.yaml`.

## 10. Non-goals (this task)

- No changes to `karr_cytokinesis.py` or any Cytokinesis test/doc.
- No new MATLAB/Octave extraction and no new trace generation of any kind.
- No edits to the live `PROCESS_CATALOG.yaml` or
  `docs/phase_f/l2_event/event_registry.yaml` — only a branch-local proposed
  patch doc.
- No implementation of the N=50 gate itself (§7) — contract only.
- No change to `karr_ftsz_polymerization.py`'s `next_update`/`trace_hint`
  short-circuit behavior — it is documented (as plumbing-only,
  `tests/vivarium/test_karr_ftsz_polymerization_l2_replay.py`) and covered by
  an inversion test proving it is mechanically real, but not removed. Its
  removal (if ever decided) is a separate change with its own review.

## 11. Test inventory

- `tests/vivarium/test_karr_ftsz_polymerization_honest_canary.py` — the
  honest-mode (no `trace_hint`) per-tick windowed canary described above.
  Always ends in `INSUFFICIENT_ENSEMBLE` / `pytest.skip(...)` for N=1; never
  reports `PASS`.
- `tests/vivarium/test_karr_ftsz_polymerization_honest_canary_inversions.py`
  — 8 inversion tests (hint-leakage mechanics, constant-trajectory
  nonvacuity guard, wrong-WID-order detection, threshold-fabrication static
  check, N=1-promotion boundary test, degenerate-timestep solver no-op,
  global-RNG isolation, OC-only-diagnostic-exclusion). All 8 pass.
- `tests/vivarium/test_karr_ftsz_polymerization_l2_replay.py` — retained
  unchanged in logic, relabeled via docstrings as PLUMBING-ONLY evidence
  (its unconditional `overlay_trace_after_hint` on `enzymes` means its green
  result demonstrates state-plumbing correctness, not honest ODE-biology
  fidelity).
