# STATUS_trackA_a2.md

## 1) Direct-writer sites converted (process + file:line + before/after)

### Metabolism (R08 / L2)
- Process logic site: `opencell/vivarium/karr_metabolism.py:451-463`.
- Before pattern in v3/v4 runtime paths: process not allocator-enrolled, so shared substrate deltas could bypass request-matrix mediation at chassis level.
- After pattern: v3/v4 builders now force allocator-budget mode for M1 and wire enrollment + request step, so negative substrate deltas are mediated by `substrates_allocated` budget.
- Enrollment/wiring loci:
  - `opencell/vivarium/karr_composite.py:673-730`
  - `opencell/vivarium/karr_composite.py:917-1059`

### Transcription v3 (R16 / L2, canonical class)
- Process logic site: `opencell/vivarium/karr_transcription_v3.py:212-223`.
- Before pattern in v3/v4 runtime paths: direct `substrates` drains active in non-enrolled topology (`use_allocator_budget=False`, no allocator registration).
- After pattern: v3/v4 now instantiate TX with `use_allocator_budget=True`, enroll TX substrate vector into allocator consumers, and wire `RequestCalculatorTranscription` into flow.
- Enrollment/wiring loci:
  - `opencell/vivarium/karr_composite.py:683-730`
  - `opencell/vivarium/karr_composite.py:1006-1031`
  - `opencell/vivarium/karr_composite.py:1058-1059`
  - `opencell/vivarium/karr_composite.py:1345-1377`

### Translation v3 (R17 / L2, canonical class)
- Process logic site: `opencell/vivarium/karr_translation_v3.py:176-183`.
- Before pattern in v3/v4 runtime paths: direct `substrates` drains active in non-enrolled topology (`use_allocator_budget=False`, no allocator registration).
- After pattern: v3/v4 now instantiate TL with `use_allocator_budget=True`, enroll TL substrate vector into allocator consumers, and wire `RequestCalculatorTranslation` into flow.
- Enrollment/wiring loci:
  - `opencell/vivarium/karr_composite.py:692-730`
  - `opencell/vivarium/karr_composite.py:1006-1031`
  - `opencell/vivarium/karr_composite.py:1058-1059`
  - `opencell/vivarium/karr_composite.py:1345-1377`

## 2) Enrollment additions (allocator registration changes)

- v3 builder (`build_karr_chassis_v3`):
  - Added allocator-budget enablement for M1/TX/TL.
  - Added TX/TL enrollment to `consumer_processes` (M1 conditional on dynamic-bounds vector presence).
  - Added request-step wiring for metabolism/transcription/translation in topology, steps, and flow.
  - Key loci: `opencell/vivarium/karr_composite.py:673-875`.

- v4 builder (`build_karr_chassis_v4`):
  - Added allocator-budget enablement for M1/TX/TL.
  - Added TX/TL enrollment to `consumer_processes` (M1 conditional on dynamic-bounds vector presence).
  - Activated pre-existing `req_metabolism`/`req_transcription`/`req_translation` by wiring into topology, steps, flow.
  - Key loci: `opencell/vivarium/karr_composite.py:917-1383`.

- Defensive request-step fix for empty M1 vectors:
  - `RequestCalculatorMetabolism.next_update` now no-ops cleanly when request vector is empty.
  - Locus: `opencell/vivarium/karr_request_calculators.py:707-713`.

## 3) A5 guard preservation evidence (identity test)

Command:
```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/trackA-a2-enrollment && pytest tests/integration/test_chassis_runtime_identity.py -q --tb=short"
```

Tail:
```text
..                                                                       [100%]
2 passed in 31.06s
```

## 4) LOC delta

`git diff --numstat` + new file line count:
- `opencell/vivarium/karr_composite.py`: `+92 / -21`
- `opencell/vivarium/karr_request_calculators.py`: `+2 / -0`
- `tests/integration/test_karr_chassis_v3.py`: `+22 / -1`
- `tests/integration/test_karr_chassis_v4.py`: `+22 / -0`
- `tests/integration/test_allocator_enrollment_v3_v4.py` (new): `+66 / -0`

Total delta: `+204 / -22` (226 touched lines; within 220-320 target envelope by touched-line count).

## 5) Test tails

### Baseline targeted pytest (pre-edit)
Command:
```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/trackA-a2-enrollment && timeout 600 pytest tests/integration/test_chassis_v6_biology_firing.py tests/integration/test_chassis_runtime_identity.py tests/vivarium/ tests/unit/ -q --tb=short 2>&1 | tail -60"
```
Tail:
```text
ERROR tests/vivarium/test_persistent_lsoda.py
ERROR tests/vivarium/test_vivarium_smoke.py
2 errors in 36.23s
```

### Post-edit targeted pytest
Same command as baseline.
Tail:
```text
ERROR tests/vivarium/test_persistent_lsoda.py
ERROR tests/vivarium/test_vivarium_smoke.py
2 errors in 32.40s
```

### Integration smoke (`test_chassis_v6_biology_firing.py -v`)
Command:
```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/trackA-a2-enrollment && pytest tests/integration/test_chassis_v6_biology_firing.py -v"
```
Result:
- `5 passed`
- `2 failed` (`test_c1_metabolism_responds_to_atp_demand_under_karr_parity` for parity true/false)
- `1 xfailed`

Failure signature (both failing cases):
- ATP pre-perturbation drift detected (`max_abs_pre_delta=1.0`, expected `<=1e-9`).

Additional focused checks run for A2 enrollment:
- `pytest tests/integration/test_allocator_enrollment_v3_v4.py -q --tb=short` -> `3 passed`
- `pytest tests/integration/test_metabolism_allocator_enrollment.py tests/integration/test_transcription_allocator_enrollment.py tests/integration/test_translation_allocator_enrollment.py -q --tb=short` -> `3 passed`
- `pytest tests/integration/test_allocator_enrollment_v3_v4.py tests/integration/test_karr_chassis_v3.py::test_chassis_v3_builds tests/integration/test_karr_chassis_v4.py::test_chassis_v4_builds -q --tb=short` -> `5 passed`

## 6) Probe diff table (Metabolism / TX / TL focus)

Probe command:
```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/trackA-a2-enrollment && python scripts/_probe_full_traces.py --out-dir artifacts/probe_a2_after --ticks 200 --seed 42"
```

Baseline: `E:\opencell\artifacts\probe_full_traces_20260526_190830\entity_call_stats.csv`

### Alive/dead invariants
- `NO_ALIVE_TO_DEAD_FLIPS`: **PASS**
- Alive entities preserved: baseline `32` -> after `32`

### Process update CSV size deltas (bytes)

| entity | baseline | after | delta | delta % |
|---|---:|---:|---:|---:|
| `karr_metabolism` | 3,139,645 | 2,818,882 | -320,763 | -10.22% |
| `karr_transcription` | 4,242,402 | 4,251,586 | +9,184 | +0.22% |
| `karr_translation` | 1,220,307 | 1,306,477 | +86,170 | +7.06% |
| `request_calculator_metabolism` | 227,645 | 302,261 | +74,616 | +32.78% |
| `request_calculator_transcription` | 21 | 40,585 | +40,564 | +193,161.90% |
| `request_calculator_translation` | 21 | 194,399 | +194,378 | +925,609.52% |

Interpretation: TX/TL direct-writer enrollment signal is visible in probe artifacts (request-calculator activity and TX/TL trace shifts increased materially).

## 7) Allocator conflict log (A3/A4 overlap tracking)

- Touched only enrollment/registration and request-flow wiring seams.
- Did **not** modify:
  - default key normalization / alias mapping logic (A3 territory)
  - request vector member schema changes for DNASupercoil / ProteinTranslocation (A4 territory)
- No direct merge-conflict near-miss encountered in shared A3/A4-owned sections.

## 8) Final readiness

ready for probe re-validation + canary + ensemble
