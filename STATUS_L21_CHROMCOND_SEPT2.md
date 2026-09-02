# STATUS: L21 ChromCond — SEPT2 tick-7 fidelity gap — CLOSED

**Result: FIXED. Root cause found and confirmed via a real production bug
(spurious extra RNG draw), not a harness artifact. Full 100-tick applied
hidden-surface `complexBoundSites` scan is now bit-identical to Karr on all
100 ticks (was 38/100 mismatched, first divergence at tick 7).**

Branch: `agent/l21-chromcond-20260812`
Fix commit: `b2e6e0d` ("Fix ChromCond spurious extra RNG draw causing tick-7+
SMC bind desync")

## 1. What PROMPT_SEPT2.md asked for

The official branch strict rubric already reported GENUINE, but the
no-known-gap rule still blocked closure because the applied hidden
`complexBoundSites` first differed at tick 7:

```
missing (357086, 0, 82)
extra   (355990, 0, 82)
```

Task: build the narrow source-vs-Python ledger for the tick-7 SMC bind,
determine whether this is an applicable `ChromosomeCondensation` bug or a
later process's mutation, fix it if applicable, then run the full
validation battery and report the recertification blast radius for the two
shared files (`opencell/util/matlab_rng.py`, `tests/vivarium/l2_replay_common.py`).

## 2. Methodology correction (prerequisite to any real investigation)

`tmp/chromcond_hidden_mismatch_probe.py` (pre-existing, untracked from an
earlier session) was comparing the **raw emitted update dict** to Karr's
`states_after/chromosome`, not the **update applied onto the injected
ground-truth state**. That is not a valid comparison (an update dict is a
delta, not a state). Fixed it to call `apply_count_update` first. Re-ran:
reproduced the task's exact stated tick-7 mismatch
(`missing=[(357086, 0, 82)]`, `extra=[(355990, 0, 82)]`, `karr_len=oc_len=212`),
confirmed ticks 0-6 bit-identical. This corrected probe is the canonical
per-tick reproduction used for the rest of the investigation.

## 3. Live-MATLAB oracle attempt — blocked by genuine shared-infra contention

Built a live-MATLAB tick-7 geometry probe pair
(`tmp/chromcond_export_hidden_tick7_exact_surface.py` +
`tmp/chromcond_tick7_exact_geometry_probe.m`) to restore the exact pre-tick-7
surface into a real `ChromosomeCondensation` MATLAB instance. Launched via
`with_matlab_slot.ps1 -Tag l21-chromcond-tick7 -Slots 4`. All 4 shared slots
remained held continuously by 4 other worktrees' genuinely-active MATLAB
processes for 2+ hours (confirmed via `Get-Process matlab` CPU time
climbing from ~8900s to ~15100s+, and direct lock-file-in-use errors — not
stale/orphaned locks). The job never acquired a slot; it was stopped.
**Investigation pivoted to static source analysis + Python instrumentation**,
which turned out to be sufficient to find and fix the root cause without
live MATLAB. The probe pair remains committed and ready to run in a future
session for an independent live-MATLAB confirmation
(`bin\pwsh -File tools\with_matlab_slot.ps1 -Tag <tag> -Slots 4 -- <cmd>` —
re-run `chromcond_export_hidden_tick7_exact_surface.py` first if the
`.mat` artifact has been cleaned up).

## 4. Root-cause ledger (the actual bug)

### 4.1 Exhaustive line-by-line audit — all formulas confirmed exact matches

Read in depth and verified byte-for-byte against production
`karr_chromosome_condensation.py`:
- `Chromosome.m` (`getAccessibleRegions`, `calcDoubleStrandedRegions`,
  `calcSingleStrandedRegions`, `getReleasableProteins`)
- `ChromosomeCondensation.m` (`evolveState`'s existing-SMC exclusion-offset
  formula, `calcNewRegions`)
- `ChromosomeProcessAspect.m` (`bindProteinToChromosomeStochastically`'s main
  bind loop and its nested `calcRegionWeights`/`calcBindingPosition`/
  `calcNewRegions`)
- `RandStream.m` (`randsample`)

Confirmed exact matches for: the SMC exclusion-offset formula, the
`calcBindingPosition` offset formula (`ceil(rand*n)-1`), the main bind loop
structure (`for i=1:nProteins; if ~any(rgnProbs) break; pick region; pick
offset; split region; end`), and the `getReleasableProteins` criterion. One
confirmed-but-functionally-inert divergence was also found and ruled out:
`_build_accessible_regions_literal`'s minimum-length filter (absent from the
real `getAccessibleRegions`) drops 35 regions genome-wide but none within
3000bp of the tick-7 boundary, and (via the weighted-sampling math which
normalizes by `sum(weights)`) has zero effect whenever a single region
dominates the weight vector — left unchanged (not the bug, not worth the
unverified genome-wide risk of removing it for zero benefit).

### 4.2 The actual bug — found via structural comparison, confirmed empirically

`_sample_smc_binding_no_hints`'s literal path called an extra,
**structurally spurious** RNG draw after every successful bind:

```python
n_bound = len(bound_centroids)
if n_bound == 0:
    return 0, None
self._consume_inner_bind_sampling_literal(n_bound=n_bound)   # <-- REMOVED
```

```python
def _consume_inner_bind_sampling_literal(self, *, n_bound: int) -> None:
    n_bound_i = max(0, int(n_bound))
    if n_bound_i <= 0:
        return
    _ = self._rng.randsample(n_bound_i, n_bound_i, False, np.ones(n_bound_i, dtype=np.float64))
```

**No counterpart to this call exists anywhere in the real WholeCell
source.** `ChromosomeProcessAspect.m`'s `bindProteinToChromosomeStochastically`
loop (lines 44-140) — the actual mechanism `ChromosomeCondensation.m`
delegates its SMC binding to — only ever calls `randStream.randsample`
(region pick) and `randStream.rand` (offset draw) once per bound protein per
loop iteration, then breaks when `~any(rgnProbs)`. There is no post-bind
shuffle, permutation, or "consume" call of any kind (verified via targeted
grep across both `.m` files for `randperm`/`shuffle`/extra `randsample`
calls — none found beyond the two documented per-iteration calls).

This call was introduced in commit `8d06797` (as `self._rng.randperm(n, n)`)
during the initial literal-path implementation, then changed to the
`randsample(..., replace=False, ...)` form in `2d917d4`. Neither commit
message nor any STATUS file documents an explicit MATLAB source citation for
its existence; the only related historical note
(`STATUS_L21_CHROMCOND_RESTART.md`) discusses an unrelated "inner randperm"
variant tested during **warmup-boundary-state-recovery** experiments (a
different code path, `initializeState`'s 20 warmup calls, not per-tick
`next_update`), which was never adopted into the final warmup handoff either.
No test in `tests/` asserts on this method's existence or behavior.

Every tick with `n_bound == 0` never calls it (consistent with ticks 0-6
passing — they have no SMC bind that tick). Tick 7 is the first tick with
`n_bound > 0` in the hidden trace, so it is the first tick this extra draw
fires, silently shifting the entire subsequent `MatlabRandStream` sequence
out of sync with true MATLAB's stream position from that point onward. Once
desynchronized, every later tick whose outcome actually depends on the drawn
value can diverge (some ticks still coincidentally match — e.g. no binding
occurs that tick, or the "wrong" draw still lands in the same region by
chance) — which is exactly the pattern seen: 38 of 100 ticks in the trace
mismatched, all starting from tick 7 onward, all on `complexBoundSites`
entries with `value=82` (SMC-ADP) positions off by a few hundred to a few
thousand bp, never a wrong-shape/wrong-count mismatch.

### 4.3 Empirical confirmation

Built `tmp/chromcond_hidden_mismatch_full_scan.py` (new; a full-100-tick
variant of the corrected probe that does **not** stop at the first
mismatch — it re-injects Karr's ground-truth chromosome state fresh every
tick per the existing hidden-replay methodology, so a mismatch at tick N
does not invalidate the independent check at tick N+1):

| Run | Mismatched ticks | First divergence |
|---|---|---|
| Before fix (baseline `ce54280`) | **38 / 100** | tick 7 |
| After removing the spurious `_consume_inner_bind_sampling_literal` call (monkeypatch experiment) | **0 / 100** | none |
| After the real production fix (commit `b2e6e0d`) | **0 / 100** | none |

Both the monkeypatch experiment and the actual production removal produce
identical bit-perfect 100-tick agreement, confirming this is the complete
and sole root cause of the tick-7+ divergence — no residual gap.

## 5. Applicability determination

**Applicable ChromosomeCondensation bug**, not a downstream process's
mutation and not a harness/extraction artifact. The divergence originates
entirely within `KarrChromosomeCondensationProcess.next_update`'s own SMC
bind path; no other process's state or code is involved. Fixed by deleting
the call site and the now-dead `_consume_inner_bind_sampling_literal` method
(12 lines removed, 0 lines of behavior-preserving replacement needed — the
call had no valid purpose to preserve).

## 6. Validation battery

| Check | Command | Result |
|---|---|---|
| Hidden replay (single-tick corrected repro) | `bin\oc-py.cmd tmp/chromcond_hidden_mismatch_probe.py` | `NO_COMPLEX_MISMATCH` (was `FIRST_COMPLEX_MISMATCH tick 7` before fix) |
| Hidden replay (full 100-tick scan, new) | `bin\oc-py.cmd tmp/chromcond_hidden_mismatch_full_scan.py` | `0 mismatched tick(s) of 100` (was `38/100`, first at tick 7) |
| Official 100-tick replay + focused suite | `bin\oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation_l2_replay.py tests/vivarium/test_karr_chromosome_condensation.py tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py -q` | **9 passed, 1 skipped** |
| Strict rubric — L2.1 (ChromCond-relevant) | `bin\oc-pytest.cmd tests/vivarium/test_l2_1_strict_rubric.py -q` | **28 passed** |
| Strict rubric — L2.2 (broader, unrelated processes) | `bin\oc-pytest.cmd tests/vivarium/test_l2_2_strict_rubric.py -q` | 31 passed, 2 failed — **both failures confirmed pre-existing and unrelated** (see §6.1) |
| L1b anchors | `bin\oc-py.cmd scripts/l1b_verify_wiring.py --process ChromosomeCondensation --strict-anchors --format plain` | FAIL (`check_oc_anchors_resolve`) — **confirmed pre-existing**, caused solely by the already-dirty, uncommitted `data/schemas/per_process_wiring/ChromosomeCondensation.yaml` (see §6.1); identical failure reproduced with this session's fix reverted |
| Default/no-manifest parity (fixture-default init + trace-anchor tests, no wiring-manifest override) | `test_process_initializes_with_fixture_defaults`, `test_100_tick_steady_state_matches_trace_anchor` (in the focused suite above) | **PASS** (both included in the 9-passed focused run) |
| Ruff | `bin\oc-py.cmd -m ruff check opencell/vivarium/karr_chromosome_condensation.py tmp/chromcond_hidden_mismatch_probe.py tmp/chromcond_hidden_mismatch_full_scan.py tmp/chromcond_export_hidden_tick7_exact_surface.py` | **All checks passed** |

### 6.1 Pre-existing-failure confirmation methodology

For both the L2.2 strict-rubric failures and the L1b anchor failure, I used
`git stash push -- opencell/vivarium/karr_chromosome_condensation.py` to
temporarily revert **only** this session's fix (leaving the pre-existing
dirty wiring YAML and everything else untouched), re-ran the exact same
command, and observed byte-identical failure output before restoring the
stash. This proves both failures pre-date and are independent of this
session's fix:
- L2.2: `test_committed_evidence_index_passes_integrity_audit` and
  `test_committed_evidence_index_is_honestly_non_green_today` fail on stale
  committed sweep-evidence tallies for **other** processes
  (MacromolecularComplexation, ProteinFolding, DNASupercoiling, etc.) —
  ChromosomeCondensation is not among the failing rows.
- L1b: `check_oc_anchors_resolve` fails because the dirty (uncommitted, must
  NOT be committed per task instruction)
  `data/schemas/per_process_wiring/ChromosomeCondensation.yaml` references
  anchors that no longer resolve against current line numbers — same failure
  with or without this session's fix applied.

## 7. Recertification blast radius (shared files)

`opencell/util/matlab_rng.py` and `tests/vivarium/l2_replay_common.py` were
**not modified this session** (confirmed via `git diff --stat` — zero
output for both). No recertification is actually required as a result of
this fix. For completeness, the consumer census (unchanged from the prior
session's analysis, re-verified this session):

- **`MatlabRandStream`** (`opencell/util/matlab_rng.py`) is used in
  production by exactly 3 processes:
  `opencell/vivarium/karr_chromosome_condensation.py`,
  `opencell/vivarium/karr_protein_translocation.py`,
  `opencell/vivarium/karr_replication.py`.
- **`l2_replay_common.py`**'s `apply_count_update` (and friends) is imported
  by **48 test files**, covering the chromosome-hidden-read-surface
  processes and the L2.1 strict rubric.

Since neither shared file changed, none of these consumers require
recertification from this fix. This row is reported per task instruction as
a standing check, not because any blast radius actually materialized.

## 8. Files changed / committed (commit `b2e6e0d`)

- `opencell/vivarium/karr_chromosome_condensation.py` — removed the spurious
  `_consume_inner_bind_sampling_literal` call site and method (the fix).
- `tmp/chromcond_hidden_mismatch_probe.py` — corrected reproduction
  methodology (apply-then-compare instead of raw-update comparison).
- `tmp/chromcond_hidden_mismatch_full_scan.py` — new; full-100-tick
  continue-past-first-mismatch scan, the decisive empirical proof.
- `tmp/chromcond_export_hidden_tick7_exact_surface.py` — new; live-MATLAB
  oracle export tool (ready for a future independent confirmation run).
- `tmp/chromcond_tick7_exact_geometry_probe.m` — new; live-MATLAB oracle
  probe (never executed this session due to slot contention; ready to run).

## 9. Explicitly preserved / NOT committed (per task instruction)

- `data/schemas/per_process_wiring/ChromosomeCondensation.yaml` — dirty,
  untouched, not committed.
- `7` (untracked, 0 bytes, repo root) — untouched, not committed.
- `STATUS_L21_CHROMCOND_RESTART.md`, `opencell/provenance/llm_interactions.jsonl`,
  `tmp/chromcond_prewarmup_inspect.py`, `tmp/chromcond_prewarmup_replay_probe.py`,
  `tmp/chromcond_validate_warmup_state.m` — pre-existing dirty diagnostics
  from earlier sessions, preserved as-is (not part of this session's diff).
  A new LLM interaction log entry was appended to the tail of the (already
  dirty) `llm_interactions.jsonl` per repo convention, but the file itself
  was left unstaged/uncommitted so its pre-existing dirty content is not
  disturbed. (Note: an earlier attempt at this append accidentally landed
  in the **main repo's** copy at `E:\opencell` due to the WSL venv's
  editable install resolving `opencell.provenance` to `/mnt/e/opencell/src`
  by default; this was caught, reverted cleanly — leaving only another
  concurrent session's unrelated FtsZ entry intact — and redone correctly
  against the worktree's own copy by explicitly inserting this worktree's
  root at the front of `sys.path`, matching the `_REPO_ROOT` pattern already
  used by `test_karr_*_l2_replay.py`.)
- Many pre-existing untracked `tmp/chromcond_*` scratch files from earlier
  sessions (region diagnostics, RNG probes, etc.) — left untracked,
  unchanged, consistent with established repo convention that only
  "final, decisive" probes get committed per session.
- `.progress_l21_chromcond*.md` — pre-existing untracked progress files,
  untouched.

## 10. Bottom line

No known hidden fidelity gap remains in `ChromosomeCondensation`. The
tick-7 SMC binding-site shift was a real, applicable, single-root-cause bug
(a spurious extra RNG-consuming call with no basis in the WholeCell MATLAB
source), now removed. Full 100-tick hidden-surface replay is bit-identical
to Karr on every tick. All ChromCond-relevant tests pass; the two remaining
test failures elsewhere in the repo (L2.2 strict rubric evidence-index, L1b
wiring anchors) are confirmed pre-existing and unrelated via stash-based
before/after comparison. No shared-index/catalog files were edited. Live
MATLAB confirmation remains available as a follow-up (probe pair committed
and ready) but is no longer required for closure given the source-level and
100-tick empirical proof above.
