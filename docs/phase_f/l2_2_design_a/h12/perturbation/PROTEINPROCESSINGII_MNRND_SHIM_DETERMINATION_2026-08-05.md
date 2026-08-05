# ProteinProcessingII H12 SENTINEL_FAIL — closure investigation & determination (2026-08-05)

**Status: DETERMINATION, NOT A CLOSURE.** This document records the honest
result of investigating whether the ProteinProcessingII H12
`SENTINEL_FAIL` (`docs/phase_f/l2_2_design_a/evidence_index.json`, the
`ProteinProcessingII` row's `reasons`) can be legitimately resolved to
`H12_CONFIRMED` right now. **It cannot.** The sentinel remains, correctly,
non-green. This document does not edit `evidence_index.json`,
`scripts/l22_evidence/h12.py`'s `decide_verdict`/`REQUIRED_BRANCHES`,
`scripts/l22_evidence/verdict.py`, or `docs/phase_f/l2_2_design_a/
PROCESS_CATALOG.yaml` — all four remain exactly as they were. It adds only
regression tests (`tests/scripts/test_h12_protii_sentinel_determination.py`)
that mechanically pin the findings below.

## 1. What was inventoried before any new execution (per DELIBERATE_ACTION_PREFIX_v2 Beat 2)

Read, in order, before writing anything: `data/karr_vendored_source/
ProteinProcessingII.m` (`evolveState`, lines 348-446), `data/karr_vendored_source/
RandStream.m` (the `mnrnd`/`stochasticRound` methods), `scripts/matlab/mnrnd.m`
(the repaired Octave/MATLAB-compatible manual shim), and the full existing H12
trail for this process: `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_h12.json`
(primary, gating artifact), `docs/phase_f/l2_2_design_a/h12/perturbation/
ProteinProcessingII_h12_perturbation.json` (Scenario A, Octave, non-gating),
`docs/phase_f/l2_2_design_a/h12/perturbation/
ProteinProcessingII_h12_scenario_b_perturbation_canary.json` (Scenario B
canary, genuine MATLAB, non-gating), `docs/phase_f/l2_2_design_a/h12/perturbation/
PROTEINPROCESSINGII_SCENARIO_B_PROPOSAL.md`, `docs/phase_f/l2_2_design_a/h12/
CONDITION_GATED_TAXONOMY_PROPOSAL.md`, and `docs/phase_f/l2_2_design_a/h12/
perturbation/PERTURBATION_SPEC.json`. No new worktree/canary/trace was created;
no rerun of any 50-seed/20-seed evidence occurred. All numbers below are either
recomputed from files already on disk (hash checks, `decide_verdict`
re-derivation) or read verbatim from already-committed, hash-bound artifacts.

## 2. Reproducing the current sentinel derivation (mechanical, not narrated)

Recomputed directly against the on-disk files (see the new test file for the
exact assertions):

- `sha256_lf_normalized(scripts/l22_evidence/h12.py)` ==
  `aee4b9b89219284c9cd570d4208f39e95a89d657f3604c683a9908fdf883fd10` ==
  the artifact's own `predictor_source_sha256_lf_normalized`. **Fresh, not stale.**
- `sha256_lf_normalized(data/karr_vendored_source/ProteinProcessingII.m)` ==
  `2082bd39cf1e0dfba52de7ddf33a5690cf6368ff8f4eca7eaa457eee4d46e0ca` ==
  the artifact's `karr_source_citation.vendored_sha256_lf_normalized`. **Fresh.**
- `sha256(data/karr_fixtures/per_process/ProteinProcessingII_flat.mat)` ==
  `a386207b68bc7d306b8385a0a0aa34ea28bc68d2af0f1530da113f80808699af` ==
  the artifact's `fixture_sha256`. **Fresh.**
- Feeding the artifact's own recorded `nontrivial_sample_count=560`,
  `exact_match_count=560`, `exact_match_rate=1.0`, `trivial_mismatch_count=0`,
  `branches_confirmed=["passthrough_fires","peptidase_fires"]` back through
  the pure `h12.decide_verdict` function (independent of any oracle/fixture
  I/O) reproduces the **exact same** verdict string (`H12_OBSERVED_REGIME`)
  and the **exact same** `verdict_reason` string, byte for byte, as what is
  stored in the artifact.
- `h12.validate_h12_support(payload, expected_process="ProteinProcessingII")`
  against the real on-disk artifact returns (not `None`):
  `"h12 artifact verdict != H12_CONFIRMED (got 'H12_OBSERVED_REGIME')"` —
  i.e. the gate mechanically, correctly rejects this row today, exactly
  matching `evidence_index.json`'s recorded `SENTINEL_FAIL` reason for the
  `ProteinProcessingII` row.
- The remaining large 50-seed oracle trace (`data/m1_sources/karr_native/
  per_process_traces_v2/ProteinProcessingII_100ticks.mat` and 49 sibling
  per-seed directories) is **not present in this worktree or the main
  checkout** (only `per_process_traces_v2` (seed 0) and
  `per_process_traces_v2_s001` exist locally) — a full from-scratch
  `h12.run_h12("ProteinProcessingII", 50, 20)` re-execution is not possible
  in this environment. This is exactly why the hash-pinning design in
  `h12.py`/`validate_h12_support` exists: freshness is verified via hash
  equality against the committed predictor/fixture/Karr-source, not by
  re-running the full oracle sweep every time. No seed count was inflated,
  relabeled, or assumed to make up for this; the recomputation above is
  restricted to what is honestly re-derivable from files present here.

**Conclusion of this section:** the sentinel is not stale, not a
transcription error, and not a hand-edited artifact — it is the correct,
reproducible, mechanically-derived output of the current code against the
current fixture/oracle-manifest evidence.

## 3. Why `transferase_fires` cannot appear in the natural 50-seed×20-tick trace

`predict_protein_processing_ii` (`scripts/l22_evidence/h12.py:645-733`) tags
`transferase_fires` only inside the `regime_valid=True` (closed-form,
fully-saturating) branch, when `transferase_demand > 0`. Under the accepted
Karr 50-seed/20-tick oracle trace, 0/1000 (seed, tick) samples have
`transferase_demand > 0` (`docs/phase_f/l2_2_design_a/h12/perturbation/
PROTEINPROCESSINGII_SCENARIO_B_PROPOSAL.md` §1). This is a fact about the
biological operating point of the trace (lipoprotein monomers are essentially
never in the unprocessed pool during this window), not a predictor defect and
not seed-sensitive — no amount of *additional* natural-trace seeds/ticks
within the catalog's own N=50/M=20 domain changes this, and the catalog's
N/M are pinned (`PROCESS_CATALOG.yaml:427-440`; extending M_ticks or N_seeds
beyond what the catalog specifies would itself be an unauthorized threshold/
scope change, not a fix). `H12_OBSERVED_REGIME` is therefore not a bug to
patch; it is the honest, permanent ceiling for this process under the
gating artifact's natural-trace-only evidence model — the same mechanism
that permanently caps `MacromolecularComplexation`'s `network_ge2_fires`
(`h12.py:137-141`; see also `tests/scripts/test_h12_artifact.py::
test_decide_verdict_missing_required_branch_is_observed_regime_not_confirmed`).

## 4. Does the repaired manual `mnrnd` shim remove the Statistics Toolbox blocker? **No — and it must not be used to.**

Two entirely separate `mnrnd`-adjacent artifacts exist in this repo; conflating
them was the central risk this investigation was asked to rule out:

1. **`scripts/matlab/mnrnd.m`** — the "repaired manual mnrnd compatibility
   shim" named in the task. It exists solely for `scripts/l2_event/
   launcher.py`'s Octave-based per-process **trace-extraction** pipeline
   (`extract_per_process_traces_v2.m`), which unconditionally
   `addpath('scripts/matlab')`s it for *every* simulated tick of *every*
   process (its own docstring, lines 1-14) because Octave has no Statistics
   Toolbox at all. It was fixed for the Canary D duplicate-bin-edge crash
   (`8470977`/`58b0878`) and is covered by
   `tests/scripts/test_mnrnd_shim.py`'s functional regression suite.
2. **Karr's real `edu.stanford.covert.util.RandStream.mnrnd`**
   (`data/karr_vendored_source/RandStream.m:127-137`) — a thin wrapper that
   makes the instance stream MATLAB's default stream and then calls the
   **Statistics Toolbox's own global `mnrnd` function**, i.e. `evolveState`'s
   stochastic rationing branch's real semantics ARE the Statistics Toolbox's
   implementation; there is no Karr-specific multinomial algorithm to fall
   back to.

`scripts/matlab_h12_perturbation/run_ppii_scenario_b_matlab.m` (line 82) and
`probe_matlab_environment.m` (line 88) each `addpath` **only** the resolved
`--wholecell-src-root`/`OPENCELL_WHOLECELL_SRC_ROOT` (the real WholeCell
source tree containing the real `RandStream.m`) — **neither ever
`addpath`s `scripts/matlab`**, and `scripts/l22_evidence/h12_perturbation.py`
contains zero references to `scripts/matlab` or `mnrnd.m` anywhere (grepped;
0 matches). The repaired shim is therefore **not currently wired** into the
Scenario B genuine-MATLAB pathway at all, and the live probe recorded on
this machine (`ProteinProcessingII_h12_scenario_b_perturbation_canary.json`
→ `run_manifest.statistics_toolbox_installed: false`) is a real, honest
report of a real gap: this MATLAB installation is licensed for the
Statistics Toolbox but does not have it installed, so `mnrnd` genuinely
cannot be called at all in this environment; `run_ppii_scenario_b_matlab.m`
(asserted by `tests/scripts/test_h12_perturbation.py::
test_run_ppii_scenario_b_matlab_gates_statistics_toolbox_on_full_mode_only`)
hard-blocks `mode='full'` on exactly this condition.

**Could the repaired shim be wired in to unblock full mode?** Mechanically,
yes — nothing stops a future edit from adding
`addpath('scripts/matlab')` before the WholeCell root in the Scenario B
driver. **This must never be done, and doing so would not "remove the
blocker without changing Karr semantics"; it would change Karr semantics**:

- Real Statistics Toolbox `mnrnd` uses a sequential conditional-binomial
  sampling algorithm (drawing one binomial variate per category from the
  running remainder), consuming a data-dependent, category-count-sized
  sequence of uniform draws from the stream.
- `scripts/matlab/mnrnd.m` uses per-trial categorical (inverse-CDF/bin-edge)
  sampling, drawing exactly `n` uniforms from the stream (a property
  explicitly regression-tested by `test_mnrnd_shim.py::
  test_consumes_exactly_n_uniforms_from_active_stream`).
- Both are legitimate ways to produce a mathematically-correct multinomial
  sample from *some* uniform stream, but they consume the stream's random
  bits in structurally different amounts and orders. Substituting one for
  the other under a fixed `RandStream` seed does not reproduce Karr's real
  per-seed realization — it produces *a* valid multinomial draw, not *the*
  draw Karr's own vendored algorithm would have produced. This is exactly
  the pre-registered forbidden pattern this task's pre-mortem named: "missing
  toolbox is bypassed with a distributionally-different RNG." It is also
  structurally identical to the reason Opus5 rejected the Turn 2a Octave-stub
  design for this exact same Scenario B (`PROTEINPROCESSINGII_SCENARIO_B_
  PROPOSAL.md` §2a) — a non-Karr stochastic implementation cannot serve as
  evidence for Karr's own dormant branch, no matter how well-tested the stub
  itself is in isolation.

**Determination:** the manual shim does not, and must not be made to,
remove the Statistics Toolbox blocker for Scenario B full-mode execution.
The blocker is genuine and stays honestly documented as
`statistics_toolbox_installed: false` in the canary artifact.
`tests/scripts/test_h12_protii_sentinel_determination.py` adds two permanent,
structurally-enforced regression guards (not substring/literal-string bans,
which would only catch the specific spellings anticipated at the time they
were written) so a future edit cannot silently reintroduce this bypass:

- **Addpath-argument guard** (`_assert_addpath_only_resolves_to_wholecell_src`,
  exercised against both `run_ppii_scenario_b_matlab.m` and
  `probe_matlab_environment.m`): first rejects, file-wide, ANY MATLAB
  *command-syntax* `addpath` invocation (e.g. `addpath ../matlab`,
  `addpath '../matlab'`, or even `addpath wholecell_src` written without
  parentheses) — command syntax never dereferences a variable, so a
  bareword argument is always taken as a literal directory name, not the
  variable's value, which makes every command-form `addpath` unauthorized
  regardless of what follows it. It then parses every remaining
  `addpath(...)` and `fullfile(...)` call's actual arguments via
  paren/quote-balanced scanning (not a single regex over raw text), and
  requires (a) the file's ONLY *functional-form* `addpath(...)` call is the
  bare identifier form `addpath(wholecell_src)`, (b) every assignment to
  the bare name `wholecell_src` has a right-hand side of exactly
  `getenv('PPII_WHOLECELL_SRC_ROOT')`, and (c) no `fullfile(...)` call
  anywhere in the file contains a contiguous `('scripts','matlab')` or
  `('..','matlab')` literal-argument pair. This structurally rejects
  `addpath('../matlab')`, `addpath(fullfile(repo_root,'scripts','matlab'))`,
  `addpath(fullfile(this_dir,'..','matlab'))`, a `wholecell_src` variable
  quietly redefined to a shim-directory path, and any command-syntax
  `addpath` bypass — not just the literal `"scripts/matlab'"` substring a
  naive check would look for. The guard's own adversarial probe test
  (`test_addpath_structural_guard_rejects_every_named_bypass_shape`) proves
  it actually rejects each of these shapes (four functional-form and four
  command-form variants) on synthetic input, not only the two real files
  (which could otherwise pass vacuously if the checker were too
  permissive).
- **Equivalence-claim guard** (`_assert_no_unsupported_equivalence_claim`,
  exercised against `scripts/matlab/mnrnd.m`'s docstring): permits truthful,
  negated disclaimers such as "NOT bit-identical to the Statistics
  Toolbox's mnrnd" (which this document's own analysis above establishes
  is true — the two algorithms consume the RNG stream's uniforms in
  different amounts/orders), but fails on any *unnegated* claim that the
  shim IS bit-identical/equivalent/identical to the real Statistics Toolbox
  mnrnd. It also ignores unrelated, true uses of "identical" that are not
  about Statistics Toolbox equivalence (e.g. the shim's own "pure language
  core, identical in MATLAB and Octave" remark about its bin-counting
  loop). The mention check recognizes both the legacy short name
  "Statistics Toolbox" and the real, current MATLAB product name
  "Statistics and Machine Learning Toolbox" (renamed in R2015b). The
  negation search is **clause-aware, not a fixed-width character window**:
  it only credits a negation word found after the nearest preceding clause
  boundary (sentence-final punctuation, a comma, or a contrastive/
  subordinating conjunction such as "but"/"however"/"although"/"though"),
  so a negation word from an earlier, grammatically unrelated clause (e.g.
  "Although this is not a perfect implementation, this output is
  bit-identical to the Statistics Toolbox's mnrnd.") can no longer
  incorrectly excuse a later, actually-unnegated equivalence claim in a
  different clause. Its own adversarial probe test
  (`test_equivalence_claim_guard_permits_truthful_disclaimers_but_rejects_false_claims`)
  proves both directions on synthetic input, including the clause-boundary
  false-negative shapes above and the "Statistics and Machine Learning
  Toolbox" phrasing.

## 5. Even a clean full-mode Scenario B run would not close the sentinel

Independent of §4's blocker: Scenario B's five scarcity states are all
constructed with `regime_valid=False` (peptidase/transferase capacity, water,
or PG160 deliberately made insufficient — that is the entire point of a
"scarcity matrix"). `predict_protein_processing_ii` only emits `branch_tags`
(including `transferase_fires`) inside the `regime_valid=True` branch,
per §3. So Scenario B, even executed perfectly clean across all 5 states ×
50 seeds with zero invariant violations, targets the **mnrnd-rationing
sub-path**, not the **closed-form `transferase_fires` branch tag** that
`REQUIRED_BRANCHES["ProteinProcessingII"]` actually requires — a fact the
proposal document itself states plainly (§8: "It cannot and does not attempt
to close or remove the natural regime's `missing_required_branches`
finding"). The process that *does* target the right branch tag, correctly,
is Scenario A (Octave, `regime_valid=True`, provably RNG-invariant by
construction) — already executed, already `H12_PERTURBATION_CONFIRMED`,
already hash-bound — but it is explicitly `NON_GATING` pending "a reviewer
decision... to fold this into the primary H12 artifact/catalog"
(`ProteinProcessingII_h12_perturbation.json.gating`).

## 6. Why that fold-in is not performed by this task

Folding Scenario A's confirmed-but-non-gating evidence into the primary,
gating `ProteinProcessingII_h12.json` artifact is exactly the class of
change `docs/phase_f/l2_2_design_a/h12/CONDITION_GATED_TAXONOMY_PROPOSAL.md`
describes and explicitly marks `Status: PROPOSAL ONLY — NOT IMPLEMENTED ON
THIS BRANCH`, requiring its own separately-authorized future PR (§3.1: "an
explicit policy decision", §3.2: acceptance criteria not yet met). It would
require either (a) relaxing/redefining what counts as `REQUIRED_BRANCHES`
coverage for a gating artifact (a threshold/acceptance-criteria change — this
task's hard rules forbid threshold relaxation), or (b) a new, carefully
hash-bound schema extension to `h12.py`/`validate_h12_support` that mixes a
catalog-N/M-pinned natural-trace domain with a structurally-different
perturbed-state domain without breaking the existing anti-cheat invariants
(catalog N/M coverage floor, `oracle_manifest_cross_check` completeness,
etc.) — a nontrivial, security-sensitive design change that the repo's own
process reserves for a dedicated, reviewed proposal, not a routine
same-session fix. Attempting it here, under time pressure, is exactly how
the "stored catalog comment overrides metrics" and "two outcomes are treated
as proof of closed form" pre-mortem failure modes actually happen in
practice. The honest choice is to leave the sentinel red and document
precisely why.

## 7. Precise, current blocker (for the next authorized attempt)

For `ProteinProcessingII` H12 to legitimately reach `H12_CONFIRMED`, ONE of
the following must happen, each requiring authorization beyond this task's
scope:

1. `docs/phase_f/l2_2_design_a/h12/CONDITION_GATED_TAXONOMY_PROPOSAL.md` is
   formally accepted and implemented (its own §3.1/§3.2), AND `verdict.py`'s
   `_has_valid_h12_support` gate is updated to accept the resulting
   `H12_CONDITION_GATED` (or equivalent) status for
   `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` demotions — a deliberate,
   reviewed policy change, not a bug fix.
2. Some *other*, still-undiscovered natural Karr trace/condition exists in
   which `transferase_demand > 0` **and** `regime_valid=True` simultaneously
   — i.e. a state where lipoprotein monomers are genuinely unprocessed *and*
   enzyme/metabolite capacity still suffices without rationing. No such
   natural sample exists in the current catalog-pinned 50×20 domain (§3).
3. A licensed, genuinely-installed Statistics Toolbox becomes available on a
   MATLAB host so Scenario B's full mode can execute — but per §5 this would
   still not close the natural-regime gap on its own; it only unblocks a
   *different* (condition-gated) evidence tier.

None of (1)-(3) is available in this session. `SENTINEL_FAIL` remains the
correct, non-green mechanical verdict for the `ProteinProcessingII` row in
`evidence_index.json`, unchanged.

## 8. Hash-binding: what this determination's §4 conclusion is actually pinned to (final-round correction)

**This conclusion applies to the exact audited file contents recorded
below, not to "whatever these files currently say."** Any future edit to
any of the five files listed here — including a purely cosmetic reformat,
a comment change, or a whitespace-only reflow, not only a deliberate
bypass — invalidates §4's "never wired in" conclusion and requires a
deliberate re-audit before it can be trusted again. This is a strategic
correction from the prior two rounds' approach (regex-based structural/
semantic guards), not an abandonment of them: those guards are retained,
but only as **defense-in-depth with an explicitly enumerated, non-universal
scope** — they were never a complete parser for arbitrary future MATLAB
syntax or prose, and this section stops implying otherwise.

**The actual fail-closed mechanism is a hash pin**, not the regex guards.
`tests/scripts/test_h12_protii_sentinel_determination.py::
test_audited_scenario_b_wiring_files_match_hash_pinned_at_audit_time`
recomputes each file's LF-normalized SHA-256
(`h12._sha256_lf_normalized`, the same git-blob-consistent hash used
elsewhere in this determination) and asserts it matches the value pinned
during this audit:

| File | `sha256_lf_normalized` (pinned 2026-08-05) |
| --- | --- |
| `scripts/l22_evidence/h12_perturbation.py` | `4cf991ec902b6590875c7eb9bb68cfff053e7afb9833093e6e16b5a2c908d272` |
| `scripts/matlab_h12_perturbation/run_ppii_scenario_b_matlab.m` | `3a8a76ea6c4e892ba16ff8119ccce802c6ba64cf1d106c606048517252d9b535` |
| `scripts/matlab_h12_perturbation/probe_matlab_environment.m` | `ee8d033188cde8aa559d8ebaa8ce810bae41512bce2d7870c6f4a2efdc4228e6` |
| `scripts/matlab_h12_perturbation/evolveState_ppii_matlab.m` | `d3080131832d99a84c835271ea45d238f45d991ed65f810de5c15f226669e6d0` |
| `scripts/matlab/mnrnd.m` | `819218f9c4db0e9b24606e6bd9d34dd31600bfbdc764c8c46e17bf72da391e67` |

(`evolveState_ppii_matlab.m` is included as the sibling Scenario B driver
`run_ppii_scenario_b_matlab.m` directly invokes per tick
(`this = evolveState_ppii_matlab(this);`) and was read during this
investigation, per `tests/scripts/test_h12_perturbation_source_binding.py`'s
`MATLAB_BINDINGS`.)

If any of these files' hash ever changes, the test above fails — not
because the checker infers a bypass occurred, but because it **cannot tell
the difference** between a bypass and a harmless edit, and fails closed
either way. That failure is the intended, mandatory prompt: re-audit the
addpath/equivalence-claim contract of the changed file by hand against its
new contents before updating the pinned hash, rather than trusting the
structural/semantic guards to have caught every possible change.

**Why the regex guards alone are not sufficient (enumerated, not
exhaustive):** `tests/scripts/test_h12_protii_sentinel_determination.py`
now also includes explicit "documented scope gap" tests
(`test_addpath_guard_documented_scope_gaps_are_not_detected_rely_on_hash_
binding`, `test_equivalence_claim_guard_documented_scope_gaps_are_not_
detected_rely_on_hash_binding`) that prove — rather than merely assert —
concrete bypass shapes the guards do **not** catch:

- The addpath guard only recognizes `addpath(...)` (functional and
  command form) and `fullfile(...)` calls, plus a whole-file literal-text
  scan for `scripts/matlab` / `../matlab`. It does not recognize MATLAB's
  separate `path(...)` search-path function, a path string built via
  bracket concatenation (`['scripts' filesep 'matlab']`) instead of
  `fullfile(...)`/a literal, or a `setenv('PPII_WHOLECELL_SRC_ROOT', ...)`
  call that redirects the environment variable's runtime value without
  changing the literal `getenv(...)` text the assignment-check inspects.
- The equivalence-claim guard's clause-boundary set is exactly
  `. ! ? ; ,` plus "but"/"however"/"although"/"yet"/"though". It does not
  treat a colon (`:`), an em-dash/double-hyphen (`--`), or conjunctions
  such as "and"/"while" as clause boundaries, so a negation separated from
  an actually-unnegated equivalence claim only by one of these forms is
  not detected.

These gaps are intentionally **not** patched this round — extending the
regex further would only ever cover the specific shapes anticipated today,
repeating the exact "complete parser" trap this round is correcting. They
are covered by the hash-binding pin above instead: introducing any of
these bypass shapes into one of the five audited files changes that
file's hash and fails the pin, exactly as any other edit would.

**Provenance correction:** the round-2 fix's provenance log entry
(`event_id sha256:6dc305d44a02aa1688f8803b1a99ea006511eb19c6894ba1d84bc6d602bc00ed`)
recorded an incomplete `linked_commits` chain — it omitted `4e4f966`, the
very fix commit its `task_summary`/`output_summary` describe. Per the
append-only provenance schema, this is corrected with a **new, superseding
entry** (`--supersedes sha256:6dc305d...`), not an amendment to the
existing JSONL line or git history.
