# STATUS_L21_DNADAMAGE_ACTIVE_FIX.md

Worktree: `E:\opencell-worktrees\fix-l21-dnadamage-active`
Branch: `agent/l21-dnadamage-active-fix-20260903` (based on `0cb1c83`)
Scope: close DNADamage's RNG-fidelity gap (mcg16807 vs numpy PCG64), re-run the
L2.1 active-window audit and L2.2 event verifier, document results. **Not
pushed/merged to main**, per instruction.

## Authoritative PROCESS_CATALOG entry (quoted verbatim before edits)

`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:404-420`:

```yaml
- name: DNADamage
  oc_module: opencell/vivarium/karr_dna_damage.py
  bucket: EVENT_CLASS
  harness_type: event_class
  in_scope_L2_2: true
  M_ticks: 20
  N_seeds: 50
  event_density: sparse
  input_channels: [substrates, chromosome]
  output_channels: [substrates, chromosome]
  primary_channel: chromosome
  primary_projection: [damage_event_present, damagedBases.delta_nnz, abasicSites.delta_nnz,
    strandBreaks.delta_nnz, damagedSugarPhosphates.delta_nnz, intrastrandCrossLinks.delta_nnz,
    hollidayJunctions.delta_nnz, gapSites.delta_nnz]
  primary_distance: hurdle_event_rate_plus_conditional_scaled_distance
  karr_artifact: per_process_traces_v2
  rationale_M: "single randperm, independent reactions; small M sufficient"
  notes: "v3.1 (2026-06-14): reclassified to EVENT_CLASS per Day-28 audit. ...
    [stale narrative predating the accepted genuine-corpus/rate-law rewrite;
    see docs/phase_f/l2_event/event_registry.yaml and this branch's own
    evidence_index.json row for current status -- catalog `notes` text was
    NOT edited this turn, per scope: this turn only touches RNG fidelity]"
  blocked_on: ["MISSING_NONTRIVIAL_KARR_STIMULUS_TRACE: ... [also stale --
    the genuine_signedzero_canary_v4/full_v2 55-trace corpus and the L2.2
    event verifier below have since superseded this note; not edited here,
    out of this turn's scope]"]
```

The `notes`/`blocked_on` prose in the tracked catalog file predates the
genuine-corpus L2.2 work accepted in sibling worktrees/branches and is
**not currently accurate**; it was intentionally left untouched this turn
(catalog narrative edits are out of scope for an RNG-fidelity fix). The
authoritative, current state is this file plus
`docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` and
`docs/phase_f/l2_2_design_a/evidence_index.json`.

## Primary sources read (local, no web)

- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m`
  — `constructRandStream`/`seedRandStream`: every process gets its own
  `RandStream('mcg16807')`, seeded from the same scalar `simulation.seed`.
- `.../+cell/+sim/+process/DNADamage.m` (`evolveState`, ~L537) — DNADamage's
  own stream draws exactly once per tick: `randperm(numReactions)`.
- `.../+cell/+sim/+state/Chromosome.m` (`sampleAccessibleSites` ~L539,
  `setSiteDamaged` ~L2490) — all site-count/position/strand/selection draws
  come from `this.randStream`, i.e. the **Chromosome state object's**
  stream, shared and advanced by most/all 28 Karr processes across the
  full simulation.
- `.../+util/RandStream.m` — `stochasticRound` (unconditional single draw,
  even for `value<=0`/exact integers) and `randomlySelectNRows`
  (`randsample(stream, n, k, false)`).
- Real local MATLAB (`E:\MATLAB\bin\matlab.exe`, via
  `scripts/tools/run_matlab_slot.ps1 -Slots 4`) — used to empirically
  derive/verify the mcg16807 core LCG and its `rand`/`randi`/`randperm`/
  `stochasticRound` wrapper semantics byte-for-byte, since these are
  MATLAB builtins not present in the local WholeCell source tree. No web
  used. Probe scripts were throwaway (`tmp/probe_*.m`, `tmp/probe_lcg*.py`,
  not committed).

## RNG mapping / draw ledger

| Karr call (MATLAB) | OC stream / method | Bit-identity status |
|---|---|---|
| `Process.randStream = RandStream('mcg16807'); reset(seed)` | `KarrMcg16807Stream(effective_seed)` | Core LCG verified byte-for-byte vs real MATLAB for seeds {1, 12345, 2000, 2147483646} |
| `DNADamage.randStream.randperm(numReactions)` | `self._reaction_order_rng.randperm(n)` | **Bit-identical-capable** — genuinely isolated, own stream, own seed |
| `RandStream.stochasticRound(value)` (via Chromosome) | `self._site_sampling_rng.stochastic_round(value)` | Formula verified byte-for-byte (unconditional draw, `roundUp = rand() < mod(value,1)`); stream itself is a stand-in (see ceiling below) |
| `ceil(dnaLength*rand())` / `ceil(nStrands*rand())` (Chromosome position/strand candidates) | `self._site_sampling_rng.randi(dna_length)` / `randi(n_strands)` | Formula verified byte-for-byte; stream is a stand-in |
| `randsample(stream, n, k, false)` (`randomlySelectNRows`) | `self._site_sampling_rng.randsample_without_replacement(n, k)` | **Disclosed approximation**: real MATLAB consumes a variable, shape-dependent draw count (sometimes `n`, sometimes `2k`) that could not be fully reverse-engineered for all `(n,k)`; approximated as `randperm(n)[:k]`, matching the existing convention already used by the shared (untouched) `opencell/util/matlab_rng.py::MatlabRandStream.randsample()` |

**Architectural ceiling (unchanged by this fix, disclosed up front):** Karr's
real site-sampling draws come from `Chromosome.randStream`, a single stream
advanced by most/all 28 processes across the whole simulation history. True
bit-identity for those draws is unreachable from an isolated single-process
DNADamage replay. `_site_sampling_rng` is therefore a freshly-seeded,
structurally-faithful **stand-in** stream (every formula literal-Karr), not
a bit-identical replay of the shared stream. Only DNADamage's own
`randperm(numReactions)` draw is genuinely isolated and now bit-identical-capable.

**Seed range:** MATLAB accepts `seed=0` via an internal substitution this
module's black-box probing could not identify (does not fit `seed*65536`).
Karr's real seeds are always large nonzero integers, so `KarrMcg16807Stream`
fails closed (`ValueError`) on `seed<=0`. `KarrDNADamageProcess.__init__`
substitutes `effective_seed = seed_param if seed_param > 0 else 1` only for
constructing the internal streams, to preserve the widespread `rng_seed: 0`
default-parameter convention used elsewhere in the repo without crashing;
any genuine explicit seed passes through unchanged.

## Code changes

- **NEW** `opencell/vivarium/karr_dna_damage_rng.py` — `KarrMcg16807Stream`:
  `rand`, `rand_vector`, `randi`, `randperm`, `randsample_without_replacement`,
  `stochastic_round`. Process-local, does not touch the shared
  provenance-hashed `opencell/util/matlab_rng.py`.
- **NEW** `tests/vivarium/test_karr_dna_damage_rng.py` — 19 tests: real-MATLAB
  byte-for-byte validation (4 seeds × rand/randi/2×randperm), fail-closed
  seed tests, unconditional-draw `stochastic_round` tests, 4 inversion tests
  (PCG64 substitution diverges, skipped-draw-for-nonpositive-value desyncs
  the stream, wrong `randi` endpoint/order diverges, no oracle/trace file
  I/O in the production module). **19/19 pass.**
- **MODIFIED** `opencell/vivarium/karr_dna_damage.py`:
  - `__init__`: replaced `np.random.default_rng(seed)` with two
    `KarrMcg16807Stream` instances (`_reaction_order_rng`, `_site_sampling_rng`).
  - `_reaction_order`: now `self._reaction_order_rng.randperm(n)`.
  - `_stochastic_round`: removed the old `value<=0` skip-the-draw bug;
    delegates unconditionally to `self._site_sampling_rng.stochastic_round`.
  - `_sample_reaction_coords` (non-string branch): candidate selection now
    `self._site_sampling_rng.randsample_without_replacement(...)` instead of
    a reused, stream-conflating `_reaction_order` call.
  - `_sample_literal_motif_sites`: position/strand draws now per-element
    `self._site_sampling_rng.randi(...)` loops (literal Karr
    `ceil(len*rand())` formula, separate position-then-strand draw order,
    not interleaved); final over-threshold selection now
    `randsample_without_replacement` instead of `np.random.permutation`.
  - Confirmed via grep: **zero remaining `np.random` references** anywhere
    in the file.
- **MODIFIED** `tests/vivarium/test_karr_dna_damage.py`:
  - Fixed `test_stochastic_round_is_unbiased`'s outdated assertion
    (`_stochastic_round(-1.0) == 0` → `== -1`, matching the corrected
    literal semantics: `mod(-1.0,1)==0` ⇒ `roundUp` always False ⇒
    `floor(-1.0) == -1`).
  - **NEW** `test_process_uses_mcg16807_streams_not_pcg64` — process-level
    inversion test: fails closed if either stream field (or any process
    attribute) is a PCG64-backed `np.random.Generator`.
  - **NEW** `test_process_rng_streams_are_seed_reproducible_and_seed_distinct`
    — same seed ⇒ identical reaction order; different seed ⇒ different
    order (guards against silently ignoring the seed parameter).

## L2.1 active-window audit re-run (seed2000, genuine trace)

Trace: `data/m1_sources/karr_native/per_process_traces_v2_event_s2000/DNADamage_20ticks.mat`
(sha256 `55983422c7...`, unchanged — same trace used before/after this fix).
Re-run via `scripts/l21_active_window_audit.py`'s internal
`_summarize_trace_candidate`/`_classify_live_trace_candidate`/
`verify_active_window_manifest_row` (seed2000 isn't in `DIRECT_SPECIAL_TRACES`,
so the CLI can't auto-discover it — same pattern used in prior sessions).

| | Before this fix (PCG64, buggy stochastic_round) | After this fix (mcg16807) |
|---|---|---|
| Classification | CODE_GAP | CODE_GAP (unchanged) |
| `first_mismatch_tick` | 2 | **4** |
| `first_mismatch_observable` | `intrastrandCrossLinks.delta_nnz` | `intrastrandCrossLinks.delta_nnz` (unchanged) |
| `first_mismatch_oc_val` / `karr_val` | 1.0 / 0.0 | **0.0 / 1.0** |
| `honest.karr_active_ticks` | 1/20 (first at tick 4) | 1/20 (first at tick 4, unchanged) |
| `honest.oc_active_ticks` | 20/20 | 20/20 (unchanged) |
| `honest.oc_active_on_karr_active_ticks` | 1 | 1 (unchanged) |

**Interpretation:** the first bit-identity divergence now lands *exactly* on
Karr's own first genuinely active tick (tick 4), instead of two ticks
*before* Karr's real activity even began. Previously OC was diverging from
a still-quiescent Karr baseline (spurious early over-firing, `oc=1.0` vs
`karr=0.0`); now OC agrees with Karr's zero baseline through ticks 0-3 and
diverges only on the literal stochastic outcome of the one tick that is
genuinely active (`oc=0.0` vs `karr=1.0`, i.e. under- not over-firing).
This is the precise, root-caused new first-divergence point explicitly
accepted as an outcome for this task — not full bit-identity, because the
remaining divergence is attributable to the disclosed, architecturally
unreachable shared-Chromosome-stream limitation, not to PCG64/np.random
usage (grep-confirmed removed).

`verify_active_window_manifest_row("DNADamage")` →
`verification_status: VERIFIED_CODE_GAP`, `fresh_classification: CODE_GAP`
matches `recorded_classification`. Manifest row updated in place
(`bit_identity`, `honest_replay`, `code_gap_anchor` fields + a new
`note_rng_fix_2026_09_03` addendum; prior `note_postmerge_2026_09_03`
preserved, not overwritten).

**Strict L2.1 rubric suite** (`tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py`):
**14/14 passed** (878.73s) — no regression to DNARepair/Replication (the
other two `CHROMOSOME_ACTIVITY_TOKENS` rows) or any other process.
`EXPECTED_ACTIVE_WINDOW_VERDICTS["DNADamage"]` unchanged (`CODE_GAP`), no
edit needed since classification didn't change.

## L2.2 event verifier re-run (55-trace accepted corpus)

Corpus: `genuine_signedzero_canary_v4` (5 seeds) + `genuine_signedzero_full_v2`
(50 seeds) under
`E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\...\dnadamage_stimulus_cohort\uvb_mechanism\`
— read via `scripts/l22_evidence/dna_damage_event_verifier.py`'s supported
`--canary-root`/`--full-root` args (no local copy needed; no root-path
change committed to the verifier module itself).

| | Before this fix | After this fix |
|---|---|---|
| `n_events_karr` | 99 | 99 (unchanged, fixed corpus) |
| `n_events_oc` | 92 | **90** |
| `joint_verdict` | PASS | PASS (unchanged) |
| `channels.chromosome.verdict` | PASS | PASS (unchanged) |
| `result.verdict` | PASS | PASS (unchanged) |

Current-tree evidence genuinely PASSES (no threshold changes, no stale
evidence reuse — corpus hash-verified via the verifier's own
`REQUIRED_OVERLAY_HASH_FIELDS` check, all 50 traces carry overlay-hash
provenance). Per instruction, regenerated the tracked canonical bundle:
`docs/phase_f/l2_2_design_a/evidence_bundle/DNADamage/latest_event/*`.

## Complete-bundle evidence_index regeneration

`python -m scripts.l22_evidence.generator generate` →
`22 rows, aggregate=NON_GREEN — FAIL: 2, MISSING_EVIDENCE: 2, PASS: 18`
(**18/2/2, preserved**). `generator audit` → `integrity: OK`, mechanically
re-derived counts match. `DNADamage` row: `mechanical_verdict: PASS`,
`reasons: []`. `ProteinProcessingI` (PPII) row: `mechanical_verdict: PASS`
(preserved, untouched by this change — verified explicitly since PPII PASS
has been a recurring regression risk in prior review rounds on this
process family).

## Test / lint summary

- Focused (`test_karr_dna_damage.py` + `test_karr_dna_damage_rng.py`):
  **37/37 passed** (35 original + 2 new process-level inversion tests).
- `test_karr_dna_damage_l2_replay.py`: **2 passed, 5 skipped** (unchanged;
  skips are the expected 5 Thattai paper-cache-only seeds per project
  convention).
- Strict L2.1 rubric (`test_probe_l2_1_strict_rubric_active_windows.py`):
  **14/14 passed** (878.73s).
- Ruff: clean on all 4 changed/new production+test files.
- Full combined suite (`python -m pytest -q`): launched in background at
  the start of this session; confirmed genuinely running (not hung) via
  `ps aux` (97-98% CPU, 100+ minutes of real CPU time consumed) but had
  **not finished within this session's wall-clock window** at the time
  this status was written, due to heavy shared-machine contention from
  several other concurrent worktree sessions' own MATLAB/pytest runs
  visible in `ps aux` on the same box. All *targeted* suites that
  specifically exercise this change (focused RNG+process tests, strict
  L2.1 rubric, L2 replay pytest, L2.2 event verifier, Ruff) are green as
  reported above. The untargeted full-suite run should be re-checked
  opportunistically in a follow-up turn/session before merging to main;
  it is not required to unblock this branch's own deliverable, since
  every module it touches has dedicated passing coverage.

## Commits (this branch, not pushed/merged)

See `git log agent/l21-dnadamage-active-fix-20260903 --oneline` for the
final list; committed in green, logically-scoped chunks with the
`Co-authored-by: Copilot` trailer, each preceded by a
`scripts.log_llm_interaction` provenance entry.

## Remaining blockers / known gaps (disclosed, not silently deferred)

1. **Shared-Chromosome-stream ceiling** (architectural, not a code bug):
   Karr's real site-sampling draws advance a single stream shared by ~28
   processes across the whole simulation; an isolated single-process
   replay cannot reproduce that exact draw sequence. `_site_sampling_rng`
   is a structurally-faithful stand-in, not a bit-identical replay.
2. **`randsample_without_replacement` draw-count approximation**: real
   MATLAB's `randsample(stream,n,k,false)` consumes a variable,
   shape-dependent number of draws not fully reverse-engineered for all
   `(n,k)`; approximated as `randperm(n)[:k]`, consistent with the
   existing (untouched) shared `matlab_rng.py` convention.
3. **L2.1 CODE_GAP classification remains CODE_GAP** for seed2000 — not
   promoted to `EXISTING_WINDOW_PASS`/GENUINE, because bit identity does
   not hold at tick 4 (blocker #1). This is the honestly-reported outcome,
   not a regression: the fix closed the *reachable* part of the RNG gap
   (DNADamage's own `randperm` + the `stochastic_round` draw-skip bug) and
   produced a precisely root-caused, later, single-tick divergence instead
   of an early, broad one.
4. Catalog `notes`/`blocked_on` prose in `PROCESS_CATALOG.yaml` (quoted
   above) is stale relative to the accepted genuine corpus/rate-law work;
   left untouched, out of scope for this RNG-fidelity turn.

---

## Session 2 (2026-09-04): shared-Chromosome-stream input-state ledger closure

**Scope of this session**: close blockers #1 and #2 above (the
shared-Chromosome-stream "architectural ceiling" and the
`randsample_without_replacement` draw-count approximation), per an
explicit follow-up task directing "no proxy RNG, no hardcoded seed/tick
offsets, and no architectural waiver." **Supersedes (does not delete)**
blockers #1/#2 above — see the corrected status at the end of this
section.

### Primary sources read this session (local, no web)

- `+edu/+stanford/+covert/+cell/+sim/Process.m` (`constructRandStream`)
  and `+edu/+stanford/+covert/+cell/+sim/CellState.m` (same pattern) —
  confirmed Chromosome (a `CellState`) gets its own
  `RandStream('mcg16807')`, seeded from the identical `simulation.seed`,
  same construction as every process.
- `+edu/+stanford/+covert/+util/RandStream.m` (the Karr WRAPPER class,
  lines 1-40, 152-202, 236-252, 273-282) — confirmed this wrapper's
  `randStream` property is a GENUINE MATLAB BUILTIN `RandStream` object
  (`this.randStream = RandStream(type, varargin{:})`, shadowing the
  builtin name), not a from-scratch reimplementation; `rand`/`randi`/
  `randperm`/`randsample`/`stochasticRound`/`randomlySelectNRows` all
  delegate directly to the builtin. `get.state`/`set.state` (lines
  273-278) delegate directly to `this.randStream.State`.
- `+edu/+stanford/+covert/+cell/+sim/+state/Chromosome.m`
  (`sampleAccessibleSites` ~539-620, `setSiteDamaged` ~2490-2527,
  `getDamagedSites`/`calcDamagedSites_nonRedundant` ~1707-1755,
  3626-3653) — read in full this session (not just cited) to confirm
  the exact iterative multi-round candidate-search algorithm, the
  `damagedSites_nonRedundant` flag combination (`includeBases=true,
  includeBonds=true, includeBase5Prime=includeBond5Prime=
  includeBase3Prime=includeBond3Prime=false, includeM6AD=true`, which
  reduces to a plain sum of the SAME 7 sparse fields OC already tracks,
  no 5'/3'-shifted variants), and `setSiteDamaged`'s non-string-branch
  early returns (`if nnz(...)==0: return`, `if isempty(positionsStrands):
  return` — both WITHOUT a draw, confirmed literal-matching OC's own
  early-return structure).
- `E:\MATLAB\toolbox\stats\stats\randsample.m` (the REAL Statistics and
  Machine Learning Toolbox source, MathWorks copyright 1993-2025, R2026a)
  — read in full; this is what the disclosed `randsample_without_replacement`
  approximation was standing in for. Confirms the exact two-branch
  algorithm (`4*k>n` → `randperm` prefix; else → rejection loop over
  builtin `randi` + final `randperm` reorder).
- Real local MATLAB (`E:\MATLAB\bin\matlab.exe`, via
  `scripts/tools/run_matlab_slot.ps1 -Slots 4`) — used extensively this
  session for live probes (see below); no web used anywhere.

### 1. Chromosome-shared-stream `.State` capture and restoration (proven, not decoded)

Empirically probed (`scripts/matlab/probe_l21_chromosome_randstream_state.m`,
tracked) whether MATLAB's builtin `RandStream('mcg16807').State` — the
SAME scalar `edu.stanford.covert.util.RandStream.state` delegates to —
can serve as genuine, restorable input state for the shared Chromosome
stream:

- **Reconstruction works**: setting a FRESH `RandStream`'s `.State` to a
  captured value and continuing to draw reproduces the ORIGINAL stream's
  continuation bit-for-bit (`reconstruction_ok=true` for all 4 probed
  seeds — this is a native MATLAB feature, not something this project
  had to reverse-engineer).
- **The .State encoding itself is NOT decodable via any closed-form
  formula this project derived**: `.State` read immediately after
  `reset(seed)` reports the raw seed (not this project's own internal
  `seed*65536 mod M` register); mid-sequence `.State` reads do not follow
  that same `*65536 mod M` transform either (multiple candidate formulas
  tested and refuted with real numeric counter-examples — see
  `artifacts/l21_dnadamage_chromosome_rng/analyze_probe*.py`, not
  committed). This is a genuine, disclosed limit: this project does not
  know MATLAB's internal encoding for `.State` at an arbitrary point, and
  is not asserting one.
- **MATLAB's builtin `randi(stream, n)` for this generator type is
  exactly `floor(n*rand())+1`**, one raw draw per requested integer, with
  NO rejection/bias-correction — verified live (`all_randi_values_match=1`,
  `all_randi_state_matches=1` across seeds {1,2000,12345,2147483646} ×
  n∈{7,500,100003}). This differs from Mersenne-Twister-backed streams
  (which do use rejection sampling) and was the missing piece needed to
  port `randsample`'s rejection-loop branch exactly (see §3 below).

**Consequence**: since `.State` restoration is proven correct via
MATLAB's own object but not decodable into this project's own
representation, this project does NOT attempt state-formula decoding.
Instead it uses MATLAB itself, offline and non-destructively, to turn a
captured `.State` pair into an exact ordered list of raw draws (§2) — the
"exact consumed-draw ledger" fallback this task's directive explicitly
authorized for this scenario.

### 2. Extractor change + offline draw-ledger reconstruction

- **`scripts/matlab/extract_per_process_traces_v2.m`** (modified):
  added `merge_chromosome_rand_stream_state` (captures
  `mod.chromosome.randStream.state` — a plain scalar read, no draw
  consumed — at DNADamage's existing `before_tick`/`after_tick` tap
  points, guarded/additive, never fails a real tick) and a
  dynamic-field copy loop in the fixed-window branch (which previously
  hard-coded `snapshot_props` and would have silently dropped any field
  beyond `substrates/enzymes/boundEnzymes/chromosome` — fixed to also
  copy any additional fields the tap merges in, lazily allocating their
  cell arrays). This is INPUT STATE capture (which exact position in
  Karr's real shared stream this tick's DNADamage draws come from), not
  answer leakage — analogous to how `states_before` already captures
  substrate/enzyme/chromosome counts as input.
- Re-extracted the canonical seed2000 20-tick trace
  (`data/m1_sources/karr_native/per_process_traces_v2_event_s2000/
  DNADamage_20ticks.mat`, gitignored/local, regenerated via
  `scripts/l2_event/dna_damage_stimulus_cohort.fixed_window_spec_for_seed
  ("uvb_mechanism", 2000)` + `launcher.build_matlab_command` to get the
  exact original extraction args) with the new field. Verified BIT-FOR-
  BIT identical to the prior canonical file on every pre-existing field
  (`substrates`, `enzymes`, `boundEnzymes`, and the full nested
  `chromosome` sparse-triple struct — zero mismatches, both a coarse and
  a deep per-leaf-dataset diff) before promoting it in place. sha256
  changed only because of the additive field
  (`55983422c7547b1e...` → `7be78871919f0e6d480f73e1c5de6cb541540e0...`).
- **`scripts/matlab/reconstruct_chromosome_draw_ledger.m`** (new,
  tracked): offline, non-destructive reconstruction. For each tick,
  clones a SCRATCH `RandStream('mcg16807')` (never the live simulation's
  real stream), sets `.State = state_before(t)`, single-steps it via
  plain `rand()` recording each value, until `.State == state_after(t)`
  exactly (fail-closed with a named tick and a `max_draws_per_tick`
  ceiling — default 200000 — if never reached). Correct regardless of
  `.State`'s internal encoding because every higher-level Karr primitive
  (§3) was independently verified to bottom out in plain `rand()` calls
  with no other state-advancing mechanism. Source-hash-bound: records
  `trace_sha256`, `dnadamage_source_sha256` (already in the trace
  metadata), `chromosome_source_sha256`, `randstream_util_source_sha256`
  (both freshly hashed from the resolved WholeCell source tree, SHA-256
  over CR-stripped bytes, matching `karr_bootstrap.m`'s own convention).
  Written as a tracked-pattern companion sidecar (also gitignored, same
  as the `.mat` tree it sits beside, following the project's existing
  convention that this whole trace family is a regenerate-on-demand
  local cache, not committed):
  `data/m1_sources/karr_native/per_process_traces_v2_event_s2000/
  DNADamage_20ticks.chromosome_rand_stream_ledger.json` — per-tick draw
  counts for seed2000: `[22,22,22,22,45,22,22,20,22,22,22,22,22,22,22,22,
  22,22,22,22]` (tick4, 0-indexed — Karr's own first genuinely active
  tick — needs 45, the most of any tick).

**Methodological trap hit and fixed mid-session** (recorded here per this
project's "no silent shortcuts" discipline): an early probe run
(`addpath('scripts/matlab')` then directly calling `randsample`) was
silently shadowed by this repo's OWN `scripts/matlab/randsample.m`
fallback shim (a structurally different weighted-cdf-based algorithm,
meant for environments without the Statistics Toolbox) instead of the
real `toolbox/stats/stats/randsample.m` — the FIRST round of "ground
truth" values captured this way were actually the SHIM's output, not
MATLAB's real toolbox algorithm, and were discovered wrong only because
`randperm(n)[:k]` (already independently verified correct) disagreed with
a `randsample(...,k==n,...)` call that should have been identical to it.
Root cause: MATLAB's `addpath('scripts/matlab')` combined with
`karr_bootstrap.m`'s own internal re-promotion of the toolbox path is
normally sufficient, but a SEPARATE trap fired first — MATLAB's `run()`
function changes the current directory to the invoked script's OWN
folder before executing it, and when a scratch probe script lived under
`scripts/matlab/` itself, `karr_bootstrap.m`'s own documented defense
("MATLAB resolves the current folder ahead of the path, so a caller
running from scripts/matlab could otherwise re-shadow the provider")
fired as designed, correctly detecting a real shadow risk — the actual
fix was to move scratch invocation scripts to a non-`scripts/matlab`
directory (`artifacts/matlab_scratch/`), never to disable or work around
`karr_bootstrap.m`'s check. All reported randsample ground truth in this
STATUS and in the tracked tests was re-captured after this fix, cross-
checked against `which randsample` resolving to
`E:\MATLAB\toolbox\stats\stats\randsample.m`.

### 3. Exact `randsample_without_replacement` (blocker #2 closed)

Replaced the disclosed approximation (`randperm(n)[:k]` for every
`(n,k)`) in `opencell/vivarium/karr_dna_damage_rng.py` with the exact
algorithm read from the real `randsample.m` (§ primary sources): `4*k>n`
→ `randperm(n)[:k]` (this branch was ALREADY exact); `4*k<=n` → a
rejection-sampling loop over a new `_builtin_randi` (MATLAB's real
built-in `randi`, `floor(n*rand())+1`, distinct from the existing public
`randi()` which stays `ceil(n*rand())` for Chromosome.m's own direct
position/strand draws — two different formulas for two different call
sites, both now present) followed by one final `randperm(k)` reorder.
Verified live against 6 real-MATLAB cases (`scripts/matlab/
probe_l21_randsample_exact.m`, tracked) spanning both branches, a k=1
edge case, a k==n edge case, and a realistic genome-scale n=50000
rejection case — all bit-for-bit exact
(`tests/vivarium/test_karr_dna_damage_rng.py`, 32/32 passing, up from
19/19; new tests include an inversion test proving the prior
`randperm(n)[:k]` approximation demonstrably diverges from the real
answer for the n=50000/k=12 case).

### 4. `KarrLedgerReplayStream` + harness wiring (fail-closed, per task item 3)

Added `KarrLedgerReplayStream(KarrMcg16807Stream)` to
`karr_dna_damage_rng.py` — a test/harness-only replay stream (no file
I/O of its own; constructed from a plain list of floats) that overrides
ONLY `rand()` to pop pre-recorded values in order; every higher-level
formula (`randi`, `randperm`, `randsample_without_replacement`,
`stochastic_round`) is inherited unchanged, so replay correctness reduces
entirely to "does `rand()` return the recorded values in the recorded
order." Fail-closed by construction: `rand()` past the end of the ledger
raises immediately (OC consumed MORE draws than recorded — wrong branch
or an extra call); `assert_fully_consumed()` (called once per tick after
`next_update` returns) raises if any recorded draws are left unconsumed
(OC consumed FEWER — a missing call or wrong draw-count formula). 5 new
tests including an explicit inversion test for the wrong-draw-count case.

Wired into `tests/vivarium/test_karr_dna_damage_l2_replay.py`:
`_load_chromosome_rand_stream_ledger` loads the companion sidecar (if
present), validates its `trace_sha256`/`chromosome_source_sha256`/
`randstream_util_source_sha256` hash-bindings against the CURRENT trace
file and CURRENT on-disk MATLAB source (fails closed/loud on any
mismatch — a stale ledger is never silently reused), and `_run_replay`
injects a fresh `KarrLedgerReplayStream` as `process._site_sampling_rng`
before each tick's `next_update` (the freshly-seeded stand-in stream is
correctly NOT carried tick-over-tick for this sub-stream, since Karr's
real shared-stream position between DNADamage's own ticks is determined
by ~27 OTHER processes' draws in between — `_reaction_order_rng`,
DNADamage's own genuinely-isolated stream, is untouched and continues to
advance tick-over-tick as before), then asserts full consumption after
the tick. Seeds 0-4 (no companion ledger on disk) are unaffected,
unchanged behavior.

### Result: ticks 0-3 close bit-identically; tick 4 fails closed with a precise, narrow, further-debuggable gap

A new dedicated test,
`test_karr_dna_damage_l2_event_replay_seed2000_chromosome_ledger`
(`xfail(strict=True)`, skips gracefully if the gitignored trace/ledger
are absent from a given checkout), replays seed2000 with the ledger
injected every tick. **Ticks 0-3 (0-indexed) fully and exactly consume
their recorded ledgers** — genuine positional/count bit-identity for the
shared-stream site-sampling draws, not merely "OC agrees Karr is
quiescent." **Tick 4 (Karr's own first genuinely active tick) fails
closed** via `assert_fully_consumed()`: OC consumes 44 of the 45 recorded
raw draws — a precisely isolated single-draw shortfall, not a vague
divergence. Debug instrumentation (not committed) traced all 32 of
tick4's reactions:

- All 32 correctly reach `chromosome`-sampling (none incorrectly gated by
  `max_reactions<=0`/`selectionProbability<=0` — both computed with the
  same structure as `DNADamage.m::evolveState`'s own formulas).
- 22 have string `vulnerableMotif`s; each correctly draws exactly one
  unconditional `stochasticRound` (Chromosome.m's own `sampleAccessibleSites`
  never skips this draw when `prob` is non-empty).
- 10 are non-string; each correctly finds ZERO real candidates —
  independently cross-checked against the trace's real
  `states_before[4]/chromosome` data (`damagedBases` has 760 nonzero
  entries, all valued 481 — a value NO DNADamage reaction's
  fixture-parsed `vulnerableMotif` equals across all 32 reactions,
  confirmed by dumping the full `DNADamage_flat.mat` fixture — so the
  zero-candidate result is itself correct, not a bug; an earlier
  hypothesis in this investigation that one of these 10 reactions should
  have matched value 481 was checked and is WRONG, corrected here rather
  than left stale).
- Exactly one reaction's site search finds `n_sites=1` and its single
  `sampleAccessibleSites` round draws 11 position + 11 strand raw values
  (`n_more = max(2*1, 1+10) = 11`, Chromosome.m's own formula, verified
  bit-identical to the recorded ledger in isolation).
- Total: 22 `stochasticRound` + 22 position/strand draws = 44 — one
  short of the ledger's 45. **The exact origin of the one remaining real
  draw was not isolated within this session's time budget** (candidates:
  a second `sampleAccessibleSites` iteration for that same reaction if
  its first round found zero valid sites before a later round succeeded;
  a different reaction being selected for the successful site search;
  or a still-unaudited call site). This is disclosed as an open,
  narrowly-scoped item for a follow-up session, not silently guessed at.

### Corrected status of blockers #1/#2 (superseding, not deleting, the entries above)

1. **Shared-Chromosome-stream ceiling — NO LONGER an architectural
   ceiling.** The mechanism is proven and implemented (state capture +
   offline draw-ledger reconstruction + fail-closed replay); ticks 0-3
   are genuinely bit-identical for the shared stream's site-sampling
   draws; tick 4 has a concrete, isolated, single-draw gap tracked above.
   `_site_sampling_rng` remains a freshly-seeded stand-in ONLY for traces
   without a companion ledger (seeds 0-4, and the accepted 55-trace L2.2
   corpus, which was not re-extracted with ledger capture this session —
   out of scope/time; see below).
2. **`randsample_without_replacement` draw-count approximation — CLOSED.**
   Replaced with the exact real-MATLAB algorithm, verified live across
   both branches including a rejection-loop-forcing case.
3. **L2.1 classification remains CODE_GAP** for seed2000 (unchanged) —
   bit identity does not yet hold at tick 4, so promotion to
   `EXISTING_WINDOW_PASS`/GENUINE does not apply. Manifest row corrected
   in place (`source.sha256`/`path` updated to the re-extracted trace and
   this worktree; `note_chromosome_ledger_fix_2026_09_04` added,
   preserving all prior notes); `verify_active_window_manifest_row` →
   `verification_status: VERIFIED_CODE_GAP`, `fresh_classification:
   CODE_GAP` matches `recorded_classification`.

### L2.2 event verifier + full evidence_index re-run (55-trace corpus, unchanged corpus)

The exact-`randsample` fix (§3) applies to ALL `KarrDNADamageProcess`
instances, including the 55-trace L2.2 corpus (which does NOT have
chromosome-stream ledgers — those traces were not re-extracted this
session, out of time budget). Re-ran the verifier against the accepted
corpus (`E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\
genuine_signedzero_canary_v4` + `..._full_v2`, unchanged, hash-verified):

| | Before this session | After this session |
|---|---|---|
| `n_events_karr` | 99 | 99 (unchanged corpus) |
| `n_events_oc` | 90 | **90 (unchanged)** |
| `joint_verdict` | PASS | **PASS (unchanged)** |

The exact-`randsample` fix did not move the aggregate 55-trace verdict
(the corpus's rejection-loop cases, if any, evidently did not have their
final selection order affected in a way that changed the event count).
Regenerated the tracked canonical bundle
(`docs/phase_f/l2_2_design_a/evidence_bundle/DNADamage/latest_event/*`)
and the complete `evidence_index.json`
(`python -m scripts.l22_evidence.generator generate` →
`22 rows, aggregate=NON_GREEN — FAIL: 2, MISSING_EVIDENCE: 2, PASS: 18`,
**18/2/2, preserved**; `generator audit` → `integrity: OK`). Diff of
`evidence_index.json` confirmed only DNADamage's own hash/timestamp/
git-sha provenance fields changed; every other row (including
`ProteinProcessingI`/PPII) is byte-identical.

### Test / lint summary (this session)

- `test_karr_dna_damage_rng.py`: **32/32 passed** (up from 19; +13 new:
  6 exact-randsample-vs-real-MATLAB parametrized cases, 1 branch-
  selection sanity check, 4 `KarrLedgerReplayStream` tests, 1 wrong-
  draw-count inversion test, 1 randperm-approximation-diverges inversion
  test).
- `test_karr_dna_damage.py`: **18/18 passed** (unchanged).
- `test_karr_dna_damage_l2_replay.py`: **1 passed, 5 skipped, 1 xfailed**
  (the new dedicated seed2000-ledger test; `xfail(strict=True)` with the
  full tick4 root-cause account above — will flip to XPASS and force
  this marker's removal if/when the remaining single-draw gap is closed).
- Combined (`test_karr_dna_damage.py` + `test_karr_dna_damage_rng.py` +
  `test_karr_dna_damage_l2_replay.py`): **51 passed, 5 skipped, 1
  xfailed**.
- Strict L2.1 rubric (`test_probe_l2_1_strict_rubric_active_windows.py`):
  **14/14 passed** (759.27s) — no regression to DNARepair/Replication or
  any other process.
- Ruff: clean on all changed production+test files
  (`opencell/vivarium/karr_dna_damage_rng.py`,
  `tests/vivarium/test_karr_dna_damage_rng.py`,
  `tests/vivarium/test_karr_dna_damage_l2_replay.py`).
- L2.2 event verifier + full `evidence_index` regeneration: PASS,
  18/2/2 preserved (see above).

### Manifest promotion

**NOT promoted to GENUINE.** Per task instruction ("Update manifest to
GENUINE only after fresh replay"), and since bit identity does not yet
hold at tick 4, the DNADamage row in
`docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` remains
`classification: CODE_GAP`, corrected in place with this session's
evidence (see `note_chromosome_ledger_fix_2026_09_04` and the updated
`source.sha256`/`path`).

### Files changed this session (tracked)

- `scripts/matlab/extract_per_process_traces_v2.m` (modified: ledger
  capture + dynamic-field copy fix)
- `scripts/matlab/probe_l21_chromosome_randstream_state.m` (new)
- `scripts/matlab/probe_l21_randsample_exact.m` (new)
- `scripts/matlab/probe_l21_randsample_vs_randperm_direct.m` (new)
- `scripts/matlab/reconstruct_chromosome_draw_ledger.m` (new)
- `opencell/vivarium/karr_dna_damage_rng.py` (modified: exact
  `randsample_without_replacement`, `KarrLedgerReplayStream`)
- `tests/vivarium/test_karr_dna_damage_rng.py` (modified: +13 tests)
- `tests/vivarium/test_karr_dna_damage_l2_replay.py` (modified: ledger
  loading/hash-binding/injection, new dedicated xfail test)
- `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` (modified:
  DNADamage row `source.sha256`/`path` + new note, CODE_GAP preserved)
- `docs/phase_f/l2_2_design_a/evidence_bundle/DNADamage/latest_event/*`
  and `docs/phase_f/l2_2_design_a/evidence_index.json` (regenerated,
  PASS preserved, 18/2/2 preserved)
- This file.

### Not changed / explicitly out of scope this session

- The accepted 55-trace L2.2 corpus was NOT re-extracted with
  chromosome-stream ledger capture (would require re-running the full
  MATLAB extraction for 55 seeds × 20 ticks each with the new field —
  a substantially larger undertaking than this session's remaining
  budget). The L2.2 verdict above reflects the exact-`randsample` fix
  only, on the UNCHANGED corpus.
- Tick 4's single remaining draw was not isolated to a specific line of
  code. This is the primary recommended next step for a follow-up
  session: instrument Chromosome.m's real `sampleAccessibleSites` (or
  extend the MATLAB-side reconstruction to log iteration boundaries) to
  determine definitively whether Karr's real run needed a second
  iteration for the same reaction, or a different reaction's search
  succeeded instead.
- `PROCESS_CATALOG.yaml` catalog `notes`/`blocked_on` prose (already
  flagged stale in the prior session) — untouched, still out of scope.
- `data/opencell_ensembles/translation/comparison_report.json` — an
  unrelated pre-existing modification in this worktree, explicitly
  preserved untouched (not staged, not reverted) per task instruction.

---

## Session 3 (2026-09-05): tick-4 single-draw closure — full bit identity

**Scope**: close the ONE remaining draw disclosed at the end of Session 2
(seed2000 tick4, OC 44/45 recorded draws) via PER-REACTION-GRANULARITY
instrumentation of the real MATLAB path — never inferring the cause from
the aggregate 44/45 alone — then re-run the full validation matrix and
remove the `xfail` only once genuinely green.

### 1. Per-reaction MATLAB instrumentation (live, hash-bound, no source patch)

Built `scripts/matlab/instrument_dnadamage_tick4_per_reaction.m` (tracked).
Does **not** modify DNADamage.m/Chromosome.m/RandStream.m in any way (no
overlay, no patched copy) — it calls the REAL, unmodified class
methods/properties externally, the same externally-read/write pattern
`extract_per_process_traces_v2.m`'s `evolve_state_with_tap` already uses.
Mechanics:

- Replays ticks 1-4 (1-based) using the extractor's own exact
  scheduler/allocation loop, copied verbatim (not refactored/shared, to
  avoid any risk that a shared-code change could affect the already-
  accepted extractor), to reach the identical real simulation state our
  seed2000 trace was captured from.
- **Self-consistency check, passed**: the chromosome-stream state
  entering tick 5 (`1550145208.0`) exactly matches the already-captured
  ledger's tick-5 `state_before` to the last decimal — proving this
  replay-to-tick-5 procedure reproduces the identical real simulation
  state, not an approximation.
- For tick 5, inlines `evolveState()`'s own literal per-reaction loop
  (DNADamage.m ~535-573, quoted verbatim in the script's comments) instead
  of calling `mod.evolveState()` as a black box, logging per reaction: 0/1-
  based index, WID, `vulnerableMotif`/`vulnerableMotifType`, is-string-
  motif, `maxReactions`, `selectionProbability`, `chromosome.randStream
  .state` immediately before/after the real (unmodified)
  `this.chromosome.setSiteDamaged()` call, the exact draw count for that
  ONE reaction (via the same proven non-destructive clone-and-step
  reconstruction already used for the ledger), the actual sites damaged,
  and a running cumulative draw count.
- Records exact source/provider hashes for provenance: `dnadamage_source
  _sha256` (via `karr_bootstrap()`'s own returned overlay identity),
  freshly-computed `chromosome_source_sha256`/`randstream_util_source
  _sha256`, and the full `mnrnd_provider_identity` (toolbox provider
  hashes for `binornd`/`mnrnd`/`poissrnd`/`random`/`randsample`).

**Methodological trap hit and fixed while building this** (recorded per
this project's no-silent-shortcuts discipline): an early draft literally
reimplemented Karr's per-reaction formula from the (unpatched) source
comment text (`maxReactions = floor(min(this.substrates ./ max(0,
-this.reactionSmallMoleculeStoichiometryMatrix(:, j))))`), which computed
`-Inf` for every one of tick4's 32 reactions (`this.substrates(k)/(-0.0)
== -Inf` in IEEE754, for any non-reactant substrate index `k` where the
stoichiometry entry is exact-zero — `-(+0.0) == -0.0`, and `max(0,-0.0)`
does not clamp back to `+0.0`). This is EXACTLY the bug
`karr_bootstrap.m::ensure_dnadamage_signed_zero_overlay` already patches
in the REAL DNADamage.m source it loads (`denom = abs(max(0,
-stoich))`), which the inline reimplementation had silently bypassed by
copying the ORIGINAL (unpatched) formula text instead of the actually-
resolved, overlay-patched one. Fixed by applying the identical `abs(...)`
normalization in the inline reimplementation; confirmed via
`total_draws` jumping from 0 (every reaction spuriously gated at
`maxReactions=-Inf<=0`) to 45 (matching the ledger exactly) after the
fix. This independently re-confirms OC's own `_max_reactions_for_reaction`
(which already used the `abs(...)`-normalized formula, matching the
overlay) was correct all along.

### 2. OC-side per-reaction instrumentation + direct side-by-side diff

Built `artifacts/l21_dnadamage_chromosome_rng/build_oc_tick4_ledger.py`
(not committed, scratch — logic folded into the permanent regression test
in §3): traces every `_sample_reaction_coords` call via
`KarrLedgerReplayStream`'s own `_index` draw counter (not a separate
re-implementation), producing a matching per-reaction JSON ledger.

Diffed the two ledgers reaction-by-reaction (never inferring from the
aggregate 44/45 alone, per instruction): the first 9 reactions matched
exactly (same index, same draw count, same cumulative count) before the
**first and only divergence**, precisely isolated at iteration 10
(reaction index 26, `DNADamage_THYTHY_cyclobutane_THYTHY_UVB_radiation`,
a 2-character string motif `"TT"`): both sides find `n_sites_actual=1`,
but real MATLAB draws 24 raw values for this ONE reaction while OC draws
only 23.

### 3. Root cause found (not triangulated) and fixed

`Chromosome.m::sampleAccessibleSites`'s real per-round break condition:

```matlab
if size(positionsStrands, 1) >= nSites
    positionsStrands = this.randStream.randomlySelectNRows(positionsStrands, nSites);
    break;
end
```

calls `randomlySelectNRows`/`randsample` **unconditionally** whenever
accumulated candidates reach (`>=`) the target — **including the exact-
match case** (found precisely `nSites` candidates, no actual selection
ambiguity). This still consumes real draws: `randsample(stream, n, n,
false)` with `n==k` hits `randsample.m`'s `4*k>n` branch (true for any
`k>=1` when `k==n`) and performs a full `randperm(n)` — `n` real draws —
even though the output is merely a reordering of the same candidates.

`opencell/vivarium/karr_dna_damage.py::_sample_literal_motif_sites` used
`if len(candidates) > n_sites:` (**strictly greater**) before calling
`randsample_without_replacement`, silently **skipping this mandatory
draw** for the exact-match case (`len(candidates) == n_sites`) —
desynchronizing the shared site-sampling stream from Karr's real one for
every subsequent draw in the same tick. **Fixed to `>=`.**

Two dedicated regression tests added to `tests/vivarium/
test_karr_dna_damage.py`:

- `test_sample_literal_motif_sites_draws_final_select_when_candidates_exactly_equal_n_sites`
  — forces the exact-match case deterministically (an all-`'A'`
  synthetic sequence + a `_window_accessible` monkeypatch that always
  accepts, so every drawn `(position, strand)` pair is accepted; a
  hand-crafted `KarrLedgerReplayStream` maps all 11 position + 11 strand
  draws of the first round to the same `(0, 0)` coordinate via
  `ceil(dna_length * 1e-12) == 1`, so exactly 1 unique candidate
  accumulates, exactly equal to `n_sites=1`) and asserts
  `assert_fully_consumed()` succeeds only when the mandatory 23rd
  (final-select) draw was actually consumed.
- `test_inversion_skip_final_select_on_exact_match_desyncs_stream` — an
  explicit inversion proving the prior `>` guard leaves the stream at a
  **different** (under-consumed) position than the fixed `>=` version,
  so a future regression back to `>` is caught by the first test's
  `assert_fully_consumed()` raising, not silently passing.

### 4. Full closure verified: rebuild ledgers, full 20-tick replay, remove xfail

Rebuilt the OC-side per-reaction ledger after the fix and re-diffed
against the real MATLAB ledger:

| | Before fix | After fix |
|---|---|---|
| OC total draws (tick4) | 44 | **45** |
| Reaction-by-reaction diff | 1 divergence (iteration 10) | **0 divergences across all 32 reactions** |
| Per-reaction draw counts | mismatch at reaction 26 (23 vs 24) | **exact match at every reaction, every cumulative count** |

Reran `test_karr_dna_damage_l2_event_replay_seed2000_chromosome_ledger`
(the dedicated ledger-driven test, previously `xfail(strict=True)`):
**genuine, unconditional PASS** — confirmed via first re-running it
*with the xfail marker still in place* to observe `XPASS(strict)` (proof
the underlying behavior flipped, not just a test-file edit), then
**removed the `xfail` marker** and re-ran to confirm a clean, marker-free
PASS. This is a full 20-tick replay (not just ticks 0-4): every tick's
recorded ledger is injected and asserted fully consumed, and every
tick's substrate/enzyme/chromosome-sparse-field values are compared
against Karr's real recorded outcome via the existing `_run_replay`
machinery (integer-exact counts, WID-length guards, pass-through
provenance — the full Rule 1-8 harness from `FIX_TEMPLATE_L2_REPLAY.md`,
unchanged). **This is genuine, non-approximated bit identity for the
complete seed2000 20-tick active window — the RNG-fidelity gap this
multi-session task set out to close is closed for this trace.**

### 5. Re-ran the full validation matrix

- `test_karr_dna_damage.py` + `test_karr_dna_damage_rng.py` +
  `test_karr_dna_damage_l2_replay.py` combined: **54 passed, 5 skipped, 0
  xfailed** (up from 51 passed/5 skipped/1 xfailed at the end of Session
  2 — the xfail converted to a genuine pass, plus 2 new regression
  tests).
- Strict L2.1 rubric (`test_probe_l2_1_strict_rubric_active_windows.py`):
  **14/14 passed** (650s) — no regression to DNARepair/Replication or any
  other process.
- Ruff: clean on all changed files (`opencell/vivarium/karr_dna_damage.py`,
  `tests/vivarium/test_karr_dna_damage.py`,
  `tests/vivarium/test_karr_dna_damage_l2_replay.py`).
- **L2.2 event verifier (55-trace corpus, unchanged corpus, re-run
  because the fix applies process-wide, not just to ledgered traces)**:

  | | Before this session's fix | After this session's fix |
  |---|---|---|
  | `n_events_karr` | 99 | 99 (unchanged corpus) |
  | `n_events_oc` | 90 | **84** |
  | `joint_verdict` | PASS | **PASS (unchanged)** |

  `n_events_oc` moved (90→84) as expected — the fix changes which sites
  get selected/consumed across the corpus (a genuine algorithmic
  correction, not a threshold change), and the joint verdict remains
  PASS. Regenerated the tracked canonical bundle and the complete
  `evidence_index.json` (`22 rows, aggregate=NON_GREEN — FAIL: 2,
  MISSING_EVIDENCE: 2, PASS: 18`, **18/2/2 preserved**; `generator audit`
  → `integrity: OK`). Diff confirms only DNADamage's own row changed;
  every other row (including `ProteinProcessingI`/PPII) is byte-identical.

### 6. Manifest: classification honestly stays CODE_GAP (methodology gap, not an algorithm gap)

Re-ran `verify_active_window_manifest_row` (the mechanical, ledger-free
audit tool) after the fix: **identical** `first_mismatch_tick=4`,
`first_mismatch_oc_val=0.0`, `first_mismatch_karr_val=1.0` as before this
session's fix — `verification_status: VERIFIED_CODE_GAP`,
`fresh_classification: CODE_GAP`, unchanged.

This is **expected and correctly diagnosed, not a residual bug**: the
standard `l21_active_window_audit.py` harness constructs a **fresh, non-
ledgered** `KarrDNADamageProcess` (the pre-existing, disclosed "stand-in
stream" architecture) for its own bit-identity check. A freshly-seeded
stream's specific stochastic outcome is uncorrelated with Karr's real
interleaved-shared-stream position **regardless of how correct the
underlying selection algorithm now is** — fixing the exact-match draw-
count bug cannot, by itself, make an uncorrelated fresh stream produce
Karr's exact recorded outcome; only ledger-driven input-state restoration
can (which is exactly what §4's genuinely-passing dedicated test does).

**Decision**: the manifest row's `classification` remains `CODE_GAP` and
is **NOT promoted to GENUINE**. Promoting it would require either (a)
extending the shared, multi-process `l21_active_window_audit.py` harness
itself to support ledger injection — a larger, riskier change touching
infrastructure every other process's L2.1 audit depends on, out of scope
for a single-process RNG-fidelity fix — or (b) documenting an
undisclosed exception to the harness's own verdict for this one process,
which this project's credibility policy does not permit. Neither was
done. The manifest row is corrected in place with a comprehensive new
`note_full_tick4_closure_2026_09_05` addendum (all prior notes
preserved) documenting the genuine closure precisely, its evidence, and
this honest disclosure about why the mechanical classification does not
(and structurally cannot, without harness changes) reflect it.

### 7. Files changed this session (tracked)

- `opencell/vivarium/karr_dna_damage.py` (modified: `_sample_literal_motif_sites`
  `>` → `>=` fix)
- `tests/vivarium/test_karr_dna_damage.py` (modified: 2 new regression
  tests)
- `tests/vivarium/test_karr_dna_damage_l2_replay.py` (modified:
  `xfail(strict=True)` marker removed from the now-genuinely-passing
  dedicated seed2000 ledger test; docstring updated with the closure
  account)
- `scripts/matlab/instrument_dnadamage_tick4_per_reaction.m` (new,
  tracked)
- `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` (modified:
  `note_full_tick4_closure_2026_09_05` + `replay_evidence.nodeid`/
  `nodeid_note_2026_09_05` corrected; `classification` unchanged,
  `CODE_GAP`)
- `docs/phase_f/l2_2_design_a/evidence_bundle/DNADamage/latest_event/*`
  and `docs/phase_f/l2_2_design_a/evidence_index.json` (regenerated,
  PASS preserved, 18/2/2 preserved, `n_events_oc` 90→84)
- This file.

### Not changed / explicitly out of scope this session

- The shared `l21_active_window_audit.py` harness itself was NOT
  extended to support ledger injection (see §6's decision rationale).
- The accepted 55-trace L2.2 corpus was NOT re-extracted with
  chromosome-stream ledger capture (still out of scope/budget; the L2.2
  re-run in §5 reflects the algorithmic fix only, on the unchanged
  corpus).
- `PROCESS_CATALOG.yaml` catalog `notes`/`blocked_on` prose — still
  untouched, still out of scope.
- `data/opencell_ensembles/translation/comparison_report.json` — the
  same unrelated pre-existing modification from Session 1/2, still
  preserved untouched (not staged, not reverted).

---

## Session 4 (2026-09-05): shared audit harness ledger-injection support — CODE_GAP → EXISTING_WINDOW_PASS

**Scope**: close the harness-methodology gap Session 3 explicitly left
open (its `note_full_tick4_closure_2026_09_05` disclosed that the
mechanical `l21_active_window_audit.py` harness could not observe the
genuine, ledger-driven bit identity Session 3 established, because it
constructs a fresh, non-ledgered process). Per instruction, extended the
shared harness itself rather than leaving the manifest CODE_GAP for a
tooling omission.

### 1. Shared helper extraction (no duplication)

Extracted the ledger-loading logic (previously private to
`test_karr_dna_damage_l2_replay.py`) into a new shared module,
**`tests/vivarium/chromosome_rand_stream_ledger.py`**:
`sha256_lf_normalized`, `resolve_wcm_source_path`,
`load_chromosome_rand_stream_ledger` — all parameterized on an explicit
`repo_root: Path` argument (never inferred from the module's own
`__file__`), so the identical loader behaves correctly regardless of
which worktree/script imports it. `test_karr_dna_damage_l2_replay.py`
was refactored to import from this module (its own thin wrapper
functions removed); no behavior change, confirmed via its own test
suite (2 passed, 5 skipped, unchanged).

### 2. Shared audit harness extension

- **`tests/vivarium/l2_2_replay_common_v2.py`**: `_ProcessSpec` gained an
  optional `chromosome_rand_stream_ledger_attr: str | None = None` field
  (documented inline), set to `"_site_sampling_rng"` **only** for
  DNADamage's spec entry — `None` (default, unchanged) for every other
  process, including the other two `CHROMOSOME_ACTIVITY_TOKENS`
  processes (DNARepair, Replication). `_ProcessContext` gained a
  `chromosome_rand_stream_ledger: list[list[float]] | None = None`
  field. `_build_context` now loads the ledger (via the shared module,
  using `Path(handle.filename)` — the h5py file's own resolved path —
  and this file's own `_REPO_ROOT`) whenever the spec declares the attr;
  fails closed (raises, via the shared loader's own hash/shape
  assertions) on any tampered/malformed sidecar, and ALSO fails closed
  if the ledger's tick count doesn't match the trace's own `n_ticks`
  (a check specific to this call site, not in the shared loader, since
  the shared loader has no `n_ticks` context of its own).
- **`scripts/l21_active_window_audit.py`**: `_honest_replay`'s per-tick
  loop now constructs a fresh `KarrLedgerReplayStream` from
  `ctx.chromosome_rand_stream_ledger[tick]` and assigns it to the
  declared attribute immediately before `process.next_update(1.0,
  state)`, whenever both the spec declares the attr AND a ledger was
  loaded; calls `.assert_fully_consumed()` immediately after
  `next_update` returns, propagating any shortfall/overflow as a hard
  failure. No new stream is constructed, and no injection happens at
  all, for any trace lacking a companion ledger sidecar (the pre-
  existing stand-in-stream behavior is completely unchanged for those).

### 3. New audit tests (8, all passing)

`tests/scripts/test_l21_active_window_audit_chromosome_rand_stream_ledger.py`:

1. `test_dnadamage_spec_declares_chromosome_rand_stream_ledger_attr` —
   spec wiring sanity check.
2. `test_dnarepair_and_replication_specs_do_not_declare_a_ledger_attr` —
   confirms the other two `CHROMOSOME_ACTIVITY_TOKENS` processes are
   structurally unaffected.
3. `test_valid_ledger_seed2000_achieves_bit_identity_and_existing_window_pass`
   — the canonical trace achieves `bit_identity.pass_all_compared_ticks
   is True`, `first_mismatch_tick is None`, and
   `_classify_live_trace_candidate` returns `CLASS_EXISTING_WINDOW_PASS`.
4. `test_missing_ledger_sidecar_falls_back_to_prior_stand_in_behavior` —
   a copy of the trace with the ledger sidecar deliberately NOT copied
   alongside it replays without error using the pre-existing stand-in
   stream (the seeds-0-4 baseline case).
5. `test_tampered_ledger_hash_mismatch_fails_closed_not_silent_fallback`
   — a ledger whose `trace_sha256` no longer matches raises at
   `_build_context` time.
6. `test_one_draw_short_ledger_fails_closed_not_silent_fallback` — a
   ledger with an internally-inconsistent (truncated `draws` without
   updating `n_draws`) tick raises at `_build_context` time.
7. `test_one_draw_short_ledger_with_consistent_n_draws_fails_closed_during_replay`
   — a ledger that is internally self-consistent but one draw short of
   what OC's algorithm actually needs raises DURING replay (either via
   `KarrLedgerReplayStream.rand()`'s own mid-call exhaustion check or
   `assert_fully_consumed()`'s post-tick check, depending on exactly
   where in the sequence the shortfall registers — both accepted as
   valid fail-closed responses; the test's regex matches either).
8. `test_overflow_ledger_fails_closed_during_replay` — a ledger padded
   with one extra, unconsumed draw raises via
   `assert_fully_consumed()` detecting the leftover.

Also re-ran the two PRE-EXISTING audit-tool test files
(`test_l21_active_window_audit_chromosome_activity.py`,
`test_l21_active_window_audit_host_custom_surfaces.py`, 10 tests) to
confirm zero regression from the harness extension.

### 4. Main-resolvable paths + main-integrate evidence copy

Rewrote the manifest's `source.path` from an absolute,
`fix-l21-dnadamage-active`-specific path to a **repo-relative** string
(`data/m1_sources/karr_native/per_process_traces_v2_event_s2000/
DNADamage_20ticks.mat`) so `_resolve_manifest_source_path` resolves it
correctly via `_REPO_ROOT` (wherever THAT worktree's own copy of
`scripts/l21_active_window_audit.py` lives) from ANY worktree/checkout,
not just this one. Copied the canonical trace + its
`chromosome_rand_stream_state.chromosome_rand_stream_ledger.json`
sidecar (both gitignored, regenerate/copy-on-demand data, never
committed — the same convention already used for this whole trace
family) into
`E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\
per_process_traces_v2_event_s2000\`, with byte-for-byte sha256
verification both files are identical to this worktree's own copies
(trace: `7be78871919f0e6d480f73e1c5de6cb541540e04f0069ed541dcd076934252f0`;
ledger: `d2d04d7a747f22d196a64deae3139c8659963cbb965ae825ee1d56dca1964588`)
— confirmed the destination directory is correctly gitignored there too
(same `.gitignore` pattern, shared across worktrees on this branch
lineage). No file in `main-integrate` outside this new, isolated,
gitignored data directory was touched.

### 5. Fresh audit re-run: manifest promoted CODE_GAP → EXISTING_WINDOW_PASS

Re-ran `verify_active_window_manifest_row("DNADamage")` after the
harness extension:

| | Before this session | After this session |
|---|---|---|
| `bit_identity.pass_all_compared_ticks` | False (from the non-ledgered harness) | **True** |
| `bit_identity.first_mismatch_tick` | 4 | **None** |
| `fresh_classification` | CODE_GAP | **EXISTING_WINDOW_PASS** |
| `verification_status` | VERIFIED_CODE_GAP | **VERIFIED_EXISTING_WINDOW_PASS** |
| `verified` | true | **true** |

This is **fresh, mechanically-verified evidence** — the manifest's
`classification` field was updated from `CODE_GAP` to
`EXISTING_WINDOW_PASS` on this basis (per instruction: "update manifest
... only after fresh audit"), `existing_trace_suffices` set to `true`
(matching every other `EXISTING_WINDOW_PASS` row's convention), and the
top-level `counts` object updated (`EXISTING_WINDOW_PASS`: 6→7,
`CODE_GAP`: 3→2, verified against a direct grep-count of the manifest's
own `classification` fields). A new `note_harness_ledger_support_
promotion_2026_09_05` addendum documents the full account (all prior
notes, including the now-historical `code_gap_evidence` object computed
BEFORE this session's harness extension, preserved unedited as the
audit trail).

### 6. `EXPECTED_ACTIVE_WINDOW_VERDICTS` updated to match

`tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py`'s
`EXPECTED_ACTIVE_WINDOW_VERDICTS["DNADamage"]` was `active_windows.
CLASS_CODE_GAP`; updated to the string `"GENUINE"` (the same convention
already used for every other `EXISTING_WINDOW_PASS`-classified process
in that dict — `probe_l2_1_strict_rubric.py::audit_one_process` maps
`verification_status == MANIFEST_VERIFY_EXISTING_WINDOW_PASS` to the
`"GENUINE"` verdict string, a naming choice pre-dating this session,
not introduced by it).

### 7. Full validation matrix, all green

- `tests/scripts/test_l21_active_window_audit_chromosome_rand_stream_ledger.py`:
  **8/8 passed** (new).
- `test_l21_active_window_audit_chromosome_activity.py` +
  `test_l21_active_window_audit_host_custom_surfaces.py`: **10/10
  passed** (unchanged, no regression).
- Combined focused suite (`test_karr_dna_damage.py` +
  `test_karr_dna_damage_rng.py` + `test_karr_dna_damage_l2_replay.py` +
  both audit tool test files above): **72 passed, 5 skipped**.
- **Strict L2.1 rubric** (`test_probe_l2_1_strict_rubric_active_windows.py`):
  **14/14 passed** (659s) — including the now-`GENUINE`-verdict
  DNADamage row and unchanged verdicts for every other process (DNARepair/
  Replication/Metabolism/ProteinDecay/RNAModification/RibosomeAssembly
  all still `GENUINE`; TranscriptionalRegulation/Cytokinesis still
  `CODE_GAP`; ChromosomeSegregation/HostInteraction still
  `MISSING_ACTIVE_EXTRACTION`).
- **L1b wiring verification** (`tests/integration/test_l1b_verify_wiring.py`):
  **19/19 passed** (unaffected — this session touched only audit-harness
  scripts, not process wiring/schema).
- **L2.2 event verifier** (unchanged corpus, re-run as a sanity check
  since no `karr_dna_damage.py` production code changed this session):
  `n_events_karr=99`, `n_events_oc=84` (unchanged from Session 3),
  `joint_verdict=PASS`. Regenerated `evidence_index.json`: 22 rows,
  18/2/2 preserved, `generator audit` → `integrity: OK`.
- Ruff: clean on all changed files (`scripts/l21_active_window_audit.py`,
  `tests/vivarium/l2_2_replay_common_v2.py`,
  `tests/vivarium/chromosome_rand_stream_ledger.py`,
  `tests/vivarium/test_karr_dna_damage_l2_replay.py`,
  `tests/scripts/test_l21_active_window_audit_chromosome_rand_stream_ledger.py`,
  `tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py`).

### 8. Files changed this session (tracked)

- `tests/vivarium/chromosome_rand_stream_ledger.py` (new: shared ledger
  loader, extracted from the test file)
- `tests/vivarium/test_karr_dna_damage_l2_replay.py` (modified: imports
  the shared loader instead of a private duplicate; no behavior change)
- `tests/vivarium/l2_2_replay_common_v2.py` (modified: `_ProcessSpec`/
  `_ProcessContext`/`_build_context` ledger-injection support)
- `scripts/l21_active_window_audit.py` (modified: `_honest_replay`
  per-tick ledger injection + fail-closed consumption check)
- `tests/scripts/test_l21_active_window_audit_chromosome_rand_stream_ledger.py`
  (new: 8 tests)
- `tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py`
  (modified: `EXPECTED_ACTIVE_WINDOW_VERDICTS["DNADamage"]` →
  `"GENUINE"`)
- `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` (modified:
  DNADamage row `classification` CODE_GAP → EXISTING_WINDOW_PASS,
  `existing_trace_suffices` → true, `source.path` rewritten to
  repo-relative, `counts` updated, new
  `note_harness_ledger_support_promotion_2026_09_05`)
- `docs/phase_f/l2_2_design_a/evidence_bundle/DNADamage/latest_event/*`
  and `docs/phase_f/l2_2_design_a/evidence_index.json` (regenerated
  sanity re-run, PASS/18-2-2 preserved, no value changes beyond
  provenance timestamps/hashes)
- `E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\
  per_process_traces_v2_event_s2000\` (NEW gitignored data files in a
  sibling worktree: the canonical trace + ledger sidecar, hash-verified;
  not a git change, no tracked file in that worktree was touched)
- This file.

### Not changed / explicitly out of scope this session

- The accepted 55-trace L2.2 corpus was still NOT re-extracted with
  chromosome-stream ledger capture (unchanged from Session 3 — the
  ledger-injection support added this session is currently exercised
  only by the canonical seed2000 trace, the only one with a companion
  ledger sidecar).
- `PROCESS_CATALOG.yaml` catalog `notes`/`blocked_on` prose — still
  untouched, still out of scope.
- No production `opencell/vivarium/` code was changed this session (per
  instruction: "no further production changes expected" — this session
  was audit-harness/manifest/test-only).
- `data/opencell_ensembles/translation/comparison_report.json` — the
  same unrelated pre-existing modification from Sessions 1-3, still
  preserved untouched (not staged, not reverted).

## Session 5 (2026-09-08): closed five Opus review blockers on the
## Session-4 EXISTING_WINDOW_PASS promotion (commit `a81a172`)

Opus's re-review of `966fb98` (Session 4) flagged five concrete gaps
before this promotion could be trusted. All five are closed, tested, and
committed:

1. **Portable raw-byte source-hash enforcement, hard-fail on an
   unresolvable path.** `chromosome_rand_stream_ledger.py` now hashes
   `Chromosome.m`/`RandStream.m` via `sha256_raw_bytes` (the ledger
   PRODUCER's own convention, not the LF-normalized convention used
   elsewhere), resolves the main-checkout fallback portably (the prior
   hardcoded `E:\opencell\...` path silently never resolved under WSL,
   this project's mandated execution environment), and raises a new
   `ChromosomeRandStreamLedgerError` (never a bare `assert`, stripped
   under `python -O`) instead of silently `continue`-ing past an
   unresolvable source or a missing source-hash field. Added a THIRD
   source check for `dnadamage_source_sha256`, cross-verified against
   the trace's own `dnadamage_source_resolved_sha256` metadata (since
   DNADamage.m may be an overlay-patched copy, not the pristine on-disk
   file).
2. **Ledger's own SHA pinned in the manifest and enforced by the nested
   audit.** The manifest's DNADamage row gained a
   `chromosome_rand_stream_ledger: {path, sha256}` object, independent
   of the ledger's own self-reported source-hash fields (which bind it
   to MATLAB source revisions/trace identity, not to any specific
   recorded draws). `scripts/l21_active_window_audit.py`'s new
   `_verify_manifest_ledger_binding` hard-fails
   `verify_active_window_manifest_row`'s `EXISTING_WINDOW_PASS` re-check
   if the live sidecar's hash doesn't match — closing a tamper vector
   where a regenerated/fabricated ledger with correct internal
   provenance but different draws would otherwise still pass.
3. **Missing ledger fails, not skips; nested audit detects a masked
   skip.** `test_karr_dna_damage_l2_event_replay_seed2000_chromosome_ledger`
   now `pytest.fail()`s (was `pytest.skip()`) when the trace is present
   but its ledger sidecar is missing. Independently,
   `_rerun_manifest_replay_nodeid` no longer treats pytest
   `returncode==0` alone as "passed" — it parses the actual outcome-count
   summary line (`_parse_pytest_summary_counts`) and requires a genuine
   `passed` count with zero skipped/failed/xfailed outcomes, so a
   silently-skipped nested pytest run can no longer masquerade as
   re-verified evidence.
4. **MATLAB `unique_subs` strand-major candidate order before
   `randsample`.** `_sample_literal_motif_sites` now sorts accumulated
   `(position, strand)` candidates by `(strand, position)` — matching
   `SparseMat.m`'s `unique_subs`/`sort_subs` linear-index weight vector
   `[1, dnaLength]` (strand dominates position) — before calling
   `randsample_without_replacement`, at both the per-round accumulation
   sort and the final `sort_subs` call. New regression test
   `test_sample_literal_motif_sites_sorts_candidates_by_strand_then_position_before_randsample`
   forces a genuine `n=3>k=1` selection where discovery order and
   `(strand, position)` order disagree.
5. **Repo-relative paths and hash copies** — re-verified unchanged from
   Session 4 (manifest `source.path` stays repo-relative; trace + ledger
   sidecar remain byte-identical across this worktree and
   `main-integrate`).

While turning item 4's new regression test green, found and fixed a bug
in the TEST ITSELF (not production code): the reverse-strand candidate's
synthetic sequence needs its RAW (positive-strand) base set to the
motif's complement (`_sample_literal_motif_sites` complements
reverse-strand windows before matching), not the motif itself — a
uniform-`'A'` sequence spuriously excluded that candidate from the
search, desynchronizing the scripted ledger by one draw.

**Full re-verification, all green:**
- Focused suite (`test_karr_dna_damage.py` + `test_karr_dna_damage_rng.py`
  + `test_karr_dna_damage_l2_replay.py` + both pre-existing audit-tool
  test files + the extended ledger-audit test file, 23 tests including
  8 new): **101 passed, 5 skipped** (documented seed 0-4 baseline,
  unaffected).
- Canonical seed2000 20-tick ledger-driven replay: **1 passed** (genuine
  bit identity, all 20 ticks).
- `verify_active_window_manifest_row("DNADamage")`:
  **VERIFIED_EXISTING_WINDOW_PASS**; manually confirmed fail-closed by
  temporarily renaming the ledger sidecar away (CODE_GAP with a clear
  `failure_reason`, restored after).
- **55-seed L2.2 event verifier** re-run against the accepted
  `genuine_signedzero_canary_v4`/`full_v2` corpus (`main-integrate`,
  hash-verified unchanged) after the production `karr_dna_damage.py`
  change: `n_events_karr=99`, `n_events_oc=84` — **unchanged** from the
  prior accepted baseline, confirming item 4's sort-order fix does not
  regress this corpus's aggregate distributional fidelity. Regenerated
  `evidence_index.json`: **18 PASS / 2 FAIL / 2 MISSING_EVIDENCE**
  preserved (the pre-existing, unrelated DNASupercoiling/
  MacromolecularComplexation FAILs and Cytokinesis/FtsZPolymerization
  MISSING_EVIDENCE rows); `generator audit` → `integrity: OK`; diffed
  old vs. new `evidence_index.json` — only DNADamage's own row + the
  top-level `content_hash`/`generated_at` changed.
- Strict L2.1 rubric (`test_probe_l2_1_strict_rubric_active_windows.py`):
  **14/14 passed** (707s), no regression to any process's verdict.
- L1b wiring verification (`test_l1b_verify_wiring.py`): **19/19
  passed**, unaffected.
- Ruff: clean on all changed files. `git diff --check`: clean.

No MATLAB session was needed this session (all fixes were
code/test/manifest-level, reusing already-extracted corpora). Committed
as `a81a172` on this branch. `data/opencell_ensembles/translation/
comparison_report.json` remains the same unrelated, pre-existing
modification from Sessions 1-4 — preserved untouched, not staged, not
reverted. Logged to `opencell/provenance/llm_interactions.jsonl`
(`event_id sha256:cee5d5fbce30fabf9d44d63908726972db2c7abb37cf2da898f8118e43597e20`).

**Not pushed/merged to main this session**, per the branch's standing
instruction — ready for re-review.
