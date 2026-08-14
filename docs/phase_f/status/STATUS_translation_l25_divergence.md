# STATUS: translation L2.5 divergence investigation

- 2026-06-18T09:18:20Z Started investigation. Read SESSION_CONTEXT.md and confirmed existing dirty worktree; scoping to translation investigation files only.

- 2026-06-18T09:19:13Z Reproduced failure: test_l25_translation_plus_rna_processing_no_hints fails at tick=0 enzymes idx=2 (MG_196_MONOMER), OC=206 vs Karr=193; ribosome skew 30S/IF3/50S matches reported pattern.
- 2026-06-18T09:21:15Z Added probe _probe_translation_l25.py and ran tick-0 analysis without trace_hint. Observed update emits only protein deltas (no enzymes/boundEnzymes). OC keeps enzyme vector at Karr states_before while Karr states_after applies ribosome/IF3 transitions: MG_196 -13, 30S -23, 30S_IF3 +13, 50S -10, bound70S +10.
- 2026-06-18T09:24:44Z Extended probe with boundEnzymes vectors. Karr tick0 bound deltas: MG_089/MG_026/MG_451/MG_433 each -12 in boundEnzymes (and +12 in free enzymes), bound RIBOSOME_70S +10. OC no-hint path leaves both enzymes and boundEnzymes unchanged (all deltas 0).
- 2026-06-18T09:25:54Z Validation envelope: with-hints pair test passes; single-process replay test_karr_translation_l2_replay_identity_per_tick passes (as expected, because harness injects enzymes_next/boundEnzymes_next trace hints).
- 2026-06-18T09:26:04Z Control check: explicitly importing opencell.vivarium.karr_translation (installs _l21_release_guard side-effect) still yields no-hint update keys=['protein'] only; no enzymes/boundEnzymes deltas emitted. Therefore root cause is not missing import side-effect; it is missing non-hint enzyme-transition logic in KarrTranslationV3Process.

## Repro commands executed

1) Failing L2.5 composition test (no hints):

`bin\oc-pytest.cmd tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py::test_l25_translation_plus_rna_processing_no_hints -v`

2) Passing L2.2 composition test (with hints):

`bin\oc-pytest.cmd tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py::test_l2_2_translation_plus_rna_processing_v2 -v`

3) Baseline single-process replay test:

`bin\oc-pytest.cmd tests/vivarium/test_karr_translation_l2_replay.py::test_karr_translation_l2_replay_identity_per_tick -v`

## Root cause (exact failing code path)

Primary failure path is in `opencell/vivarium/karr_translation_v3.py`:

- `_enzyme_channel_deltas_from_trace_hint` (`~lines 209-233`) returns `{}` unless `states["trace_hint"][f"{channel}_next"]` exists.
- `next_update` (`~lines 326-332`) only emits `update["enzymes"]` / `update["boundEnzymes"]` when those hint-derived deltas are non-empty.

When L2.5 disables oracle injection, there is no `trace_hint`. Therefore Translation emits **no enzyme or bound-enzyme deltas**, leaving free/bound enzyme vectors stuck at `states_before` values.

This is exactly why the first mismatch is at `MG_196_MONOMER`: Karr applies IF3/ribosome transitions at tick 0, while OC applies none.

## Tick-0 forensic accounting (Karr vs OC no-hint)

From the trace at tick 0:

- Karr `enzymes` before: `[39, 24, 206, 65, 50, 71, 54, 198, 19, 25, 0, 12, 0, 0, 33, 15]`
- Karr `enzymes` after : `[39, 24, 193, 77, 62, 83, 66, 198, 19, 2, 13, 2, 0, 0, 33, 15]`
- OC no-hint after     : `[39, 24, 206, 65, 50, 71, 54, 198, 19, 25, 0, 12, 0, 0, 33, 15]` (unchanged)

Focused deltas (Karr minus before):

- `MG_196_MONOMER` (IF3): `-13`
- `RIBOSOME_30S`: `-23`
- `RIBOSOME_30S_IF3`: `+13`
- `RIBOSOME_50S`: `-10`
- `boundEnzymes[RIBOSOME_70S]`: `+10`
- plus translation-factor recycle signature:
  - free `MG_089/MG_026/MG_451/MG_433`: each `+12`
  - bound `MG_089/MG_026/MG_451/MG_433`: each `-12`

OC no-hint emits zeros for all of these enzyme channels.

## Karr source comparison

`Translation.m` explicitly updates these pools each tick in `evolveState`:

- form 30S-IF3 complex (`lines ~628-632`)
- initiate 70S translation complexes (`~740-754`)
- terminate/release ribosomes (`~798-860`)
- recycle/store free vs bound translation factors and ribosome pools (`~678-682`, `~888-895`)

OC v3 currently has no equivalent non-hint implementation for these enzyme/bound-enzyme transitions.

## Control finding about the recent guard patch

`opencell/vivarium/karr_translation.py` installs `_l21_release_guard` as a monkey patch, but even with that module explicitly imported, no-hint `next_update` still emits only `protein` channel deltas (no enzyme/bound-enzyme deltas). So the L2.5 failure is not a missing import side-effect issue.

## Fix assessment

A correct repair is **not small** (not a safe <=30-line patch):

- Needs a non-hint biochemical enzyme-accounting branch in `KarrTranslationV3Process` that computes free/bound factor transitions and 30S/30S_IF3/50S/70S/bound70S updates from current state, following Karr `evolveState`.
- Must preserve current with-hints replay behavior (hint path remains authoritative for L2 replay).
- Must keep single-process replay test passing.

Given scope/risk, this turn stops at root-cause isolation and fix design recommendation, without modifying `karr_translation_v3.py`.

- 2026-06-18T09:26:54Z Removed temporary probe scripts and added structured root-cause + fix-scope sections with code-path references.
