# Track A5 TX/TL v3 Fitness Summary

## Decision: (a) `seed_from_fixture` flag with chassis honor
- Chosen path: **(a)**.
- Rationale: we need fixture-aligned `t=0` for Karr replay parity, but there are legitimate non-replay/debug use cases that may still want the historical non-zero initialization profile.
- Implementation choice: add `seed_from_fixture` to chassis builders and set default to fixture-aligned behavior (`True`) while preserving explicit opt-out (`False`).
- Code comment added at init site in `karr_composite.py` documenting this decision.

## Runtime-identity guardrails
- Added a chassis-level assertion helper `assert_chassis_runtime_identity(...)` in `opencell/vivarium/karr_composite.py`.
- Guardrail checks:
  - `karr_transcription` must be `KarrTranscriptionV3Process`.
  - `karr_translation` must be `KarrTranslationV3Process`.
  - legacy keys `karr_transcription_v3` / `karr_translation_v3` must be absent in v6 runtime map.
- Wired into `build_karr_chassis_v6` so identity drift fails fast at build time.

## TL t=0 monomer fix
- Implemented fixture-backed monomer seeding from `data/karr_fixtures/per_process/Translation.npz` (`fixture__monomers`).
- `build_karr_chassis_v5` now accepts `seed_from_fixture: bool = True` and uses fixture monomers when enabled.
- `build_karr_chassis_v6` forwards the same flag to v5.
- Added dimension guard (`fixture_monomers.size == len(m3_model.protein_wcm_ids)`) to fail fast on fixture/model drift.
- When fixture seeding is enabled, all translation monomers are explicitly initialized to prevent ports-schema defaults from reintroducing non-zero `counts_mature`.

## Files modified and LOC
- `opencell/vivarium/karr_composite.py`
- `tests/integration/test_chassis_runtime_identity.py`
- `tests/integration/test_tx_tl_v3_init_parity.py`
- `opencell/validation/track_a/a5_tx_tl_v3_fitness_summary.md`

Net LOC summary (current diff):
- Added: 265
- Deleted: 4

## Tests added and assertions
- `tests/integration/test_chassis_runtime_identity.py`
  - `test_v6_runtime_identity_matches_v3_bindings`:
    - guardrail helper passes,
    - runtime classes are v3 for TX/TL,
    - legacy v3 keys are absent,
    - TX/TL are not in steps.
  - `test_runtime_identity_guardrail_raises_on_class_drift`:
    - synthetic class drift triggers `AssertionError`.

- `tests/integration/test_tx_tl_v3_init_parity.py`
  - `test_translation_fixture_tick0_monomers_are_zero`:
    - fixture monomer vector shape `(482,)`,
    - all values are zero.
  - `test_v6_translation_t0_matches_fixture_when_seeded_from_fixture`:
    - chassis `protein.unprocessed_counts` matches fixture monomers exactly at `t=0` with `seed_from_fixture=True`.
  - `test_v6_translation_t0_can_opt_out_of_fixture_seeding`:
    - `seed_from_fixture=False` restores non-zero initialization behavior.

## Additional L0 mismatches beyond TX/TL
- None discovered in current `composition_audit.md` L0 hot list; only Transcription and Translation are listed.
- Therefore no additional runtime-identity guardrails were added beyond TX/TL in this PR.
