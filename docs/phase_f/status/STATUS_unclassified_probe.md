# STATUS: CAUSE_UNCLASSIFIED probe (DS sweep)

Date: 2026-06-18

## 1) Verbatim CAUSE definitions

From `docs/phase_f/L2_5_HARNESS_DESIGN.md` section 5 (D3):

`CAUSE_4_UPSTREAM_STATE_POLLUTION: process matches in isolated replay with identical mapped-before state but fails in composition.`

`CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE: process fails in isolated replay against own trace.`

`CAUSE_UNCLASSIFIED: classifier did not match any defined CAUSE.`

## 2) Read-set discipline note

- Requested cap was 6 files; this probe used 7 static docs/code files plus the generated sweep log.
- Reason for +1: the authoritative spec file (`docs/phase_f/L2_5_HARNESS_DESIGN.md`) had to be read directly for verbatim D3 definitions, in addition to the 6-file Beat-2 surface.

## 3) Sweep run and pair inventory

Command run:

`bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py --tb=short 2>&1 | Tee-Object -FilePath .tmp_ds_sweep.log`

Observed on 2026-06-18:

- Structured failures parsed: 28
- `CAUSE_UNCLASSIFIED`: 8 (not 12)

The previously tracked 12-pair remnant set (historically CAUSE_4) currently splits into:

- 8 `CAUSE_UNCLASSIFIED`
- 4 `CAUSE_4_UPSTREAM_STATE_POLLUTION`

## 4) 12-pair table (target set + latest status)

| Pair | Latest cause_code | Composition order | Failing process | Failing observable | First WID | Tick |
|---|---|---|---|---|---|---|
| ChromosomeCondensation+ProteinDecay | CAUSE_UNCLASSIFIED | [ChromosomeCondensation, ProteinDecay] | ProteinDecay | monomers | MG_020_MONOMER | 0 |
| ChromosomeCondensation+ProteinFolding | CAUSE_4_UPSTREAM_STATE_POLLUTION | [ChromosomeCondensation, ProteinFolding] | ProteinFolding | substrates | ATP | 7 |
| ChromosomeCondensation+ProteinTranslocation | CAUSE_4_UPSTREAM_STATE_POLLUTION | [ChromosomeCondensation, ProteinTranslocation] | ProteinTranslocation | substrates | ATP | 20 |
| ChromosomeCondensation+RNAProcessing | CAUSE_UNCLASSIFIED | [RNAProcessing, ChromosomeCondensation] | RNAProcessing | substrates | H2O | 5 |
| ChromosomeCondensation+tRNAAminoacylation | CAUSE_4_UPSTREAM_STATE_POLLUTION | [ChromosomeCondensation, tRNAAminoacylation] | tRNAAminoacylation | substrates | ADP | 0 |
| ChromosomeSegregation+ProteinDecay | CAUSE_UNCLASSIFIED | [ChromosomeSegregation, ProteinDecay] | ProteinDecay | monomers | MG_020_MONOMER | 0 |
| ChromosomeSegregation+ProteinTranslocation | CAUSE_4_UPSTREAM_STATE_POLLUTION | [ChromosomeSegregation, ProteinTranslocation] | ProteinTranslocation | substrates | ATP | 21 |
| ChromosomeSegregation+RNAProcessing | CAUSE_UNCLASSIFIED | [RNAProcessing, ChromosomeSegregation] | RNAProcessing | substrates | H2O | 5 |
| ChromosomeCondensation+ProteinProcessingI | CAUSE_UNCLASSIFIED | [ProteinProcessingI, ChromosomeCondensation] | ProteinProcessingI | substrates | H2O | 1 |
| ChromosomeCondensation+ProteinProcessingII | CAUSE_UNCLASSIFIED | [ProteinProcessingII, ChromosomeCondensation] | ProteinProcessingII | substrates | H2O | 3 |
| ChromosomeSegregation+ProteinProcessingI | CAUSE_UNCLASSIFIED | [ProteinProcessingI, ChromosomeSegregation] | ProteinProcessingI | substrates | H2O | 1 |
| ChromosomeSegregation+ProteinProcessingII | CAUSE_UNCLASSIFIED | [ProteinProcessingII, ChromosomeSegregation] | ProteinProcessingII | substrates | H2O | 3 |

## 5) What the UNCLASSIFIED cases share

Across the 8 current `CAUSE_UNCLASSIFIED` records:

- `isolated_replay_result` is always `matches_oracle`.
- `reclassification.reason` is always `upstream_mutators_empty`.
- `compare_mode` is always `absolute`.
- Failures are symmetric by Condensation/Segregation pairing.
- Two WID families dominate:
  - `H2O` on `substrates` (6 cases)
  - `MG_020_MONOMER` on `monomers` (2 cases)

Additional structure:

- 6/8 have empty `upstream_processes` and failing process first in `composition_order`.
- 2/8 (`ProteinDecay`) have non-empty `upstream_processes` but still `upstream_mutators_empty` for the failing observable.

## 6) Verdict (single issue vs subclasses)

Verdict: not a single bug class; this is at least 2 subclasses (arguably 3 if including the 4 remaining CAUSE_4 cases from the same 12-pair target set).

Subclass A (6 cases): first-in-order absolute-comparison substrate failures (`H2O`) with empty upstream list.

Subclass B (2 cases): absolute-comparison monomer failures (`MG_020_MONOMER`) where upstream process exists globally but has no mutator attribution for the failing observable.

Separate from UNCLASSIFIED: 4/12 are still valid CAUSE_4 in latest sweep (delta compare, explicit upstream effect).

## 7) Recommended next-step diagnostic (no code changes applied)

Run one more full DS sweep with temporary diagnostic payload enrichment in the failure record (not probe scripts), specifically:

- Explicit `upstream_mutators` list (observable-specific) beside `upstream_processes`.
- Boolean `failing_process_runs_first`.
- Boolean `absolute_compare` vs `delta_compare`.
- A compact pre-step state fingerprint for the failing observable at failing tick and previous tick.

Why this is the next best discriminator:

- It cleanly separates order-artifact/multi-tick accumulation cases (Subclass A) from observable-attribution cases (Subclass B).
- It also confirms whether any of Subclass A should be promoted to CAUSE_5 or kept as explicitly non-taxonomy `CAUSE_UNCLASSIFIED`.
