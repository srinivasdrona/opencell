# HostInteraction L2.1 Active Window — Decision Record

**Date:** 2026-09-04
**Status:** RESOLVED — `EXISTING_WINDOW_PASS` (was `MISSING_ACTIVE_EXTRACTION`)
**Branch:** `agent/l21-host-active-fix-20260904`

## 1. The question

HostInteraction was the sole `MISSING_ACTIVE_EXTRACTION` row in
`docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`. A prior seed-0 anchor
search for `host.isBacteriumAdherent` false→true ran 50,000 ticks
(`E:\opencell-worktrees\genuine-l21-active\tmp\run_host_retry.out.log`) and
found no transition. The mandate for this task was explicit: do not raise
`max_search_ticks` further, do not blindly launch more seeds, and do not
fabricate an event.

## 2. Reading the actual source first

`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/HostInteraction.m`
(`evolveState`, lines ~266-303) is a **pure, memoryless boolean cascade**,
recomputed fresh every tick from the CURRENT (not fractional) copy numbers
of 14 enzyme monomers/complexes in `this.enzymes`:

```matlab
h.isBacteriumAdherent = all(this.enzymes(this.enzymeIndexs_terminalOrganelle)) && ...
                        all(this.enzymes(this.enzymeIndexs_adhesin));
h.isTLRActivated(h.tlrIndexs_1) = h.isBacteriumAdherent && any(this.enzymes(this.enzymeIndexs_tlr12Ligand));
h.isTLRActivated(h.tlrIndexs_2) = h.isBacteriumAdherent && (any(tlr12Ligand) || any(tlr26Ligand));
h.isTLRActivated(h.tlrIndexs_6) = h.isBacteriumAdherent && any(this.enzymes(this.enzymeIndexs_tlr26Ligand));
h.isNFkBActivated = (isTLRActivated(2) && isTLRActivated(1)) || (isTLRActivated(2) && isTLRActivated(6));
h.isInflammatoryResponseActivated = isNFkBActivated || (isBacteriumAdherent && any(this.enzymes(this.enzymeIndexs_antigen)));
```

There is **no RNG anywhere in this process** (confirmed against
`PROCESS_CATALOG.yaml`'s pre-existing `bucket: DETERMINISTIC`,
`rationale_M: "no RNG"` — correct, unchanged by this work). `initializeState`
just calls `evolveState()` once, using whatever enzyme copy numbers the
broader `Simulation.initializeState()` pipeline already established.

`Host.tlrIndexs_1=1`, `tlrIndexs_2=2`, `tlrIndexs_6=3` (see
`+state/Host.m`), so the 3-element `isTLRActivated` array flattens to
`isTLRActivated_1` (TLR1), `_2` (TLR2), `_3` (TLR6).

## 3. Inventory before extraction

- `data/karr_fixtures/per_process/HostInteraction_flat.mat` (a representative
  fixture snapshot, not necessarily tick 0): every one of the 8
  `terminalOrganelle` / 4 `adhesin` enzyme WIDs already carried a nonzero
  copy number (11-33).
- The existing standard trace
  (`data/m1_sources/karr_native/per_process_traces_v2/HostInteraction_100ticks.mat`)
  is genuinely inactive, but only because of how the per-process trace
  extractor's `merge_event_observables` enrichment is gated (see §4) — it
  never carried the host boolean surface at all in `window_contract='fixed'`
  mode, so there was nothing to classify as active in the first place.
- No other worktree/fixture had a genuine host-conditioned active window on
  disk (per `l21_active_window_audit.py --process HostInteraction`
  scan, both candidates classified inactive pre-fix).

## 4. Smallest empirical canary first

Before touching any extraction or process code, ran the smallest possible
canary against the SAME genuine fitted `Simulation` + allocator-correct
scheduler used by `extract_per_process_traces_v2.m` (`scripts/matlab/probe_host_interaction_canary.m`,
seed=0, no perturbation): print `host.isBacteriumAdherent` /
`isTLRActivated` / `isNFkBActivated` / `isInflammatoryResponseActivated`
plus the raw `enzymes` values for the 5 relevant index sets at ticks
0 (pre-evolve), 1, 2, 5, 10, 20, 50, 100.

**Result:** ALL FOUR Host booleans are **TRUE from tick 0/1 onward** and
remain true through tick 100. Every required enzyme WID already has a
nonzero copy number (e.g. `enzymes(terminalOrganelle) = [31 31 17 33 26 19
24 11]`) because Karr's fitted seed-0 initial condition already carries
these moderate/abundant expression levels — the model does not "cold
start" translation from zero.

**Conclusion:** `host.isBacteriumAdherent` (and everything it gates) is the
correct, real, source-faithful signal — but it is a LEVEL (state-truth)
signal that is already active before the observation window begins, not a
discrete EVENT with an observable onset. A false→true SEARCH can
structurally never terminate for a signal that is already true before the
search starts. The 50,000-tick honest failure documented in
`run_host_retry.out.log` is the CORRECT negative result for that search
strategy, not evidence of a bug or of non-reachability. This is the
"natural unperturbed activity is reachable" branch of the task mandate —
no perturbation/stimulus is needed or justified.

## 5. Extraction: fixed window, not anchor search

Extended `scripts/matlab/extract_per_process_traces_v2.m` with an opt-in
`anchor_opts.capture_signal_container` flag: when set, a plain
`window_contract='fixed'` capture ALSO calls `merge_event_observables` at
both tap points (previously only `window_contract='anchor'` did this),
merging in the real per-tick host boolean surface without performing any
anchor SEARCH. `merge_event_observables`'s existing `boolean_transition` +
`host` branch already flattened `isTLRActivated` into
`isTLRActivated_1/2/3` alongside `isBacteriumAdherent`/`isNFkBActivated`/
`isInflammatoryResponseActivated` — no changes needed there.

Ran `scripts/matlab/extract_host_interaction_active_window.m` (part 1, positive control):
`window_contract='fixed'`, `tick_offset=0`, `n_ticks=100`, `seed=0`,
`signal_kind='boolean_transition'`, `signal_property='host'`,
`signal_field='isBacteriumAdherent'`, `capture_signal_container=true`.
Output: `data/m1_sources/karr_native/per_process_traces_v2_event_s000/HostInteraction_100ticks.mat`
(sha256 `5eaa308f2b7fe4dbd5e96c698cd7c5c978cd1d65bc28e680078346e76d4507d2`,
gitignored per existing `per_process_traces_v2_event_s*/` pattern;
reproducible from the committed driver script). Confirmed via direct HDF5
read: all 6 host booleans are `1` (true) for all 100 ticks.

No additional seeds were launched — a single genuine seed-0 window was
sufficient to demonstrate real, non-degenerate activity across the entire
window, and the task mandate explicitly discourages blindly launching more
seeds once one genuine result is in hand.

## 6. The literal source gap (this was the real bug)

`opencell/vivarium/karr_host_interaction.py` (pre-fix, "Karr-light v1") did
**not** implement the boolean cascade at all. It computed a continuous
"adhesion capability" fraction from `protein.counts / reference_count`,
fed a stochastic Poisson bind/unbind aggregate-bond model, and never
modeled TLR/NF-kB/inflammatory response in any form
(`docs/phase_f/audits/HostInteraction_semantic_audit.md` HI-S4-01,
HI-S4-02, HI-S5-02: `CODE_DEVIATES`). `scripts/l21_active_window_audit.py`
had a hardcoded zero-stub for the TLR/NF-kB/inflammatory projections
(`_project_custom_observable`) and an explicit test locking that stub in
(`tests/scripts/test_l21_active_window_audit_host_custom_surfaces.py::
test_host_missing_signaling_surfaces_fail_closed_as_zero_vectors`) — i.e.
the gap was already known and fenced off pending this fix.

Rewrote `KarrHostInteractionProcess` as a literal port:
`all()`/`any()` nonzero-count semantics over the same 5 fixture index sets
(`enzymeIndexs_terminalOrganelle/adhesin/tlr12Ligand/tlr26Ligand/antigen`),
writing `cell.host_attached` / `host_tlr1_activated` / `host_tlr2_activated`
/ `host_tlr6_activated` / `host_nfkb_activated` /
`host_inflammatory_response_activated` (all `_updater: "set"`, emitted only
when changed from the incoming state). Removed the RNG/rate-constant/
Poisson machinery entirely (matches source: no RNG, no timestep
dependence). `substrates`/`enzymes`/`boundEnzymes` ports kept as
wired-conformance pass-throughs (HostInteraction never mutates them, in
either MATLAB or OC — Vacuous process, unchanged).

## 7. Closing the audit-layer gap

`scripts/l21_active_window_audit.py`'s generic "activity" heuristic
(`_trace_activity_detail`/`_scan_activity_without_context`) is a
before≠after MISMATCH check — correct for discrete pulse/event processes
(Cytokinesis, DNA repair), but structurally unable to detect a
constantly-true LEVEL signal (before==after==True on every tick, by
construction, once the process is active). Added a
`LEVEL_TRUTH_ACTIVITY_PROCESSES` special case (currently just
`HostInteraction`) whose activity predicate is "the after-value is
non-degenerately True", not "the value changed this tick". Also added
`CUSTOM_VECTOR_SURFACES["HostInteraction"]` entries for the 5 previously-
stubbed observables and removed the zero-stub from
`_project_custom_observable` so they route through the same generic
`("cell", <field>)` projection path as `isBacteriumAdherent`.

## 8. Verification (fail-closed)

- `bin\oc-py.cmd scripts/l21_active_window_audit.py --process HostInteraction`
  → `classification=EXISTING_WINDOW_PASS`,
  `bit_identity.pass_all_compared_ticks=true` across all 9 compared
  surfaces (substrates/enzymes/boundEnzymes pass-through + all 6 host
  booleans), `honest_replay.oc_active_on_karr_active_ticks=100/100`
  (was 0/0 pre-fix).
- `bin\oc-pytest.cmd tests/vivarium/test_karr_host_interaction_l2_replay.py`
  → both the standard L2a replay and the new event-window replay (now
  asserting bit-exact host-boolean equality per tick, not just the
  substrate/enzyme pass-through) pass.
- `bin\oc-pytest.cmd tests/vivarium/test_karr_host_interaction.py` → 11
  tests covering the literal cascade, vacuous-index-set MATLAB semantics,
  determinism (no RNG), and anti-cheat gating checks (TLR2-without-TLR1/
  TLR6 unreachability; NF-kB requires the TLR2 conjunct, not merely
  TLR1-or-TLR6).
- `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` HostInteraction row
  promoted to `EXISTING_WINDOW_PASS` with full `replay_evidence` (pytest
  nodeid) and `trace_window`/`source.sha256` binding.
  `l21_active_window_audit.verify_active_window_manifest_row` independently
  re-verifies this row end-to-end (re-runs the pytest nodeid, re-checks the
  source sha256) → `VERIFIED_EXISTING_WINDOW_PASS`.
- `data/schemas/per_process_wiring/HostInteraction.yaml` updated (line
  anchors + notes + `known_deviations`) and `scripts/l1b_verify_wiring.py
  --process HostInteraction` → PASS; full-suite run → 27/28 PASS (only
  pre-existing, unrelated `DNADamage` fails `check_oc_anchors_resolve`).
- `ruff check` on all changed Python files → clean.

## 9. L2.2 scope assessment

`PROCESS_CATALOG.yaml`'s `HostInteraction` row (`bucket: DETERMINISTIC`,
`in_scope_L2_2: false`, `rationale_M: "no RNG"`, `notes: "L2.1 sufficient."`)
is confirmed correct against the actual source — HostInteraction has no
stochastic primitive anywhere. No catalog correction was needed. This
closure did not generate or promote any L2.2 evidence.

## 10. What was NOT done

- No synthetic/fabricated adherence value was written anywhere; every
  emitted boolean is a real function of `protein.counts` at call time.
- No stimulus/perturbation was introduced — this was the "natural
  unperturbed activity is reachable" branch, not the condition-gated
  branch.
- No additional seeds beyond seed 0 were extracted (unnecessary once one
  genuine, fully-active window was in hand).
- Did not touch `TerminalOrganelleAssembly` (also flagged "Karr-light" in
  its own module docstring) — out of scope for this task.

## 11. Discriminating-conditions closure (2026-09-05+): after-the-fact results comparison

**Opus review (2026-09-05)** correctly rejected §5–§8 above as degenerate
evidence taken alone: a trace where all 6 host booleans are constant-True
for the entire window cannot, by construction, distinguish this literal
port from a hardcoded `return all-True` stub. Both would look bit-identical
against that one trace. This section records the after-the-fact result of
the 5 conditions preregistered in
`docs/phase_f/l2_1/HOSTINTERACTION_CONDITION_PREREGISTRATION.md`
(predictions were written and committed BEFORE the MATLAB extraction below
ran — see that document for the full derivation from `HostInteraction.m`'s
own formula). Per that document's own rule, this section is append-only:
any disagreement between a prediction and a genuine extraction result would
be recorded here as a dated correction to the *prediction*, never a silent
edit to the preregistered table.

**Result: every one of the 5 preregistered predictions matched its genuine
MATLAB extraction result bit-exact, with no corrections needed.**

| Condition | `host_attached` | `tlr1` | `tlr2` | `tlr6` | `nfkb` | `inflammatory` | Predicted == Actual |
|---|---|---|---|---|---|---|---|
| `NEG_ADHERENCE` | F | F | F | F | F | F | ✅ |
| `PARTIAL_ADHERENT_NO_SIGNAL` | T | F | F | F | F | F | ✅ |
| `TLR12_PATH` | T | T | T | F | T | T | ✅ |
| `TLR26_PATH` | T | F | T | T | T | T | ✅ |
| `ANTIGEN_ONLY` | T | F | F | F | F | T | ✅ |

Extraction mechanics:

- All 5 conditions were extracted by the SAME committed driver
  (`scripts/matlab/extract_host_interaction_active_window.m`, part 2),
  using a new `extraction_opts.per_process_enzyme_overrides.HostInteraction`
  surface added to `scripts/matlab/extract_per_process_traces_v2.m`. This
  surface overrides only the named enzyme WIDs on the process-local
  `this.enzymes` vector every tick, right after `copyFromState()`
  repopulates it from the global protein pool — it never writes back to
  the shared pool (no process this extractor covers ever
  `copyToState()`s `this.enzymes`) and never touches Karr's own `host`
  output booleans directly. Static proof of this wiring lives in
  `tests/scripts/test_extract_per_process_traces_v2_static.py::test_per_process_enzyme_overrides_wired_at_both_copyfromstate_sites`.
- Each condition is a 5-tick fixed window (`n_ticks=5`, `tick_offset=0`,
  seed 0, `window_contract='fixed'`, `capture_signal_container=true`),
  written to its own gitignored output directory
  (`data/m1_sources/karr_native/per_process_traces_v2_host_condition_<id>_s000/HostInteraction_5ticks.mat`)
  so the 5 short traces never collide with each other or the positive
  control. sha256 of each (verified against the tracked value in
  `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`'s
  `discriminating_conditions.conditions[].source.sha256`):
  - `NEG_ADHERENCE`: `d0003f61daad027d0b8635d9485ae62f20eb68874517c421067bf10693f89209`
  - `PARTIAL_ADHERENT_NO_SIGNAL`: `d589057ed07b3a1744560d7fae889eea547442f2c2d04c2db4795105101982b0`
  - `TLR12_PATH`: `9926f3f23a4aa221ca43d65433e01969390c6a370867aa6bedd159b43b32f891`
  - `TLR26_PATH`: `ea000bb2e9f1d08d533b7f41d86853082fe8af8fffac9512a3bfa8b4d57d6155`
  - `ANTIGEN_ONLY`: `5ad7872b8ed1c1bb2446e0e90007759b73314297ba265107cd6d03c6daa5b606`

New test coverage
(`tests/vivarium/test_karr_host_interaction_discriminating_conditions.py`,
15 tests, all passing):

1. `test_genuine_condition_matches_preregistered_prediction` — the genuine
   MATLAB extraction result equals the preregistered prediction, for all 5
   conditions (the table above).
2. `test_literal_port_reproduces_genuine_condition_bit_exact` — feeds the
   REAL extracted `this.enzymes` counts (`states_before/enzymes`, mapped
   through the fixture's `enzymeWholeCellModelIDs` ordering) into the
   literal OC port and asserts bit-exact agreement with the genuine MATLAB
   `states_after` result on **all 6** host booleans, for all 5 conditions.
3. `test_constant_true_stub_fails_every_negative_or_partial_condition` —
   the exact degenerate alternative Opus flagged (a stub that always
   returns True for all 6 fields) is constructed and asserted to diverge
   from the genuine result on at least one field, for every one of the 5
   conditions. This is the acceptance-rule check preregistered in
   `HOSTINTERACTION_CONDITION_PREREGISTRATION.md`: it structurally proves
   these 5 conditions have discriminating power that the positive-control
   trace alone lacked.

Two adjacent bugs were found and fixed while wiring these conditions into
`scripts/l21_active_window_audit.py` (the SAME script whose
`EXISTING_WINDOW_PASS` verdict for the positive-control window is quoted in
§8 above — these fixes did not change that verdict, but did change how
honestly it is reported and how robustly it would be computed for a
non-degenerate mixed-True/False window):

- **Under-seeded booleans (`_overlay_custom_observable`)**: the pre-tick
  state seed for HostInteraction only wrote `cell.host_attached` from the
  trace's genuine `states_before` value; the other 5 fields
  (`host_tlr1_activated`/`host_tlr2_activated`/`host_tlr6_activated`/
  `host_nfkb_activated`/`host_inflammatory_response_activated`) were left
  at the `ports_schema` default (`False`) regardless of the real trace
  value. This happened to be harmless for the all-True positive-control
  window and for these particular conditions (default `False` is a valid
  diff baseline whenever the emitted value is later merged with a
  from-scratch per-tick state, which is how this replay harness works),
  but it was dishonest and fragile. Fixed to seed all 6 fields via the
  existing `CUSTOM_VECTOR_SURFACES["HostInteraction"]` mapping.
- **Fabricated `before=0.0` (`_level_truth_activity_detail`)**: the
  level-truth activity detail hardcoded `before=0.0` for every detected
  active tick, regardless of the real trace value — for the
  positive-control window (constant-True from tick 0), the honest
  `states_before` value at every tick is also `1.0`, so reporting
  `before=0.0` fabricated a false "it just turned on" narrative for a
  signal that was never off. Fixed to read the real `states_before` value;
  `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`'s
  `trace_window.first_active_detail` was updated from
  `before=0.0/after=1.0` to the honest `before=1.0/after=1.0`.
- **OC-side "activity" heuristic (`_honest_replay`)**: once the seeding bug
  above was fixed, `oc_active_this_tick = _recursive_update_nontrivial(update)`
  (checking whether the emitted delta dict was non-empty) collapsed to
  `oc_active_ticks=0` for the entire positive-control window — correctly
  seeding the incoming state to match ground truth means a genuinely-active
  but already-correct level signal emits NO delta on any tick (nothing
  changed), so "was the update dict non-empty" structurally under-reports
  activity for this process family, mirroring the same structural gap the
  Karr-side heuristic already had (§7). Added an OC-side
  `LEVEL_TRUTH_ACTIVITY_PROCESSES` branch that projects the CURRENT
  (post-`next_update`) value of each declared custom-vector surface
  directly from state via `_project_custom_observable` and checks
  non-degenerate truth, symmetric with the Karr-side check. Re-verified
  `classification=EXISTING_WINDOW_PASS`,
  `honest_replay.oc_active_on_karr_active_ticks=100/100` after this fix
  (unchanged from §8, now computed honestly instead of by an accidental
  from-scratch-per-tick-state coincidence).

Also corrected in this pass (documentation-only, no behavior change):
`data/schemas/per_process_wiring/HostInteraction.yaml`'s `known_deviations`
now explicitly documents the free-enzyme-vs-protein-counts topology
question raised during this review: Karr's `this.enzymes` for
HostInteraction is never partitioned by the allocator (zero request), so
in Karr itself it already reflects the raw, unpartitioned global copy
number of these WIDs (confirmed by both the canary in §4 and the 5
conditions above); OC's `protein.counts` shared store is the same
architecture-wide convention every other zero-request process in this
codebase reads from (verified: 45+ topology bindings across
`karr_composite.py` all route `protein` to the single top-level
`("protein",)` store — there is no separate free-vs-bound partition
modeled anywhere in OC's shared state). Reading `protein.counts` for
HostInteraction's enzyme WIDs is therefore the correct match to Karr's
`this.enzymes`, not a topology deviation; the unused
`enzymes`/`boundEnzymes`/`substrates` ports on `KarrHostInteractionProcess`
are wiring-conformance placeholders only, deliberately left unwired in
`karr_composite.py`'s HostInteraction topology.

Final verification (all green, re-run after every fix above):

- `bin\oc-py.cmd scripts/l21_active_window_audit.py --process HostInteraction`
  → unchanged `classification=EXISTING_WINDOW_PASS`,
  `bit_identity.pass_all_compared_ticks=true`,
  `honest_replay.oc_active_on_karr_active_ticks=100/100`,
  `trace_window.first_active_detail` now honestly `before=1.0/after=1.0`.
- `bin\oc-pytest.cmd tests/vivarium/test_karr_host_interaction.py
  tests/vivarium/test_karr_host_interaction_l2_replay.py
  tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py
  tests/vivarium/test_karr_host_interaction_discriminating_conditions.py
  tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py
  tests/scripts/test_l21_active_window_audit_host_custom_surfaces.py
  tests/scripts/test_extract_per_process_traces_v2_static.py` → 58 passed,
  1 skipped (same pre-existing, unrelated allocator-oracle skip as §8).
- `scripts/l1b_verify_wiring.py --process HostInteraction` → PASS.
- `ruff check` on all changed Python files → clean.
- No fabricated/synthetic value anywhere; no additional seeds launched
  beyond the existing seed 0; all 5 conditions came from ONE MATLAB
  session run of the one committed driver script.

## 12. Second Opus rejection round (2026-09-08): containment, allowlist, verifier-depth, path-portability

A second Opus review pass on the §11 closure rejected 4 further blockers.
Each is closed below; this section is append-only, same as §11.

### 12.1 `per_process_enzyme_overrides` shared-state containment (real bug found)

`scripts/matlab/extract_per_process_traces_v2.m`'s prior comment claimed
the enzyme override was "never written back by copyToState() since no
process in this codebase's covered set writes to this.enzymes" — this was
**never verified against `Process.m` and was wrong**. Direct inspection of
`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m`'s
`copyToState()` shows it unconditionally writes `this.enzymes`/
`this.boundEnzymes` back into the shared global
`this.metabolite.counts`/`this.rna.counts`/`this.monomer.counts`/
`this.complex.counts` state whenever `this.enzymes` is non-empty. Since
HostInteraction's enzyme vector is non-empty (15 WIDs) and gets
overridden (e.g. `MG_218_MONOMER=0` for `NEG_ADHERENCE`), the prior code
would have written the OVERRIDDEN (zeroed) values back into the SHARED
global monomer/complex pool at every tick an override was active —
corrupting state visible to every other process evaluated later in the
same tick's random process order, and to every subsequent tick, for the
remainder of that extraction run. This was a genuine correctness bug, not
a documentation-only issue.

**Fix**: `apply_process_enzyme_overrides` now returns an
`override_snapshot` (the genuine pre-override `enzymes`/`boundEnzymes`
values, captured before any mutation) alongside the mutated `mod`. A new
`restore_process_enzyme_overrides(mod, override_snapshot)` puts those
genuine values back, called after
`evolveState()`/`calcResourceRequirements_Current()` and the
states_before/states_after snapshots, but **strictly BEFORE**
`copyToState()` — this ordering is the entire containment guarantee: the
override is visible only to the target's own per-tick computation, never
to `copyToState()`, never to any other process, never to a later tick.

A **runtime containment assertion** was added directly in
`evolve_state_with_tap`: when an override is active on the target process
this tick, it captures the genuine global `monomer.counts`/`complex.counts`
for the overridden WIDs (via `mod.monomer`/`mod.complex`, handle
references to the SAME shared state objects every process reads) both
immediately before `evolveState()` and immediately after `copyToState()`,
and raises a MATLAB error (`extract_per_process_traces_v2:
enzyme_override_leaked_to_global_state`) if they ever differ. This is not
a one-off test script — it runs automatically on every future extraction
that uses `per_process_enzyme_overrides`, for every tick, fail-closed.

**Genuine runtime proof**: all 6 HostInteraction traces (positive control
+ 5 conditions) were regenerated from scratch (old files deleted, not
just re-verified) via
`scripts/tools/run_matlab_slot.ps1 -MatlabCommand "... extract_host_interaction_active_window"`,
and the run completed with all 6 `[trace_v2] saved: ...` lines and zero
containment errors — proving the containment assertion is genuinely
exercised (not merely present in source) and holds for every condition.
Re-running `tests/vivarium/test_karr_host_interaction_discriminating_conditions.py`
and `tests/vivarium/test_karr_host_interaction_l2_replay.py` against the
regenerated traces reconfirmed all predictions/bit-exactness unchanged
(same values, new sha256s since MATLAB run timestamps differ).

Static proof (`tests/scripts/test_extract_per_process_traces_v2_static.py`):
`test_per_process_enzyme_overrides_wired_at_both_copyfromstate_sites` was
updated for the new `[mod, override_snapshot] = ...` signature and now
also asserts the pre-override snapshot is captured before the mutation
loop. A NEW test,
`test_per_process_enzyme_overrides_are_contained_before_copytostate`,
**requires** (not merely describes) that `restore_process_enzyme_overrides`
runs after `evolveState()` and strictly before `copyToState()`, and that
the runtime containment assertion exists and is gated correctly — this
inverts the prior test's stance from "documents why this is assumed safe"
to "fails if containment is ever removed."

### 12.2 `karr_host_interaction.py` removed from the L2 oracle-dependency legacy allowlist

`tests/vivarium/test_l2_no_oracle_dependency.py`'s `_ALLOWLIST` still
carried `karr_host_interaction.py` with a stale comment describing the
OLD "Karr-light v1" model's init-time oracle-rate-calibration pattern
(`_extract_trace_rates`). The CURRENT literal port
(`opencell/vivarium/karr_host_interaction.py`) reads only
`data/karr_fixtures/per_process/HostInteraction_flat.mat` (a non-oracle
input-spec fixture) via `scipy.io.loadmat`, never imports `h5py`, and
contains none of the banned oracle-path string tokens — the allowlist
entry was stale technical-debt bookkeeping left over from the prior
closure round, not an active violation. Removed the entry;
`test_l2_process_source_does_not_depend_on_replay_oracle[karr_host_interaction.py]`
now PASSes on its own merits (no longer needs the allowlist carve-out).
Confirmed via full-suite run that the only 2 remaining failures
(`karr_cytokinesis.py`, `karr_dna_damage.py` — both ALSO allowlisted but
apparently already fixed upstream without their allowlist entries being
removed) are pre-existing and reproduce identically on the pre-my-change
baseline (verified via `git stash`), unrelated to this change.

### 12.3 Manifest verifier depth: per-condition sha/value validation, all 3 nodeids, skip-as-failure

The §11 closure's `verify_active_window_manifest_row` only re-ran ONE
pytest nodeid (`replay_evidence.nodeid`) and trusted `returncode == 0`
alone to mean "passed" — but pytest's exit code is 0 for both a fully
PASSED run and a fully SKIPPED run, so a manifest row claiming
`EXISTING_WINDOW_PASS` whose backing test silently skips (e.g. a missing
gitignored artifact after a fresh clone) would have been wrongly reported
as re-verified. The `discriminating_conditions` block's own 5 conditions
and 3 nodeids were never independently checked at all.

**Fix**: `_run_pytest_nodeid` (new, replaces the old inline subprocess
call) parses the pytest summary line for `N skipped` and treats any
`N > 0` as `passed=False` regardless of return code. A new
`verify_discriminating_conditions(row, manifest_path, process_name)`:
validates every condition's `source.sha256` against the actual file bytes;
re-reads the genuine `states_after` host-boolean values directly from
each condition's trace and compares them field-by-field against the
manifest's recorded `predicted_and_actual` dict (catching a hand-typed
value that silently drifted from the real data); and re-runs **every**
nodeid in `replay_evidence.nodeids` (all 3, not just one) via
`_run_pytest_nodeid`. `verify_active_window_manifest_row` now calls this
whenever a row carries a `discriminating_conditions` block, folding its
result into the overall verification (fail-closed). For speed, a cheap
per-condition failure short-circuits before the (subprocess-per-nodeid)
reruns, since the overall result is already determined.

New test file
`tests/scripts/test_l21_host_interaction_discriminating_conditions_verifier.py`
(12 tests) proves this fail-closed under every scenario: tampered
condition sha256, tampered `predicted_and_actual` value, missing
condition source file, empty/missing nodeids list, missing
`discriminating_conditions` block entirely (must not silently claim the
extension ran), a genuinely SKIPPED pytest nodeid reported as
`passed=False` (built from a real throwaway skip-only test file, not
mocked), a genuinely PASSED nodeid still correctly reported as
`passed=True` (negative control against over-firing), and the
`skip_or_fail_missing_artifact` helper's fail-vs-skip branching for an
`EXISTING_WINDOW_PASS` process, a non-PASS process, and an unknown
process name.

**`tests/vivarium/l2_replay_common.py`** gained
`skip_or_fail_missing_artifact(path, process_name, description)`: skips
cleanly if the manifest carries no `EXISTING_WINDOW_PASS` claim for
`process_name`, but calls `pytest.fail()` (never `pytest.skip()`) when it
does — used by both `test_karr_host_interaction_l2_event_replay` (event-
window trace missing) and
`test_karr_host_interaction_discriminating_conditions.py`'s
`_load_condition` (condition trace missing). This closes "event/condition
tests fail (not skip) when row is EXISTING_WINDOW_PASS and artifacts
missing."

**Side effect (found, not introduced, and deliberately NOT fixed here,
out of scope)**: applying the corrected skip-vs-pass detection uniformly
(it lives in the SHARED `_rerun_manifest_replay_nodeid`/`_run_pytest_nodeid`
path used by every process's row, not something that could be scoped to
HostInteraction alone without being incoherent) exposes that
`ChromosomeSegregation`'s manifest row has the identical latent defect:
its `source.path` is an absolute path into a DIFFERENT worktree
(`E:\opencell-worktrees\fix-l21-chromseg-active\...`), and its replay
nodeid (`tests/vivarium/test_karr_chromosome_segregation_l2_replay.py::
test_karr_chromosome_segregation_l2_event_replay[event_seed_0]`) silently
SKIPS when run from THIS worktree (the trace isn't locally present here).
The OLD `returncode == 0` check reported this as re-verified; the fixed
code correctly reports `ACTIVE_WINDOW_MANIFEST_INVALID`. Verified via
`git stash` that this test PASSED (wrongly) on the pre-fix baseline and
FAILS (correctly) only after the fix — i.e. this is a genuine pre-existing
defect on a process this task does not own, newly exposed rather than
newly introduced. `tests/scripts/test_probe_l2_1_strict_rubric_active_
windows.py::test_current_tree_active_window_manifest_checkpoint
[ChromosomeSegregation]` will now fail in a full-suite run until that
row's evidence is made main-relative/locally-copied the same way
HostInteraction's was in §12.4 below; routed to the ChromosomeSegregation
track (`fix-l21-chromseg-active` worktree) rather than fixed here. The
`[HostInteraction]` parametrization of the same test passes cleanly.

### 12.4 Main-relative manifest paths + main-integrate local copies

The HostInteraction row's `source.path`/`repo_relative_hint` (main
trace_window) previously embedded this worktree's absolute path
(`/mnt/e/opencell-worktrees/fix-l21-host-active/...`) — this only
resolves correctly from THIS worktree, and would break once merged
elsewhere (exactly the defect found in ChromosomeSegregation's row
above). Changed to a repo-relative path
(`data/m1_sources/karr_native/per_process_traces_v2_event_s000/
HostInteraction_100ticks.mat`); `_resolve_manifest_source_path` already
resolves non-absolute paths against `_REPO_ROOT` of wherever the script
currently runs, so this now works identically from any worktree/checkout
as long as the data file is present in THAT worktree's local `data/`
tree. The 5 `discriminating_conditions.conditions[].source.path` entries
were already written repo-relative from the start.

All 6 traces (positive control + 5 conditions, freshly regenerated per
§12.1) were copied byte-for-byte into
`E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\...`
(verified identical sha256 via `Get-FileHash`) so the orchestrator's
integration worktree carries this evidence locally without needing a
fresh MATLAB run. These copies are gitignored data (not committed here or
in main-integrate), matching the existing convention for all other
per-process trace evidence in this repo.

Re-ran the full HostInteraction-focused suite after all fixes above:
`bin\oc-py.cmd scripts/l21_active_window_audit.py --process HostInteraction`
→ unchanged `EXISTING_WINDOW_PASS`; `verify_active_window_manifest_row`
→ `VERIFIED_EXISTING_WINDOW_PASS` with
`discriminating_conditions_verification.passed=true` (all 5 conditions'
sha256+values re-validated, all 3 nodeids re-run genuinely, zero skips);
`tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py::
test_current_tree_active_window_manifest_checkpoint[HostInteraction]` →
PASSED; full HostInteraction-focused pytest suite (74 tests across 7
files) → all passed except the same 1 pre-existing, unrelated
allocator-oracle skip (`test_l25_host_interaction_plus_terminal_organelle.py`,
documented as a genuine unresolved MATLAB tick-coverage limitation, not
something this change may fix) — zero skips attributable to this closure's
own evidence. `l1b_verify_wiring.py` → 27/28 (same pre-existing, unrelated
`DNADamage` failure). `ruff check` on all changed Python files → clean.

