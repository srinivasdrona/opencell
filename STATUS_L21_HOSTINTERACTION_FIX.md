# STATUS — HostInteraction L2.1 Active Window Closure (2026-09-04)

## Task
Close HostInteraction's `MISSING_ACTIVE_EXTRACTION` L2.1 gap (the sole
missing active window in `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`)
and any literal source gap discovered along the way, without fabricating an
event, without raising `max_search_ticks` blindly, and without launching
extra seeds speculatively.

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

## Commits
See `git log agent/l21-host-active-fix-20260904` for the chunked, green
commits (each preceded by the test run that validated it).
