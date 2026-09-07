# STATUS_L21_DNADAMAGE_INTEGRATION.md

Worktree: `E:\opencell-worktrees\integrate-l21-dnadamage-clean`
Branch: `integrate/l21-dnadamage-clean`, based on `main` @ `82b26ca`
("chore: route DNADamage curated integration").
Source candidate: `E:\opencell-worktrees\fix-l21-dnadamage-active`,
branch `agent/l21-dnadamage-active-fix-20260903` @ `a81a172`
("fix(l21-dnadamage): close Opus review blockers -- source-hash tamper
vectors, silent-skip promotion, MATLAB sort order"), Opus-accepted per
`plan.md`'s DNADamage L2.1 entry ("Final Opus re-review **ACCEPTED
curated integration**").

## Scope discipline

Only DNADamage-scoped hunks were pulled from the candidate branch. The
candidate branch's own diff vs. its merge-base (`4054fd9`) also touched
ChromosomeSegregation/Cytokinesis/HostInteraction/TranscriptionalRegulation
test files, `tmp/*`, `.progress_*` files, and its own local catalog/index
copies -- **none of that was copied**. Where a shared multi-process file
needed a DNADamage-only addition (`scripts/l21_active_window_audit.py`,
`tests/vivarium/l2_2_replay_common_v2.py`,
`scripts/matlab/extract_per_process_traces_v2.m`), the candidate's diff
vs. merge-base was extracted and applied with `git apply --3way` against
this worktree's own (differently-evolved, already-integrated-elsewhere)
copy of each file; the 3-way merge mechanically discarded every hunk
already present here (from separately-integrated ChromSeg/HostInteraction/
stress-profile lanes) and kept only the true DNADamage-ledger additions.
Diffs were inspected post-merge to confirm zero non-DNADamage content
leaked in.

## Files restored/added (scoped)

- `opencell/vivarium/karr_dna_damage.py` (modified, byte-identical to
  candidate's `a81a172` plus the two latent fixes below)
- `opencell/vivarium/karr_dna_damage_rng.py` (new, byte-identical to
  candidate)
- `tests/vivarium/chromosome_rand_stream_ledger.py` (new, byte-identical)
- `tests/vivarium/l2_2_replay_common_v2.py` (DNADamage
  `chromosome_rand_stream_ledger_attr`/`_build_context` field only)
- `tests/vivarium/test_karr_dna_damage.py`,
  `test_karr_dna_damage_l2_replay.py`, `test_karr_dna_damage_rng.py`
  (byte-identical to candidate after 3-way merge conflict resolution)
- `scripts/l21_active_window_audit.py` (DNADamage ledger-injection hunks
  only: `KarrLedgerReplayStream` wiring in `_honest_replay`,
  `_verify_manifest_ledger_binding`, `_parse_pytest_summary_counts`,
  stricter `_rerun_manifest_replay_nodeid`)
- `scripts/matlab/extract_per_process_traces_v2.m`
  (`merge_chromosome_rand_stream_state` capture hunk only --
  `apply_condition_overrides`/`boundTFs` were already present here from
  the separately-integrated stress-profile lane and were left untouched)
- `scripts/matlab/reconstruct_chromosome_draw_ledger.m`,
  `probe_l21_randsample_exact.m`, `probe_l21_chromosome_randstream_state.m`,
  `probe_l21_randsample_vs_randperm_direct.m`,
  `instrument_dnadamage_tick4_per_reaction.m` (new, byte-identical)
- `tests/scripts/test_l21_active_window_audit_chromosome_rand_stream_ledger.py`
  (new, then re-scoped per the second latent fix below)
- `tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py`
  (`EXPECTED_ACTIVE_WINDOW_VERDICTS["DNADamage"]` -> `"GENUINE"` only)
- `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` (DNADamage row
  replaced wholesale with candidate's final row; `counts` recomputed by
  tallying every row's `classification` -- every other row byte-identical)
- `STATUS_L21_DNADAMAGE_ACTIVE_FIX.md` (candidate's own STATUS, carried
  over as historical audit trail, matching the convention already used
  by the ChromCond/PPII/Macromol/mnrnd-provider integration lanes)
- `docs/phase_f/l2_2_design_a/evidence_bundle/DNADamage/latest_event/*`
  and `docs/phase_f/l2_2_design_a/evidence_index.json` (regenerated on
  this branch, not copied -- see below)

**Not copied** (excluded by task scope): candidate's own copies of
`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`,
`docs/phase_f/l2_2_design_a/evidence_index.json`,
`docs/phase_f/l2_2_design_a/evidence_bundle/DNADamage/`, any
`karr_bootstrap.m`/Macromol/M5000/ChromSeg files, `tmp/*`,
`.progress_*`.

## Two latent fixes applied during integration (not present in `a81a172`)

Per `plan.md`'s accepting Opus re-review: *"Include two nonblocking but
real cleanups before merge: sort non-string selected indices like MATLAB
`sort(rndIdxs)`, and scope data-absence skips only to data-dependent
tests."*

1. **`sort(rndIdxs)` in the non-string branch.** Karr's real
   `+edu/+stanford/+covert/+util/RandStream.m::randomlySelectNRows`
   (lines 249-252) is `rndIdxs = sort(randsample(this.randStream,
   size(mat,1), nRndRows, false)); mat = mat(rndIdxs,:)` -- the selected
   1-based row indices are sorted ASCENDING before indexing, not left in
   raw `randsample` draw order. `karr_dna_damage.py::_sample_reaction_coords`'s
   non-string branch (the literal port of
   `Chromosome.m::setSiteDamaged`'s `randomlySelectNRows` call) was
   missing this sort -- it mapped `candidates[idx-1] for idx in
   order_1based` in raw draw order. This is a pure reordering (does not
   change WHICH candidates are selected), but the returned list's order
   is consumed positionally by downstream damage-site processing, so it
   must match Karr's real row order exactly. Fixed by adding
   `order_1based = sorted(order_1based)` before the list comprehension,
   with an inline comment citing the exact MATLAB source lines. (The
   sibling string-motif branch, `_sample_literal_motif_sites`, already
   re-sorts its final output by `(strand, position)` after selection --
   Karr's own `sort_subs` call -- so it was not affected by this gap.)

2. **Module-level skip marker scoped to only data-dependent tests.**
   `tests/scripts/test_l21_active_window_audit_chromosome_rand_stream_ledger.py`
   had a module-level `pytestmark = pytest.mark.skipif(not (trace and
   ledger present), ...)` that silently skipped EVERY test in the file
   whenever the gitignored canonical seed2000 trace/ledger tree is
   absent from a checkout (e.g. CI, a fresh clone) -- including six pure
   unit tests that need neither file: the two `_ProcessSpec`
   declaration tests, `test_verify_manifest_ledger_binding_none_when_row_declares_nothing`,
   the parametrized `test_parse_pytest_summary_counts`, and the two
   monkeypatched `test_rerun_manifest_replay_nodeid_*` tests (whose own
   docstrings explicitly say "this test does not depend on any
   gitignored trace/ledger data being present in this checkout"). Fixed
   by replacing the module-level `pytestmark` with a named
   `_requires_canonical_trace = pytest.mark.skipif(...)` marker applied
   per-test to only the 13 tests that genuinely read
   `_CANONICAL_TRACE`/`_CANONICAL_LEDGER`; the six data-independent
   tests are now undecorated and always run.

## Data files copied into this worktree (gitignored, not committed)

- `data/m1_sources/karr_native/per_process_traces_v2_event_s2000/
  DNADamage_20ticks.mat` -- sha256
  `7be78871919f0e6d480f73e1c5de6cb541540e04f0069ed541dcd076934252f0`
- `data/m1_sources/karr_native/per_process_traces_v2_event_s2000/
  DNADamage_20ticks.chromosome_rand_stream_ledger.json` -- sha256
  `d2d04d7a747f22d196a64deae3139c8659963cbb965ae825ee1d56dca1964588`

Both copied byte-for-byte from `main-integrate`'s already-accepted copy
(hashes verified identical); the manifest's `source.path` is
repo-relative so this resolves identically from any worktree.

- `data/m1_sources/karr_native/per_process_traces_v2_event_s000/
  ChromosomeSegregation_100ticks.mat` -- sha256
  `84d78428490411f5b5cf7271f3ea6dbb62bc1a57b2654ef433ed5f1a8c2c38a1`
  (see "Incidental fix" below -- this is a pre-existing, unrelated row's
  data file, copied only so its own already-accepted evidence resolves
  locally; the row itself was not touched).

## Manifest surgical edit

`docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`: the `DNADamage`
row was replaced wholesale with the candidate's final `a81a172` row
(`classification: CODE_GAP -> EXISTING_WINDOW_PASS`, repo-relative
`source.path`, new `chromosome_rand_stream_ledger` object pinning the
ledger sidecar's own sha256, renamed `replay_evidence.nodeid` to the
dedicated ledger-aware test, full historical note trail preserved). Top-
level `counts` was recomputed by tallying every row's `classification`
field (not hand-edited): `EXISTING_WINDOW_PASS` 7->8, `CODE_GAP` 3->2,
`MISSING_ACTIVE_EXTRACTION` unchanged at 1. `git diff --stat` confirms
only the DNADamage row + `counts` changed; every other row is
byte-identical to pre-integration `main`.
`EXPECTED_ACTIVE_WINDOW_VERDICTS["DNADamage"]` in
`test_probe_l2_1_strict_rubric_active_windows.py` was updated from
`active_windows.CLASS_CODE_GAP` to the literal string `"GENUINE"` (the
convention already used by every other `EXISTING_WINDOW_PASS` process in
that dict).

## Incidental fix required to reach a genuine 14/14 (not a scope change)

Running the full strict rubric suite from this worktree exposed that
`ChromosomeSegregation`'s manifest row's nested replay re-verification
(`test_karr_chromosome_segregation_l2_replay.py::
test_karr_chromosome_segregation_l2_event_replay[event_seed_0]`) was
silently **SKIPPED** in this worktree (its own trace file was never
copied here) rather than genuinely passing. Before this integration's
shared-harness fix (`_rerun_manifest_replay_nodeid`'s stricter
skip-detection, part of the accepted DNADamage curated-integration
scope), a `returncode==0`-only check would have silently accepted that
skip as a "pass" -- exactly the class of masked-skip bug Opus's review
called out. With the fix correctly in place, this pre-existing gap in
this worktree's local data population surfaced as a real, reproducible
failure. This is not a code or manifest bug in ChromosomeSegregation's
row (main-integrate has the exact same trace file, hash-identical, and
that row's own accepted evidence is untouched) -- it is this worktree
simply missing a copy of already-accepted, gitignored data. Fixed by
copying `ChromosomeSegregation_100ticks.mat` from `main-integrate` (hash
verified identical, see above). The `ChromosomeSegregation` row itself
was **not edited** in any way -- only its data file was made locally
resolvable, exactly the same class of fix already applied to DNADamage's
own row in an earlier session.

## DNADamage L2.2 event bundle -- regenerated on this branch, not copied

Regenerated via `scripts.l22_evidence.dna_damage_event_verifier`,
pointed at the accepted 55-trace `genuine_signedzero_canary_v4` (5
traces) / `genuine_signedzero_full_v2` (50 traces) raw corpus under
`main-integrate` (`--canary-root`/`--full-root`, the tool's own
supported root arguments -- no raw MATLAB corpus was copied into this
worktree, no MATLAB was launched, no data was re-extracted):

```
bin\oc-py -m scripts.l22_evidence.dna_damage_event_verifier \
  --canary-root /mnt/e/opencell-worktrees/main-integrate/data/m1_sources/karr_native/genuine_signedzero_canary_v4/dnadamage_stimulus_cohort/uvb_mechanism \
  --full-root   /mnt/e/opencell-worktrees/main-integrate/data/m1_sources/karr_native/genuine_signedzero_full_v2/dnadamage_stimulus_cohort/uvb_mechanism
```

Result: `verdict=PASS`, `full.observed_pooled_fire_ticks_karr=99`,
`full.observed_pooled_fire_ticks_oc=84` (the required Karr99/OC84 pair),
`full.mechanical_verdict=PASS`; canary sub-check remains
`PRIMARY_INSUFFICIENT_SAMPLES` (N=5, non-gating, unchanged pre-existing
behavior). Then regenerated the per-process catalog-provenance index:

```
bin\oc-py -m scripts.l22_evidence.generator generate
bin\oc-py -m scripts.l22_evidence.generator audit
```

`generate` -> 22 rows, aggregate NON_GREEN, **PASS 19 / FAIL 1 /
MISSING_EVIDENCE 2** (the required 19/1/2 board). `audit` ->
`integrity: OK`, identical tally. Diffed the regenerated
`evidence_index.json` against pre-integration `main`: only the
`DNADamage` row plus the top-level `content_hash`/`generated_at` fields
changed; the pre-existing DNASupercoiling/MacromolecularComplexation
FAIL and Cytokinesis/FtsZPolymerization MISSING_EVIDENCE rows are
untouched. The candidate branch's own stale bundle/index (computed
against its own, differently-evolved copy of the other 21 rows) was
never copied.

## Test/gate results (this worktree, post-integration)

- Focused suite (`test_karr_dna_damage.py` + `test_karr_dna_damage_rng.py`
  + `test_karr_dna_damage_l2_replay.py` + both pre-existing audit-tool
  test files + the ledger-audit test file): **88 passed, 5 skipped**
  (documented seed 0-4 UVB-trace-not-found baseline, unaffected -- the
  second latent fix above correctly un-hid the six previously-masked
  data-independent unit tests without changing this count).
- Exact 20-tick canonical replay
  (`test_karr_dna_damage_l2_event_replay_seed2000_chromosome_ledger`):
  **1 passed**.
- Manifest verifier (`verify_active_window_manifest_row("DNADamage")`):
  `verification_status=VERIFIED_EXISTING_WINDOW_PASS`,
  `fresh_classification=EXISTING_WINDOW_PASS`, source hash match,
  nested replay `replay_verification={"passed": true, "summary_counts":
  {"passed": 1}, ...}` -- **1 passed**, no masked skip.
- Strict L2.1 active-windows rubric
  (`test_probe_l2_1_strict_rubric_active_windows.py`): **14 passed**
  (after the incidental ChromosomeSegregation data-file fix above; 0
  regressions to any other process's verdict).
- L1b wiring verification (`test_l1b_verify_wiring.py`): **19 passed**.
- Ruff: clean on all 10 changed/added Python files.
- Provenance tests (`tests/provenance/`): **44 passed**.

## Not done / explicitly out of scope

- No push, no merge into `main`. This branch remains a clean, isolated
  integration candidate at the tip described below.
- Candidate's disclosed architectural ceiling (site-sampling draws come
  from a freshly-seeded stand-in stream for every trace lacking a
  companion ledger sidecar -- i.e. every seed except the canonical
  seed2000) is unchanged and out of scope for this integration.
- No other process's manifest row, catalog entry, or evidence bundle was
  touched beyond the incidental ChromosomeSegregation data-file copy
  documented above (which touched no tracked file).

## Provenance

Logged to `opencell/provenance/llm_interactions.jsonl` after the
integration commit (`c330fe5`), and separately unioned the candidate
branch's own 10 DNADamage-tagged provenance entries (Sessions 1-5:
mcg16807 RNG port through the ledger-injection/promotion closure) into
this branch's log, deduped by `event_id` -- append-only, content-
addressed, zero duplicates after merge (320 unique ids). This preserves
the candidate's own methodology audit trail rather than dropping it
during integration.

## Final commits on this branch (relative to `main` @ `82b26ca`)

1. `c330fe5` -- fix(l21-dnadamage): curated integration (scoped files +
   two latent fixes + manifest edit + L2.2 regen)
2. `b97ca96` -- chore(l21-dnadamage): log LLM interaction provenance for
   curated integration c330fe5
3. `97356e5` -- chore(l21-dnadamage): union candidate DNADamage
   provenance entries by event_id

Working tree is clean; branch has **not** been pushed or merged into
`main`.
