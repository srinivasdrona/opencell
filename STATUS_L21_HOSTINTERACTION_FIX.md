# STATUS — HostInteraction L2.1 Active Window Closure (2026-09-04, discriminating-conditions closure 2026-09-05+)

## Task
Close HostInteraction's `MISSING_ACTIVE_EXTRACTION` L2.1 gap (the sole
missing active window in `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`)
and any literal source gap discovered along the way, without fabricating an
event, without raising `max_search_ticks` blindly, and without launching
extra seeds speculatively. Follow-on round: close all Opus review blockers
against the initial positive-control-only closure (see "Discriminating
conditions round" below).

## Result: CLOSED. `EXISTING_WINDOW_PASS`.

Full decision record (read this first for the "why"):
`docs/phase_f/l2_1/HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md`.

## What was found
1. `HostInteraction.m`'s `evolveState()` is a pure, memoryless boolean
   cascade over 5 fixed enzyme index sets, no RNG, recomputed fresh every
   tick — never a discrete event.
2. A genuine seed-0 canary (`tmp/probe_host_interaction_canary.m`) proved
   `host.isBacteriumAdherent` (and TLR1/2/6, NF-kB, inflammatory response)
   is TRUE from tick 1 onward given Karr's fitted initial protein counts.
   The prior 50,000-tick false→true anchor search failure was the CORRECT,
   honest result for the wrong search strategy — not a bug, not a
   never-firing field.
3. The OC process (`opencell/vivarium/karr_host_interaction.py`) was a
   fabricated "Karr-light v1" stochastic model with zero relationship to
   the actual boolean cascade, and never modeled TLR/NF-kB/inflammatory
   response at all (this was the real literal-source-fidelity gap).

## What was changed
- `scripts/matlab/extract_per_process_traces_v2.m`: new opt-in
  `anchor_opts.capture_signal_container` flag lets a plain `fixed` window
  also carry the merged host boolean surface (previously only `anchor`
  mode did).
- Extracted a genuine fixed-window trace (seed 0, 100 ticks) at
  `data/m1_sources/karr_native/per_process_traces_v2_event_s000/HostInteraction_100ticks.mat`
  (gitignored; reproducible via `tmp/l21_host_interaction_fixed_active_window.m`).
- `opencell/vivarium/karr_host_interaction.py`: full rewrite as a literal
  port of the boolean cascade (adherence/TLR1/2/6/NF-kB/inflammatory
  response), reading raw `protein.counts`, zero RNG.
- `scripts/l21_active_window_audit.py`: added
  `LEVEL_TRUTH_ACTIVITY_PROCESSES` (HostInteraction) since the generic
  before≠after "activity" heuristic cannot detect a constantly-true level
  signal; wired the 5 previously-stubbed TLR/NF-kB/inflammatory
  observables through the real `CUSTOM_VECTOR_SURFACES` projection path
  (removed the zero-stub).
- `tests/vivarium/test_karr_host_interaction.py`: full rewrite (11 tests)
  for the literal cascade, including anti-cheat gating checks.
- `tests/vivarium/test_karr_host_interaction_l2_replay.py`: event-window
  test now asserts bit-exact host-boolean equality per tick (was
  substrate/enzyme-only).
- `tests/scripts/test_l21_active_window_audit_host_custom_surfaces.py`:
  replaced the "fail closed as zero" stub-locking test with a real
  cell-state projection test.
- `tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py`:
  `HostInteraction` expected verdict `MISSING_ACTIVE_EXTRACTION` →
  `GENUINE`.
- `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`: HostInteraction row
  promoted to `EXISTING_WINDOW_PASS` with full replay evidence; top-level
  counts updated (8 PASS / 3 CODE_GAP / 0 MISSING).
- `data/schemas/per_process_wiring/HostInteraction.yaml`: line anchors,
  status, and `known_deviations` updated to match the literal port.

## Verification (all green)
- `bin\oc-py.cmd scripts/l21_active_window_audit.py --process HostInteraction`
  → `EXISTING_WINDOW_PASS`, bit-identical, `honest_replay.oc_active_on_karr_active_ticks=100/100`.
- `bin\oc-pytest.cmd tests/vivarium/test_karr_host_interaction.py
  tests/vivarium/test_karr_host_interaction_l2_replay.py
  tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py` →
  13 passed, 1 skipped (pre-existing, unrelated allocator-oracle skip).
- `bin\oc-pytest.cmd tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py
  tests/scripts/test_l21_active_window_audit_host_custom_surfaces.py` →
  19 passed (full 11-process manifest checkpoint including HostInteraction).
- `bin\oc-py.cmd scripts/l1b_verify_wiring.py --process HostInteraction` →
  PASS. Full suite → 27/28 (only pre-existing, unrelated `DNADamage`
  fails `check_oc_anchors_resolve` — confirmed unaffected by this change).
- `ruff check` on all changed Python files → clean.
- Confirmed the 2 `test_karr_composite_chassis.py` M1+M2 failures
  (`test_m2_rna_stable_at_steady_state_under_composition`,
  `test_shared_substrates_accumulate_m2_consumption`) are PRE-EXISTING on
  baseline main (reproduced via `git stash`) and unrelated to HostInteraction.

## What was NOT done
- No fabricated/synthetic adherence value anywhere.
- No stimulus/perturbation introduced (natural activity was reachable).
- No additional seeds extracted beyond seed 0 (one genuine window
  sufficed).
- `TerminalOrganelleAssembly` (also "Karr-light" per its own docstring)
  was not touched — out of scope.
- No push/merge to main — commits are local to
  `agent/l21-host-active-fix-20260904`.

## Discriminating-conditions round (2026-09-05+, closes Opus review blockers)

Opus review (2026-09-05) correctly rejected the round above as degenerate
on its own: a trace where all 6 host booleans are constant-True cannot
distinguish this literal port from a hardcoded constant-True stub. Full
after-the-fact result and bug writeup:
`docs/phase_f/l2_1/HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md` section 11.
Preregistered predictions (written before extraction):
`docs/phase_f/l2_1/HOSTINTERACTION_CONDITION_PREREGISTRATION.md`.

### What was found and fixed
1. **Degenerate positive-only evidence** — closed by preregistering and
   extracting 5 genuine, source-legal, INPUT-SIDE enzyme-knockout
   conditions (`NEG_ADHERENCE`, `PARTIAL_ADHERENT_NO_SIGNAL`,
   `TLR12_PATH`, `TLR26_PATH`, `ANTIGEN_ONLY`) via a new
   `extraction_opts.per_process_enzyme_overrides.HostInteraction` surface
   on `scripts/matlab/extract_per_process_traces_v2.m`, driven by one
   committed script (`scripts/matlab/extract_host_interaction_active_window.m`,
   part 2). All 5 matched their preregistered predictions bit-exact; the
   literal OC port reproduces all 5 bit-exact on all 6 booleans; a
   constant-True stub fails every one of them on at least one field.
2. **Under-seeded booleans** — `scripts/l21_active_window_audit.py`'s
   `_overlay_custom_observable` only seeded `cell.host_attached` from the
   genuine trace value, leaving the other 5 host booleans at the
   `ports_schema` `False` default regardless of the real trace value.
   Fixed to seed all 6 via the existing `CUSTOM_VECTOR_SURFACES` mapping.
3. **Fabricated `before=0.0`** — `_level_truth_activity_detail` hardcoded
   `before=0.0` for every detected active tick instead of reading the real
   `states_before` value, fabricating a false "just turned on" narrative
   for a signal that is genuinely constant-True. Fixed to report the real
   value; the manifest's `trace_window.first_active_detail` now honestly
   reads `before=1.0/after=1.0` (was `before=0.0/after=1.0`).
4. **OC-side activity heuristic broke once seeding was fixed** — with
   booleans correctly seeded, `_recursive_update_nontrivial(update)`
   (checking the emitted delta dict) collapsed `oc_active_ticks` to 0 for
   the entire positive-control window, because a correctly-seeded,
   genuinely-active level signal emits no delta (nothing changed). Added
   an OC-side `LEVEL_TRUTH_ACTIVITY_PROCESSES` branch that projects the
   post-`next_update` state value directly (mirroring the Karr-side
   check) instead of relying on delta non-emptiness.
5. **Free-enzyme vs protein-counts topology** — verified NOT a divergence
   (Karr's `this.enzymes` for this zero-request process already reflects
   the raw, unpartitioned global copy number, matching OC's `protein.counts`
   shared-pool convention used identically by 45+ other process bindings
   in `karr_composite.py`) and documented explicitly in
   `data/schemas/per_process_wiring/HostInteraction.yaml`'s
   `known_deviations` to remove ambiguity for future auditors.
6. **Manifest authority** — `L21_ACTIVE_WINDOWS_MANIFEST.json`'s
   HostInteraction row now carries a `discriminating_conditions` block
   with all 5 conditions' predictions, genuine sha256-bound sources, and
   the 3 new pytest nodeids, alongside the corrected honest
   `trace_window.first_active_detail`.
7. **Debris cleanup** — the 2 MATLAB drivers (`extract_host_interaction_active_window.m`,
   `probe_host_interaction_canary.m`) were moved from `tmp/` to
   `scripts/matlab/` (tracked, reproducible); one-off `tmp/` inspection
   scripts used only for this round's manual verification were deleted
   after their checks were superseded by the new committed test file.

### New/changed files this round
- `docs/phase_f/l2_1/HOSTINTERACTION_CONDITION_PREREGISTRATION.md` (new,
  preregistered before extraction).
- `scripts/matlab/extract_host_interaction_active_window.m` (moved from
  `tmp/`, extended with the 5-condition extraction loop).
- `scripts/matlab/probe_host_interaction_canary.m` (moved from `tmp/`,
  unchanged).
- `scripts/matlab/extract_per_process_traces_v2.m`: new
  `apply_process_enzyme_overrides`/`select_process_enzyme_overrides`
  helpers and `per_process_enzyme_overrides` opt (default empty,
  backward-compatible).
- `tests/scripts/test_extract_per_process_traces_v2_static.py`: new
  `test_per_process_enzyme_overrides_wired_at_both_copyfromstate_sites`.
- `tests/vivarium/test_karr_host_interaction_discriminating_conditions.py`
  (new, 15 tests): genuine-condition-matches-prediction,
  literal-port-bit-exact, and constant-True-stub-fails, each parametrized
  over all 5 conditions.
- `scripts/l21_active_window_audit.py`: seed-all-six-booleans fix, honest
  `before` value fix, OC-side level-truth activity fix.
- `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`: HostInteraction row
  updated (honest `trace_window.first_active_detail`, new
  `discriminating_conditions` block).
- `data/schemas/per_process_wiring/HostInteraction.yaml`: `known_deviations`
  extended with the free-enzyme-vs-protein-counts topology clarification.
- `docs/phase_f/l2_1/HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md`: new
  section 11 (after-the-fact discriminating-conditions comparison).
- `.gitignore`: added
  `data/m1_sources/karr_native/per_process_traces_v2_host_condition_*/`.

### Verification (all green, this round)
- `bin\oc-py.cmd scripts/l21_active_window_audit.py --process HostInteraction`
  → unchanged `EXISTING_WINDOW_PASS`, `bit_identity.pass_all_compared_ticks=true`,
  `honest_replay.oc_active_on_karr_active_ticks=100/100`,
  `trace_window.first_active_detail` now honestly `before=1.0/after=1.0`.
- `bin\oc-pytest.cmd tests/vivarium/test_karr_host_interaction.py
  tests/vivarium/test_karr_host_interaction_l2_replay.py
  tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py
  tests/vivarium/test_karr_host_interaction_discriminating_conditions.py
  tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py
  tests/scripts/test_l21_active_window_audit_host_custom_surfaces.py
  tests/scripts/test_extract_per_process_traces_v2_static.py` → 58 passed,
  1 skipped (same pre-existing, unrelated allocator-oracle skip as before).
- `tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py::test_current_tree_active_window_manifest_checkpoint`
  (all 11 processes) → 11 passed, confirming the manifest edits did not
  regress any other process's row.
- `bin\oc-py.cmd scripts/l21_active_window_audit.py --process ChromosomeSegregation`
  spot check → unchanged `MISSING_ACTIVE_EXTRACTION` (pre-existing,
  confirms the fixes are gated behind `process_name == "HostInteraction"`
  / `LEVEL_TRUTH_ACTIVITY_PROCESSES` and cannot affect other processes).
- `bin\oc-py.cmd scripts/l1b_verify_wiring.py --process HostInteraction` →
  PASS.
- `ruff check` on all changed Python files → clean.

## Commits
See `git log agent/l21-host-active-fix-20260904` for the chunked, green
commits (each preceded by the test run that validated it).
