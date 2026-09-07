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

