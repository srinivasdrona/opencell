# STATUS: TranscriptionalRegulation L2.1 final clean integration (2026-09-09)

**Branch:** `integrate/l21-txreg-final` (new worktree, rooted at current
`origin/main`) -- **not merged/pushed to main.**
**Base:** `c56e7e4` (current main at branch time); merged forward to
`8d25274` mid-session (plan.md/provenance-only, no conflicts beyond
provenance's own event-id union, resolved).
**Preserves:** all accepted TxReg science/evidence from
`integrate/l21-txreg-clean@209a951` (Opus-ACCEPTED science, REJECTED
integration mechanics against current main).

## Why a new worktree

Current main had independently landed ReplicationInitiation's own L2.1
ledger-restored closure (`0dca05c` + later plan commits) since
`integrate-l21-txreg-clean` branched. RepInit's merge touched the exact
same shared files TxReg's candidate touched: `decisions/dec-006-*.md`,
`decisions/_decision_index.yaml`, `scripts/l21_active_window_audit.py`,
`tests/vivarium/l2_2_replay_common_v2.py`,
`tests/vivarium/chromosome_rand_stream_ledger.py`,
`scripts/matlab/reconstruct_chromosome_draw_ledger.m`,
`opencell/provenance/llm_interactions.jsonl`. Opus's review found the old
worktree's mechanical integration of these files unacceptable (effectively
asking for a 3-way union, not a naive merge/overwrite). Rather than
resolve that as a git merge conflict, this session built a brand-new
worktree/branch directly from current `origin/main` and surgically
re-applied only the TxReg-specific deltas on top of main's
RepInit-bearing versions of every shared file, verifying byte-for-byte
equivalence to the accepted candidate for every TxReg-exclusive file
along the way.

## Exact prescription followed (A-J)

**A. dec-006 union (one doc, one yaml entry).** Merged
`decisions/dec-006-shared-chromosome-randstream-input-oracle.md`:
shared title covering both processes
(`... (ReplicationInitiation, TranscriptionalRegulation)`); main's
Renumbering-note/Related-Decisions/Consequences sections kept verbatim;
candidate's "Invalidation triggers" section added (main's doc had none
in the body, only in the yaml index). `decisions/_decision_index.yaml`'s
single `dec-006` entry (immediately after `dec-005`, unchanged position)
now carries the union of both sides' invalidation triggers (3 main + 4
candidate = 7, no overlaps) plus candidate's
`renumbered_from`/`renumber_reason` fields (main's entry had neither).
Verified with a PyYAML round-trip test: 6 total decisions, all ids
unique, dec-006 has exactly 7 triggers and sits immediately after dec-005.

**B. `scripts/l21_active_window_audit.py`.** Started from current main
wholesale (kept `_CHROMOSOME_LEDGER_STREAM_CLS`, its fail-closed
`KeyError` message, and `disable_chromosome_rand_stream_ledger`
unchanged). Added one import
(`opencell.util.txreg_mcg_rand.TxRegChromosomeLedgerRandStream`) and one
registry line; the registry is now exactly `{"DNADamage":
KarrLedgerReplayStream, "ReplicationInitiation":
_ReplicationInitiationChromosomeLedgerRandStream,
"TranscriptionalRegulation": TxRegChromosomeLedgerRandStream}`. Removed
TxReg's 4 stale pre-site-level-rewrite custom-projection entries/branches
(`CUSTOM_COMPARE_OBSERVABLES["TranscriptionalRegulation"]`,
`CUSTOM_WID_ATTRS["TranscriptionalRegulation"]`, the `_tr_surface_order`
helper + its now-dead `lru_cache` import, and the two early-return/branch
bodies in `_overlay_custom_observable`/`_project_custom_observable`) that
shadowed the correct v2-spec projection and caused a spurious CODE_GAP
independent of any RNG/occlusion fix.

**C. `tests/vivarium/l2_2_replay_common_v2.py`.** RepInit's
(`chromosome_rand_stream_ledger_attr="_chromosome_rng"`) and DNADamage's
(`"_site_sampling_rng"`) specs/disable-flag preserved byte-for-byte.
TranscriptionalRegulation's spec fully rewritten to the real site-level
`tf_bound_promoters`/`bound_tfs` surfaces (34/5 entries), no longer
`pass_through` for `enzymes`/`boundEnzymes`, `hidden_read_surface=
("chromosome",)`, `chromosome_rand_stream_ledger_attr="_chromosome_rng"`.
Exactly three ledger-consuming process specs in the whole file, all three
registered in (B)'s registry.

**D. Regenerated trace+ledger copied pre-merge, hash-verified.** Copied
`TranscriptionalRegulation_4000ticks.mat`
(sha256 `73fc1d9710e2a98f61221d51a80cdbc490fb6d44db4ea95853414048c9fc7aa2`)
and its `.chromosome_rand_stream_ledger.json` sidecar
(sha256 `f01783e8356737429cf02bd90edf4b4063f49724092c5f77b2deb9dc303d2b67`)
from `integrate-l21-txreg-clean` into both this worktree and
`main-integrate`, replacing the stale pre-`window_contract='fixed'` pair
(`3c4931bb.../33c73974...`) that lacked the
`dnadamage_source_resolved_sha256` metadata field the shared ledger
loader requires. Verified via `Get-FileHash` before AND after the copy in
both destinations.

**E. `tests/vivarium/chromosome_rand_stream_ledger.py`.** Main's
normalization predicate (`isinstance(draws, (int, float)) and not
isinstance(draws, bool) and entry.get("n_draws") == 1: draws =
[float(draws)]`) kept verbatim -- more defensive than the candidate's
original (excludes `bool`, explicit float cast). Candidate's expanded
docstring merged in, additively extended to also name
ReplicationInitiation as a third consuming lane (candidate's docstring
only knew about DNADamage + TxReg).

**F. `scripts/matlab/reconstruct_chromosome_draw_ledger.m`.** Code logic
identical between main and candidate (verified via diff -- the only
difference was the top comment). Unioned the comment to name all three
consuming lanes (DNADamage, ReplicationInitiation, TranscriptionalRegulation)
in one paragraph.

**G. `opencell/provenance/llm_interactions.jsonl`.** Merged by
`event_id` (never by line/position), twice: once for the initial
candidate-vs-main union (335 main + 10 candidate-only = 345), once more
during the mid-session `origin/main` merge conflict (345 ours + 2
main-only = 347). Both merges verified duplicate-free.

**H. Manifest promotion, exact 11/0/0.** Fixed a real bug in
`scripts/l21_promote_transcriptional_regulation_manifest.py`: its counts
tally only ever wrote classification keys that actually occurred among
the rows, so a manifest with zero CODE_GAP/MISSING_ACTIVE_EXTRACTION rows
(exactly this promotion's outcome) would have silently omitted those keys
instead of writing them as `0`. Pre-initialized all three keys to 0
before tallying. Reran mechanically against this worktree's own
regenerated trace/ledger: **literal `{"EXISTING_WINDOW_PASS": 11,
"CODE_GAP": 0, "MISSING_ACTIVE_EXTRACTION": 0}`**, and the
`pytest_replay_command` field now lists exactly 11 nodeids.

**I. Host-verifier regression, no dependence on a real non-PASS row.**
Added `test_active_window_manifest_code_gap_row_verifies_via_synthetic_row`
to `tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py`. Before
this promotion, `verify_active_window_manifest_row`'s `CLASS_CODE_GAP`
re-verification branch was only incidentally exercised via
TranscriptionalRegulation's real CODE_GAP row inside the parametrized
`test_current_tree_active_window_manifest_checkpoint`; with the real
manifest now at a literal 11/0/0, that coverage would otherwise silently
disappear. The new test builds an entirely synthetic manifest row
(`HostInteraction`'s `process_name`, but a self-contained dummy trace
file this test creates and controls in `tmp_path`) and monkeypatches
`_summarize_trace_candidate`/`_classify_live_trace_candidate`, so it
depends on neither any real trace file's presence in this worktree nor
the real manifest containing any non-PASS row.

**J. Preservation checklist (verified, not merely assumed).**
`git status --porcelain` after every commit confirms this session never
touched: `opencell/vivarium/karr_replication_initiation.py`,
`opencell/vivarium/karr_dna_damage.py`/`karr_dna_damage_rng.py`,
`opencell/vivarium/karr_cytokinesis.py`, `karr_host_interaction.py`,
`karr_chromosome_segregation.py`, `scripts/matlab/
extract_per_process_traces_v2.m` (extractor API/tap points/containment/
unconditional-metadata-write all untouched), or
`tests/vivarium/test_l2_no_oracle_dependency.py`'s allowlist. TxReg's PIT
gate pilot evidence remains explicitly `PILOT_ONLY_NOT_A_GATE_VERDICT`
and outside the scored L2.2 catalog board, which is unchanged at
**18 PASS / 2 FAIL / 2 MISSING_EVIDENCE, integrity OK**.

## Genuine current-worktree verification (this session)

All commands run via `bin\oc-pytest.cmd`/`bin\oc-py.cmd` (WSL venv), per
project convention. Where this fresh worktree lacked another process's
large gitignored trace file, it was mirrored in from `main-integrate`
(the canonical accepted-evidence location) rather than skipped, so every
check below is a genuine run, not a data-dependent skip:

| Check | Result |
|---|---|
| TxReg no-skip exact replay (`test_karr_transcriptional_regulation_l2_event_replay[event_seed_0]`) | PASSED, bit-identical across all 4000 ticks (rerun twice: promoter run + final post-merge smoke check) |
| RepInit exact (`scripts/diagnose_repinit_l21.py`, ledger-restored default) | `bit_identity_pass=true`, `compared_tick_count=200`, `first_mismatch_tick=null` |
| RepInit `--no-ledger` (honest non-ledger diagnostic) | `bit_identity_pass=false`, `compared_tick_count=200`, `first_mismatch_tick=15` (`enzymes[0]`) -- exact match to `STATUS_L21_REPINIT_SEPT2.md`'s reported numbers |
| DNADamage replay (`test_karr_dna_damage_l2_event_replay_seed2000_chromosome_ledger`) | PASSED |
| All active windows (`tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py`, full file incl. the new Host-verifier regression) | **16/16 passed** (all 11 `test_current_tree_active_window_manifest_checkpoint[*]` rows GENUINE, plus 5 verifier-mechanics tests) |
| Ledger tests (`tests/vivarium/chromosome_rand_stream_ledger.py` + `test_chromosome_rand_stream_ledger.py` + `test_l21_active_window_audit_chromosome_rand_stream_ledger.py`) | 54/54 passed |
| Extractor static tests (`test_extract_per_process_traces_v2_static.py`) | included in the 52/52 below |
| Rule 8 (`tests/prompts/test_rule8_no_oracle_reads.py`) + oracle-dependency (`test_l2_no_oracle_dependency.py`) + extractor | 52/52 passed |
| L1b (`test_l1b_verify_wiring.py`) + `tests/provenance/` | 63/63 passed |
| L2.2 generator audit | `integrity: OK`, **18 PASS / 2 FAIL / 2 MISSING_EVIDENCE** (unchanged) |
| TxReg unit suite (`test_karr_transcriptional_regulation*.py`, `test_txreg_mcg_rand.py`) | 80/80 passed |
| PIT gate suite (`test_l22_evidence_txreg_pit_gate.py`) | 20/20 passed |
| PIT gate pilot rerun | byte-identical statistics to the previously accepted run (`ks_pvalue=0.422`, `n_events=45`), verdict still `PILOT_ONLY_NOT_A_GATE_VERDICT` |
| Ruff on every touched Python file | All checks passed |
| MATLAB source | Worktree had no local `data/m1_sources/WholeCell` copy; `karr_bootstrap()` correctly fell back to the main checkout's `E:\opencell\data\m1_sources\WholeCell` (verified in the trace-regeneration log from the prior session; unchanged this session since no further extraction was needed) |

## Not done / explicitly out of scope

- Not merged or pushed to `main`.
- `main-integrate`'s own copy of the manifest/decisions/audit-harness
  files was **not** updated in this session (only its gitignored
  trace/ledger pair, per item D's explicit "pre-merge" scope) -- that
  worktree's own manifest/code stays on current-main content until an
  actual merge lands.
- Cytokinesis/HostInteraction/FtsZ/RibosomeAssembly/ChromosomeSegregation
  large trace data was mirrored into this worktree purely so the
  validation suite above could run without data-dependent skips; it was
  not modified, re-extracted, or re-verified beyond confirming the
  existing manifest rows still verify.

## Next step

Ready for one final, lightweight Opus integration review of
`integrate/l21-txreg-final` against current `origin/main`.
