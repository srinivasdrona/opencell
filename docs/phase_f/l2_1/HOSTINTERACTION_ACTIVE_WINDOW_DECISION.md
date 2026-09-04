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
scheduler used by `extract_per_process_traces_v2.m` (`tmp/probe_host_interaction_canary.m`,
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

Ran `tmp/l21_host_interaction_fixed_active_window.m`:
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
