# STATUS — investigate_kp20_regression

## Files read
- `opencell/validation/phenotype_registry.py`
- `opencell/validation/phenotype_extractors.py`
- `opencell/validation/phenotype_scorecard.py`
- `opencell/validation/karr_reference_values.py`
- `docs/phase_e/E2_scorecard_post_strip.md`
- `docs/phase_e/E2_scorecard_wave2.md`
- `STATUS_phenotype_scorecard_wave2.md`
- `STATUS_trackA_a1.md`
- `STATUS_trackA_a2.md`
- `STATUS_trackA_a3.md`
- `STATUS_ptransloc.md`
- `E:\opencell\artifacts\ensemble_wave2_20260527_023611\seed_{42,43,44,45}\trajectory.pkl`
- `E:\opencell\artifacts\ensemble_wave2_20260527_023611\seed_{42,43,44,45}\key_substrates.csv`
- `E:\opencell\artifacts\ensemble_wave2_20260527_023611\seed_43\process_traces\request_calculator_protein_translocation.csv`
- `E:\opencell\artifacts\ensemble_wave2_20260527_023611\seed_43\process_traces\request_calculator_translation.csv`
- `E:\opencell\artifacts\ensemble_wave2_20260527_023611\seed_43\process_traces\karr_allocation_step.csv`

## Files written
- `docs/phase_e/KP20_regression_investigation.md`
- `STATUS_investigate_kp20_regression.md`

## Commits
- `182142d` — `docs(kp20): regression investigation report`
- `<this commit>` — `STATUS_investigate_kp20_regression.md`

## Headline finding
KP20 regressed from PASS (`0.0239602`) to FAIL (`3.051..3.194` across seeds 42-45) because 20 amino-acid pools plus `GTP` (and late `ATP`) diverge by >10x from baseline, with KP20 crossing threshold by ~`166 s` in every seed.

## Recommendation
Fix the producing process (allocator/request path), starting with `RequestCalculatorPTransloc` request magnitude semantics and allocator request normalization effects, rather than changing KP20 threshold or extractor.

## Open questions
- Is the amino-acid floor-at-`1.0` behavior intentional (numerical guardrail) or an unintended allocator artifact?
- Which request producer dominates AA depletion in the first ~600 s (requires per-process ablation or request-ledger instrumentation)?
- Should KP20 for v6 baselines be computed on full 1 s substrate traces or only 100 s snapshot cadence?
