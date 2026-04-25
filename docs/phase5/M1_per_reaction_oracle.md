# M1 per-reaction validation oracle (Karr-native)

- Module: `opencell.m1.karr_metabolism`
- Fixture: `data/karr_fixtures/karr_native_m1.json`
- LP: biomass flux = `0.0392 /h` (stored = `0.0763 /h`)
- Total nonzero predicted fluxes: `324`

## Acceptance
- Metric: `median |log2(predicted/karr_stored)|`
- Threshold: `< 1.0`
- Value: `0.9599442045485458`
- Comparable reactions (both nonzero): `196`
- **Passed: `True`**

## Summary
- Within 2x: `105` / `196`
- Within 8x: `126` / `196`
- p90 |log2 ratio|: `9.965784284662087`
- Sign counts: `{'agree': 147, 'pred_zero_karr_nonzero': 57, 'karr_zero_pred_nonzero': 35, 'both_zero': 52, 'disagree': 45}`

## Top-disagreeing reactions (by |log2 ratio|, both nonzero)

| WCM ID | fba col | predicted | karr stored | |log2 ratio| | sign |
|---|---:|---:|---:|---:|---|
| `Pdp3` | 156 | -2.654 | 3.735e-25 | 82.555 | karr_zero_pred_nonzero |
| `DeoD5` | 53 | -2.654 | 3.735e-25 | 82.555 | karr_zero_pred_nonzero |
| `TX_ACAL` | 223 | 4.717 | -3.26e-24 | 80.260 | karr_zero_pred_nonzero |
| `TX_URA` | 314 | -997.1 | -1.428e-17 | 65.921 | karr_zero_pred_nonzero |
| `Pgi` | 162 | -0.212 | 2725 | 13.650 | disagree |
| `DeoD8` | 55 | -1000 | 0.2136 | 12.193 | disagree |
| `Pdp1` | 154 | 1000 | -0.2136 | 12.193 | disagree |
| `TX_H2O2` | 257 | -4.634 | -1.058e+04 | 11.157 | agree |
| `PcbX` | 153 | -933.8 | -1e+06 | 10.065 | agree |
| `TX_AROP12` | 228 | -992.1 | -1e+06 | 9.977 | agree |
| `TX_AROP13` | 229 | -995.6 | 9.97e+05 | 9.968 | disagree |
| `TX_AROP11` | 227 | -998.8 | -1e+06 | 9.967 | agree |
| `LIPASE_DIBUTYRIN_MG310` | 95 | -1000 | 1e+06 | 9.966 | disagree |
| `LIPASE_DIBUTYRIN_MG344` | 97 | 1000 | -1e+06 | 9.966 | disagree |
| `LIPASE_METHYL_OCDCEA_MG310` | 98 | -1000 | 1e+06 | 9.966 | disagree |
| `LIPASE_METHYL_OCDCEA_MG344` | 100 | 1000 | -1e+06 | 9.966 | disagree |
| `LIPASE_MONOBUTYRIN_MG310` | 101 | -1000 | 1e+06 | 9.966 | disagree |
| `LIPASE_MONOBUTYRIN_MG344` | 103 | 1000 | -1e+06 | 9.966 | disagree |
| `LIPASE_TRIBUTYRIN_MG310` | 104 | -1000 | 1e+06 | 9.966 | disagree |
| `LIPASE_TRIBUTYRIN_MG344` | 106 | 1000 | -1e+06 | 9.966 | disagree |
| `LIPASE_TRILAURIN_MG310` | 107 | -1000 | 1e+06 | 9.966 | disagree |
| `LIPASE_TRILAURIN_MG344` | 109 | 1000 | -1e+06 | 9.966 | disagree |
| `LIPASE_TRIMYRISTIN_MG310` | 110 | -1000 | 1e+06 | 9.966 | disagree |
| `LIPASE_TRIMYRISTIN_MG344` | 112 | 1000 | -1e+06 | 9.966 | disagree |
| `LIPASE_TRIOLEIN_MG310` | 113 | -1000 | 1e+06 | 9.966 | disagree |

## Interpretation

Karr-native per-reaction oracle: opencell.m1.karr_metabolism solves Karr's fitted FBA exactly (S 376x504, RHS 376, full objective with biomass +1000 and 35 parsimony penalties, no enzyme bounds because they are post-step). Predicted fluxes are compared 1:1 against Karr's stored runtime fluxs[645] indexed by reactionWholeCellModelID -- no ID mapping required (iPS189 fully dropped). Acceptance: median |log2(predicted/karr_stored)| < 1.0 over reactions where both fluxes are nonzero. Sign disagreement on a reversible reaction indicates direction inversion under biomass-max vs Karr's runtime context.