# STATUS — Shared Chromosome-State Stage A+B Implementation

**Task:** Implement the accepted shared chromosome-state Stage A+B slice
(dec-007) in `fix/shared-chromosome-state-stage-ab-20261013`.
**Role:** DOER in the planner → test-writer → implementer → independent-reviewer
workflow. Design/tests frozen; not redesigned, not weakened.
**Starting HEAD:** `6741b16` (clean).
**Result:** Stage A+B implemented and verified against the frozen contract
(25/25 PASS). One commit landed. One demonstrated, unavoidable test
inconsistency is documented below (not patched around) per the task's own
"stop and document" instruction.

## Commits

1. `8ce84a9949730c70a3121b1dda693decac1fbcfe` — `feat(chromosome-rng):
   implement Stage A+B shared chromosome RNG stream (dec-007)`. All
   production/bookkeeping changes below.
2. (this STATUS + the provenance log entries) — see final commit in this
   branch's log after this file lands.

## Exact files changed

Production (Stage A+B, authorized write surface):
- NEW `opencell/util/chromosome_state_rand.py` — `ChromosomeStateRandStream`
  (DC-4 unified mcg16807 shim; identical arithmetic to the already-proven
  bit-identical `TxRegMcgRandStream`/`ChromCondMcgRandStream`, per Probe P1
  cited in the design doc). `opencell/util/chromcond_mcg_rand.py` and
  `opencell/util/txreg_mcg_rand.py` were **not** touched — DC-4's "fold into
  one class" intent is satisfied by the new class; the existing per-process
  dec-006 ledger-isolated files are left exactly as-is (lower risk, zero
  provenance-hash disturbance for their existing accepted evidence).
- `opencell/state/chromosome_store.py` — `CHROMOSOME_RAND_STREAM_KEY =
  "_shared_rand_stream_state"`, `_UNSEEDED_RAND_STREAM_STATE`,
  `ChromosomeStore._rand_stream` (live handle, `None` until seeded),
  `rand_stream()` / `rand_state()` / `set_rand_state()`, `to_state()` emits
  the leaf iff seeded, `from_state_mapping()` restores iff present and
  non-sentinel (sentinel treated as absent, never auto-seeds), `copy()`
  deep-copies the stream state (never shares the live object).
- `opencell/vivarium/karr_transcriptional_regulation.py` —
  `ports_schema()["chromosome"]` gains the `_shared_rand_stream_state` leaf
  (`_default` = int64 `[-1,-1]`, `_updater: "set"`, `_emit: True`).
  `__init__` no longer constructs a per-process `_chromosome_rng` stand-in
  (`self._chromosome_rng = None`). New
  `_resolve_chromosome_rng_for_tick(chrom_state, chromosome_store)` and
  `_chromosome_rand_stream_writeback()` helpers; `next_update` calls the
  former right after resolving `chromosome_store` and the latter
  unconditionally before returning, writing `update["chromosome"]
  ["_shared_rand_stream_state"]` every tick including zero-draw ticks.
  `_sample_accessible_sites_batched` is **byte-for-byte unchanged**.
- `opencell/vivarium/karr_composite.py` — `_seeded_chromosome_rand_stream_state(seed)`
  helper; `build_karr_chassis_v4`/`v5` gain `"chromosome": ("chromosome",)`
  in the `karr_transcriptional_regulation` topology entry and a seeded
  `_shared_rand_stream_state` leaf in `initial_state["chromosome"]` (seed 0,
  hardcoded — neither builder has a seed parameter); `build_karr_chassis_v6`
  inherits v5's already-seeded leaf via its existing
  `deepcopy(base_engine.initial_state)` (no second seed is ever
  constructed). New `_CallableInitialStateDict` makes v6's returned
  `Composite.initial_state` attribute a real `dict` for direct access while
  its `__call__` forwards to the original bound method, so every existing
  `composite.initial_state()` call site (e.g.
  `tests/vivarium/test_karr_protein_modification.py::test_chassis_seeded_mg109_complex_enzyme_drives_mg109_only_targets`)
  keeps working unchanged. One unrelated default-argument fix: see
  "Pre-existing bug fixed" below.
- `scripts/l2_4_verify_conservation.py` — `ConservationCollector.__init__`
  calls new `_seed_shared_chromosome_rand_stream(seed=seed)`, which
  overwrites `composite.initial_state["chromosome"]
  ["_shared_rand_stream_state"]` in place with
  `ChromosomeStateRandStream(seed).get_state()`. Ordinary per-entity
  reseeding (`_seed_entities`) is untouched.
- `scripts/run_chassis_v6_32400t.py` — same addition to
  `DiagnosticCollector.__init__`.

Required bookkeeping (tightly coupled to the above; not separately
authorized file-by-file in the task but necessary direct consequences of
line-number/wiring/hash changes caused by this change, consistent with
"fix bugs caused by or tightly coupled to your changes"):
- `data/karr_method_inventory/oc_method_map.yaml` — the three
  `TranscriptionalRegulation` anchors pointing at
  `KarrTranscriptionalRegulationProcess.next_update:1570` were updated to
  `:1655` (next_update's new start line after the new helper methods were
  inserted above it). Required for `scripts/l1b_method_completeness.py`.
- `data/schemas/per_process_wiring/TranscriptionalRegulation.yaml` — line
  ranges for `next_update` (now 1655-1765), `build_karr_chassis_v4` (now
  1119-1765) and `build_karr_chassis_v5` (now 1770-2659) refreshed; prose
  notes that said production topology "omits chromosome" / "OC production
  uses a continuously advancing process-local stand-in" updated to describe
  the Stage A+B state (chromosome port now wired; RNG now store-owned and
  serialized) while preserving the still-true Stage C/D/E deferrals
  (authoritative bound-site writeback, t0 sweep, inter-process draw
  interleaving). Required for `scripts/l1b_verify_wiring.py`
  `check_oc_anchors_resolve`.
- `docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml` —
  `source_tree.sha256` refreshed from `e828cc75...` to `49230da8...`
  (`scripts/pre_l25_honesty.py source-digest`, `file_count` unchanged at
  128 since the new `chromosome_state_rand.py` file is not yet a tracked
  wiring/method-map dependency of any process row). Required for
  `scripts/pre_l25_honesty.py audit` to report `INTEGRITY_OK` instead of
  `INTEGRITY_FAIL` on a stale-baseline false alarm (the actual blocker list
  — 23 blocked / 5 eligible — is byte-identical before and after; only the
  tree hash needed refreshing).
- `opencell/provenance/llm_interactions.jsonl` — two entries (initial +
  commit-SHA-bearing supersede), per the commit-cadence logging contract.
- `STATUS_stage_ab_impl.md` — this file.

## Pre-existing bug fixed (unrelated to RNG, required to execute the frozen test)

`build_karr_chassis_v5`'s own default `dynamic_bounds=False` crashes
unconditionally — confirmed **independent of every Stage A+B change** by
`git stash` to clean HEAD `6741b16` and calling `build_karr_chassis_v5()`
with zero arguments:

```
Exception: updater is absent at path ('substrates_allocated', 'karr_metabolism')
with value None for update {...}
```

(`vivarium/core/store.py:1655`, raised from `KarrAllocationStep`'s t=0
`run_steps()` inside `Engine.__init__`.) `build_karr_chassis_v5(dynamic_bounds=True)`
builds successfully on the same clean HEAD. `build_karr_chassis_v5` has
**zero callers anywhere in the repo** other than `build_karr_chassis_v6`
(which always explicitly passes `dynamic_bounds=dynamic_bounds`, itself
defaulting to `True`) — confirmed by repo-wide grep. The frozen test
`test_stage_ab_composite_builders_initial_state_chromosome_rand_stream`
calls `build_karr_chassis_v5()` with no arguments (v5 has no seed
parameter), which is the exact crashing invocation. Flipped the default to
`True` (matching v6's own default). This is a one-line default-argument
change with **zero possible regression** (no caller could have been relying
on the old, always-crashing default) and is required for the frozen test to
even construct a v5 chassis.

## Verification

1. **Frozen contract** — `bin\oc-pytest.cmd tests/vivarium/test_shared_chromosome_state_stage_ab.py -q`
   → **25 passed** (was 12 passed / 13 failed at the session's start,
   confirmed to reproduce exactly that baseline before any edits).
2. **TxReg fast set** — `bin\oc-pytest.cmd tests/vivarium/test_karr_transcriptional_regulation.py tests/vivarium/test_karr_transcriptional_regulation_anticheat.py tests/vivarium/test_karr_transcriptional_regulation_ledger_and_damage.py tests/vivarium/test_chromosome_rand_stream_ledger.py -q`
   → **87 passed, 5 failed** (92 collected). Clean-HEAD baseline (same 4
   files, `git stash`): **92 passed, 0 failed**. The 5 failures are a
   demonstrated, unavoidable consequence of the frozen contract — see
   "Documented test inconsistency" below. No other regression in this set.
3. **L2.1 replay** — `bin\oc-pytest.cmd tests/vivarium/test_karr_transcriptional_regulation_l2_replay.py -q -rs`
   → **2 passed** (100-tick canonical identity replay + 4000-tick event
   replay), **0 skipped**, bit-identical, unchanged from baseline. (Local
   trace artifacts were present under `data/m1_sources/karr_native/...`.)
4. **Compatibility** — `bin\oc-pytest.cmd tests/util/test_chromcond_mcg_rand.py tests/vivarium/test_karr_chromosome_condensation_chassis_wiring.py -q`
   → **27 passed, 1 xfailed** (expected xfail, pre-existing).
5. **L2.4 conservation** — `bin\oc-py.cmd scripts/l2_4_verify_conservation.py --ticks 100 --seeds 0,1,2,3 --out-dir tmp/stage_ab_l2_4 --fresh`
   → `PASS seeds=0,1,2,3 ticks=100 exchange_wids_skipped=124`.
6. **L1b + honesty** —
   - `bin\oc-py.cmd scripts/l1b_method_completeness.py` →
     `L1b METHOD-COMPLETENESS: PASS (115/115 runtime methods resolved)`.
   - `bin\oc-py.cmd scripts/l1b_verify_wiring.py` →
     `L1b wiring conformance: PASS (28/28 rows PASS)`.
   - `bin\oc-py.cmd scripts/pre_l25_honesty.py audit` →
     `PRE-L2.5 HONESTY BASELINE: INTEGRITY_OK; eligible=5/28; blocked=23`
     (byte-identical blocker list to clean-HEAD baseline; only the source
     hash needed refreshing, see above).
7. **Lint / diff hygiene** — `ruff check` on every touched Python file: zero
   new findings (two pre-existing-and-untouched findings in
   `karr_composite.py`/`l2_4_verify_conservation.py` caused by my edits
   shifting import order/Yoda-condition style were fixed; the remaining
   `run_chassis_v6_32400t.py`/`l2_4_verify_conservation.py` findings are
   confirmed pre-existing via `git stash` and untouched). `git diff --check`
   → clean (no whitespace errors).

No skips or warnings were produced by any of the above commands beyond the
pre-existing `l1b_verify_wiring.py` warnings (missing-MATLAB-tree skip
notices and pre-existing WID-grouping warnings, unrelated to this change
and unchanged from baseline).

## Source/design conformance (dec-007 / design doc)

- **DC-2/DC-4** — one state-owned, serialized `ChromosomeStateRandStream`;
  no second RNG authority; unified generator arithmetic. ✅
- **§4.3 exact contract** — leaf path
  `("chromosome", "_shared_rand_stream_state")`, int64 `[seed, mcg_state]`,
  `set` updater, `_emit: True`, sentinel `[-1,-1]` default. ✅
- **Absent-key semantics** — seed-once only at initial-state construction
  (composite builders); `next_update` never silently reseeds on an
  absent/sentinel leaf for a genuinely topology-wired, never-before-seeded
  call (hard `RuntimeError`, matches dec-007 Decision 3 verbatim). ✅ — with
  one necessary, explicitly-scoped back-compat exception documented below.
- **Stage B RNG-only swap** — `_sample_accessible_sites_batched`'s
  candidate/affinity/accessibility/exclude-overlap logic is **byte-for-byte
  unchanged**; only the RNG *provider* (`self._chromosome_rng`) changes from
  a per-process stand-in to the store-owned handle. Draw **sequence** is
  preserved for the single-seed replay baseline (verified bit-identical,
  item 3 above). ✅
- **Private `tf_bound_promoters` dual representation** — untouched, still
  present and `accumulate`-updated; no Stage C writeback/removal attempted.
  ✅ (confirmed by the frozen
  `test_stage_b_private_tf_bound_promoters_remains_temporary_surface`.)
- **No ledger in production** — `karr_transcriptional_regulation.py`
  imports no `*LedgerRandStream` symbol anywhere (confirmed by the frozen
  AST-scan test); the new `ChromosomeStateRandStream` class has no file I/O
  of any kind. ✅
- **Checkpoint honesty** — `opencell/core/checkpoint.py` untouched; no
  chromosome persistence claimed. ✅ (confirmed by the frozen
  `test_stage_a_checkpoint_limitation_explicit`.)
- **No Stage C/D/E footprint** — no `sample_accessible_regions` on the
  store, no TxReg t0 pre-binding sweep, no `ChromosomeCommitStep`, no
  two-column fold-change, no checkpoint.py expansion. ✅

## Documented test inconsistency (not weakened — per task instruction)

**Claim.** The frozen contract's
`test_stage_a_absent_key_init_seed_once_vs_next_update_fail_closed`
requires `next_update` to raise `RuntimeError` **unconditionally** — even
when the incoming state's TF counts are all zero (i.e. no draw is
"genuinely needed" by any reasonable reading of `_bind_transcription_factors`'s
`if free_copies[tf_i] <= 0: continue` early-exit) — whenever the chromosome
branch is a bare/synthetic dict (`{}`, or `{_shared_rand_stream_state:
sentinel}`) with no legacy `polymerizedRegions`/`monomerBoundSites`/
`complexBoundSites` keys and no externally-installed `_chromosome_rng`.
This is **structurally indistinguishable** (same process construction, same
chromosome-dict shape, same zero-draw path) from 5 pre-existing tests that
call `next_update` on a real, fixture-loaded
`KarrTranscriptionalRegulationProcess(...)` with a hand-built
`"chromosome": {}` and never install `_chromosome_rng` first:

1. `tests/vivarium/test_karr_transcriptional_regulation.py::test_no_free_tfs_no_binding_change`
   — `_empty_tr_state(p)["chromosome"] == {}`, all TF counts 0.0 (byte-for-byte
   the same shape as the frozen test's `state_missing`).
2. `tests/vivarium/test_karr_transcriptional_regulation.py::test_steady_state_binding_fraction`
   — same `_empty_tr_state` base, nonzero TF counts, 100 real `next_update`
   ticks expecting genuine stochastic binding to succeed.
3. `tests/vivarium/test_karr_transcriptional_regulation_anticheat.py::test_bound_tfs_uses_column0_only_not_sum_of_both_columns`
   — `_empty_state(p)["chromosome"] == {}`, TF count 0.0.
4. `tests/vivarium/test_karr_transcriptional_regulation_anticheat.py::test_tf_binding_tu_level_view_is_not_read_as_binding_input`
   — same base, TF counts 5.0 (real draws expected to succeed).
5. `tests/vivarium/test_karr_transcriptional_regulation_anticheat.py::test_fake_trace_hint_in_state_has_no_effect_on_output`
   — same base, TF counts 3.0 (real draws expected to succeed).

**Proof the conflict is real, not an implementation gap.** I implemented a
3-tier resolution order in `_resolve_chromosome_rng_for_tick` specifically
to minimize collateral damage:
1. valid (non-sentinel) leaf → always wins;
2. already-installed `self._chromosome_rng` (covers every test that
   explicitly sets `p._chromosome_rng = ...` before calling `next_update` or
   `_sample_accessible_sites_batched` directly — `_make_toy_process`-based
   tests, the dec-006 ledger-replay harness, `test_karr_transcriptional_regulation_ledger_and_damage.py`'s
   `_FixedOrderStream`/`_SequencedOrderStream` doubles);
3. legacy `polymerizedRegions`/`monomerBoundSites`/`complexBoundSites`
   fields present but no RNG leaf → bootstrap a fresh seed-derived stream
   once (covers the **un-ledgered 100-tick canonical L2.1 replay**, whose
   `state["chromosome"]` carries those three legacy fields via
   `build_state_template`'s schema defaults but never the new RNG leaf —
   confirmed via instrumented draw-count probe: exactly 4 real draws occur
   at tick 15 of that replay, with the sentinel leaf present the entire
   run, and this resolution order lets it continue using the same
   continuously-advancing stream the pre-Stage-B code always used, hence
   bit-identical);
4. otherwise → `RuntimeError` (satisfies the frozen test).

This 3-tier order is the **most permissive** design that still satisfies
the frozen test, and it was reverse-engineered specifically to rescue as
many pre-existing tests as structurally possible. The 5 failing tests use
`_empty_tr_state`/`_empty_state` helpers that construct `"chromosome": {}`
— literally the same empty-dict shape as the frozen test's `state_missing`
— **with no override installed**, so tier 2 and tier 3 both fail to apply,
and tier 4 (the frozen test's own required behavior) necessarily fires.
There is no `next_update`-observable signal that distinguishes "this is the
frozen unit test verifying fail-closed" from "this is
`test_no_free_tfs_no_binding_change` verifying zero-TF-count no-op" — both
are, by construction, a fresh `KarrTranscriptionalRegulationProcess(...)`,
never overridden, given an empty chromosome dict. Making tier 4 permissive
enough to also pass these 5 tests (e.g. falling back to a bootstrapped
stream whenever `self._chromosome_rng is None`, the way tier 3 does)
necessarily also makes `test_stage_a_absent_key_init_seed_once_vs_next_update_fail_closed`
pass incorrectly (no `RuntimeError` raised), **directly weakening the
frozen contract**. Per the task's explicit instruction — "If a test is
demonstrably inconsistent with dec-007/design, stop, commit any
independent green chunk, and document exact evidence in STATUS instead of
weakening it" — I implemented the frozen contract faithfully and am
documenting this exact, demonstrated conflict rather than special-casing
around it or editing the non-frozen test files (which are also outside the
authorized write surface for this task).

**Recommendation for the planner/reviewer:** either (a) relax the frozen
test's `state_missing`/`state_sentinel` sub-case to also require nonzero TF
counts (making it a true "genuinely needs a draw" fail-closed check,
consistent with dec-007's own qualifying clause — "Ordinary production
`next_update` **that genuinely needs a draw** MUST..."), or (b) accept that
`_empty_tr_state`/`_empty_state` in the 5 affected pre-existing test files
need a one-line update to supply a valid seeded chromosome leaf (outside
this task's authorized write surface, so not attempted here).

## Remaining deferred stages (explicitly out of scope, confirmed untouched)

- Stage C — `sample_accessible_regions` centralization, shared bound-site
  writeback, private `tf_bound_promoters` removal (A1 claim).
- Stage D — TxReg t0 pre-binding sweep.
- Stage E — `ChromosomeCommitStep` multi-consumer owner, intent leaves,
  DNADamage/DNASupercoiling/Replication shared-stream migration.
- Two-column (`nTU x 2`) `tx_rate_fold_change` emission.
- `opencell/core/checkpoint.py` cross-run chromosome persistence.

## Final verdict

Frozen Stage A+B contract: **25/25 PASS**. All verification gates green.
The documented 5-test synthetic helper inconsistency is fully resolved
by the test-author follow-up below.

## Test-Author Follow-Up (2026-10-14): Synthetic Helper Correction (Resolved)

**Adjudication:** Under dec-007 Decision 3 and design §4.3, production topology
seeds `_shared_rand_stream_state` once at init and `next_update` writes back the
advanced state on every tick including zero-draw ticks. The 5 pre-existing
synthetic tests in `test_karr_transcriptional_regulation.py` and
`test_karr_transcriptional_regulation_anticheat.py` constructed bare states with
`chromosome: {}` and no installed stream, triggering the fail-closed guard
intended for unseeded production execution.

**Correction applied (test-only):**
1. `tests/vivarium/test_karr_transcriptional_regulation.py`:
   - Updated `_empty_tr_state` to populate `chromosome: {"_shared_rand_stream_state": np.array([seed, int(stream._mcg_state)], dtype=np.int64)}` matching the seed-once topology contract.
   - Updated `_apply_full_update` to propagate `update.get("chromosome")` onto `state["chromosome"]` so multi-tick tests (`test_steady_state_binding_fraction`) advance state faithfully across ticks.
2. `tests/vivarium/test_karr_transcriptional_regulation_anticheat.py`:
   - Updated `_empty_state` to populate `chromosome: {"_shared_rand_stream_state": ...}` with the process seed.
3. Production remains untouched and frozen; explicit tests that missing/sentinel state fails closed and ledger-injection tests are fully preserved.

**Results after correction:**
- `test_shared_chromosome_state_stage_ab.py`: **25/25 PASS** (43.7s)
- TxReg 4-file fast selection (`test_karr_transcriptional_regulation.py`, `test_karr_transcriptional_regulation_anticheat.py`, `test_karr_transcriptional_regulation_ledger_and_damage.py`, `test_chromosome_rand_stream_ledger.py`): **92/92 PASS** (132.7s)
- Canonical TxReg replay (`test_karr_transcriptional_regulation_l2_replay.py`): **2/2 PASS** (241.8s)
- `ruff check` / `git diff --check`: clean.
