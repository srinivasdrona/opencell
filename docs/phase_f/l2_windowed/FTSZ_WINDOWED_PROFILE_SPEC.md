# FtsZPolymerization windowed/continuous fidelity profile — spec

> **2026-08-05 update:** the N=1, non-division-anchored honest diagnostic
> this spec documents (§3 onward) is superseded for CATALOG CONFORMANCE by
> the pre-division event-window evidence path in
> `scripts/l2_event/ftsz_pre_division_evidence.py` (spec:
> `docs/phase_f/l2_windowed/FTSZ_PRE_DIVISION_EVENT_WINDOW_SPEC.md`), which
> targets the LIVE, unedited `PROCESS_CATALOG.yaml` row (`bucket:
> EVENT_CLASS`, `M_ticks: 200`, `N_seeds: 50`,
> `seed_window.tick_range_from_division: [-200, 0]`) directly, rather than
> the `WINDOWED_CONTINUOUS_CLASS` reclassification this spec's §1 argues
> for. That reclassification (`proposed_patches/
> ftsz_polymerization_windowed_v1.catalog_patch.yaml`) remains unapplied.
> `tests/vivarium/test_karr_ftsz_polymerization_honest_canary.py` (this
> spec's diagnostic) is NOT deleted -- it remains valid N=1 evidence -- but
> it no longer represents the catalog-conformance evidence path for this
> process. This document's own content is otherwise unchanged below.

STATUS: branch-local spec for `agent/l2-ftsz-windowed-profile`. Documents the
Turn-1 intent (approved with adjudications), the Turn-2 implementation, and
the Turn-3 closeout (Opus review findings: unconditional stoichiometry check,
accurate per-clause coverage reporting, trace provenance anchoring, corrected
enzyme WID cardinality/mapping, and a non-dirtying telemetry artifact
design). Does not itself reclassify anything in the live catalog or event
registry — see
`proposed_patches/ftsz_polymerization_windowed_v1.catalog_patch.yaml` for
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
   **Called unconditionally on every tick** (Turn-3 fix), including ticks
   where the substrate delta dict is empty `{}` — an empty dict makes every
   `.get(wid, 0.0)` default to 0.0, which is only a valid outcome when
   `dot(n_gtp, enzyme_delta) == dot(n_gdp, enzyme_delta) == 0`. Turn-2's
   original `if substrate_delta:` guard would have silently skipped this
   check on a tick where a bug dropped the `substrates` key entirely; Turn-3
   removed that guard and added a mutation-inversion test
   (`test_empty_substrate_delta_fails_on_nonzero_coupling_ticks`) that forces
   `substrate_delta={}` against the real per-tick enzyme deltas and proves
   the check now fails on exactly the ticks with real nonzero GTP/GDP
   coupling (63/100 — independently re-derived in the test, not hardcoded).
3. **Integrality and finiteness**: every emitted enzyme/substrate delta is
   finite and an integer (reuses the shared `assert_delta_integral` helper
   pattern from `l2_replay_common.py`).
4. **Nonnegativity**: resulting enzyme/substrate counts (current + delta) are
   finite and nonnegative.

These are asserted with `==`/exact-integer checks, not `pytest.approx`
tolerances — there is no fudge factor to launder a real bug through.

## 6. Raw per-tick discrepancy telemetry (reported, not gated)

For each of the 100 ticks, the canary computes telemetry and (Turn-3) writes
it to pytest's `tmp_path` only, then compares it field-by-field (excluding
the environment-dependent `trace_path`) against a checked-in reference
snapshot at `docs/phase_f/l2_windowed/ftsz_seed0_honest_mode_telemetry.json`
as a reproducibility assertion. The test never overwrites that tracked file
as a side effect of running — regenerating the reference is a deliberate,
reviewed act (done once for this Turn-3 schema update; see git history of
that file). The telemetry includes:

- `enzymes` L1 and L∞ discrepancy between OC's honest-mode delta and Karr's
  observed delta (WID-aligned via `process.enzyme_wids`).
- `substrates` L1 and L∞ discrepancy (WID-aligned via `process.substrate_wids`).
- Summary stats (mean/max/zero-match-tick-count) per channel.
- `trace_sha256`: the exact SHA256 of the `.mat` file the run read from
  (see §8a, Trace provenance).
- `substrate_stoichiometry_clause_coverage`: per-clause branch-coverage
  counters (see table below) — explicitly NOT a correctness claim, since
  invariant equality is asserted unconditionally on all 100 ticks regardless
  of these counts (§5, item 2).

**Observed real values (seed 0, N=1, 100 ticks, honest ODE mode, no
trace_hint)**:

| channel | L1 mean | L1 max | zero-discrepancy ticks |
|---|---|---|---|
| `enzymes` | 11.69 | 29.0 | 0 / 100 |
| `substrates` | 1.18 | 6.0 | 37 / 100 |

**Substrate-stoichiometry clause coverage (branch coverage, not invariant
correctness — see the distinction below)**:

| clause | nonzero on | meaning |
|---|---|---|
| GTP coupling (`dot(n_gtp, enzyme_delta) != 0`) | 63 / 100 OC ticks | `GTP_delta == -n_gtp.d_enzyme - PI_delta` term actually exercised nonzero |
| GDP coupling (`dot(n_gdp, enzyme_delta) != 0`) | 1 / 100 OC ticks | `GDP_delta == -n_gdp.d_enzyme + PI_delta` term actually exercised nonzero |
| PI/H2O/H hydrolysis-shortfall (`PI_delta > 0`) | 0 / 100 OC ticks | **unexercised** — the shortfall-compensation branch (`H2O_delta == -PI_delta`, `H_delta == PI_delta`, and the `+ PI_delta` terms above) was checked as identically zero on every tick in this one seed; its nonzero behavior has never been validated by this canary |

**Exact invariant correctness is a separate claim from branch/clause
coverage.** The stoichiometry equations in §5 item 2 are asserted `==` on
all 100 ticks unconditionally, including the 37/100 ticks with zero
substrate delta and the 100/100 ticks with zero hydrolysis-shortfall value —
those ticks correctly satisfy the equations at value 0, but they do not
exercise (and therefore cannot falsify) the shortfall-compensation branch's
behavior when it is actually nonzero. Any future seed/trace where
`PI_delta > 0` occurs would be the first real test of that specific branch.

This is real, unmodified, non-fabricated telemetry from one run. It shows
nontrivial divergence between OC's honest BDF-integrated trajectory and
Karr's custom-ODE23S + independent-RNG-stream trajectory. This is expected
given different solvers and different stochastic discretization draws, and
is **explicitly not judged pass/fail** by this task (adjudication #1/#2) —
it is reported as diagnostic evidence for whoever eventually builds the
N=50 gate (§7).

### 6a. Trace provenance (N=1 anchor)

The canary asserts (fails loudly, not silently, on mismatch) that the trace
file `resolve_trace_path("FtsZPolymerization")` resolves to has this exact
SHA256 before doing anything else:

- **`FtsZPolymerization_100ticks.mat`** (the actual extraction target read by
  `cell_vector`/`resolve_trace_path` in this canary):
  `c0797bcb84fa6041875caddf6a7c195362fdad64fd80412a34946a914aaa9ee1`
  (full 64-hex-char SHA256, verified in-branch).

A different artifact exists elsewhere in this repo's inventory —
`data/karr_fixtures/per_process_replay/FtsZPolymerization.npz`, SHA256
`348db55cf64c97c11fc5e94f7f9d2b93f77a9da7edf93647d8e41570a311fdaf` — which
is **explicitly not** the extraction target of this canary. It is a
different replay run with divergent RNG pools/state (a separate harness
invocation, not the seed-0 Karr ground-truth trace), and must not be
conflated with the `.mat` trace above when reasoning about N=1 provenance.

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

- `enzyme_wids` has **11** entries (Turn-3 correction — an earlier draft of
  this spec incorrectly stated 5, which is actually the substrate cardinality
  below), verified in-branch from the live fixture:
  `['MG_224_MONOMER', 'MG_224_MONOMER_GDP', 'MG_224_MONOMER_GTP',
  'MG_224_2MER_GTP', 'MG_224_3MER_GTP', 'MG_224_4MER_GTP', 'MG_224_5MER_GTP',
  'MG_224_6MER_GTP', 'MG_224_7MER_GTP', 'MG_224_8MER_GTP',
  'MG_224_9MER_GTP']`. Index 0 = free FtsZ monomer
  (`enzyme_index_ftsz == 0`), index 1 = FtsZ-GDP monomer
  (`enzyme_index_ftsz_gdp == 1`), index 2 = FtsZ-GTP-activated
  monomer/nucleus seed (`enzyme_index_ftsz_gtp == 2`), indices 3-10 = growing
  polymer forms from the 2-mer through the 9-mer
  (`enzyme_index_ftsz_dimer == 3`, `enzyme_index_ftsz_9mer == 10`).
  `n_monomers = [1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9]` gives the monomer-equivalent
  weight per index (used by the conservation invariant); `n_gtp = [0, 0, 1,
  2, 3, 4, 5, 6, 7, 8, 9]` and `n_gdp = [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]` give
  the per-index GTP/GDP coupling weights used by the stoichiometry invariant
  (§5 item 2).
- `substrate_wids` = `['GDP', 'GTP', 'PI', 'H2O', 'H']` (**5** entries,
  indices 0-4). The hydrolysis-shortfall compensation vector (both MATLAB
  and OC) is `[+1, -1, +1, -1, +1]` in this exact order applied to
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
