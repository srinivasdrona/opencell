# Phase E.2 - 28-Phenotype Scorecard

`E2_PASS=7/28 OC=3/8 VAL=1/8 INC=1/5 BEY=2/7 BLOCKED=8`

**Run**: chassis_v6 @ commit `ee52141`
**Wall-time**: `0.00` s
**Pass count**: `7/28` (pre-fix baseline gate >=6)
**Bucket summary**: opencell-tooling 3/8 · validation-and-organism-scaling 1/8 · karr-known-incomplete 1/5 · biology-beyond-Karr 2/7
**Blocked**: `8` (KP03, KP04, KP15, KP21, KP25, KP26, KP27, KP28)

## Pre-fix vs Post-fix

This scorecard is the **BEFORE-fix baseline** captured on the known broken chassis_v6 (allocation-bypass cascade from E.1). Failures and blocked rows are expected inputs to E.3. A second E.2 run will be produced after the allocation-consumer fix lands.

## Per-KP detail

| KP | Label | Bucket | Opencell | Karr | rel_err | Status | Disposition |
|---|---|---|---:|---:|---:|---|---|
| KP01 | Growth rate (g/s) | opencell-tooling | -8.7262e-22 | 2.11927e-05 | 1 | FAIL | tolerance exceeded |
| KP02 | Doubling time (s) | validation-and-organism-scaling | NaN | 47186.1 | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP03 | Flux-oracle agreement | opencell-tooling | NA | 0 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP03-FLUX-ORACLE) |
| KP04 | Glucose uptake (PTS) | validation-and-organism-scaling | NA | 2725 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP04-TX_GLCPTS) |
| KP05 | Total mRNA abundance | validation-and-organism-scaling | 658 | 784 | 0.1607 | PASS | within tolerance |
| KP06 | Total protein abundance | validation-and-organism-scaling | 27453 | 16177 | 0.697 | FAIL | tolerance exceeded |
| KP07 | mRNA short-horizon stability | opencell-tooling | 0.000744073 | 0.1 | 0.007441 | PASS | threshold_max satisfied |
| KP08 | Protein short-horizon stability | opencell-tooling | 0.000247558 | 0.1 | 0.002476 | PASS | threshold_max satisfied |
| KP09 | Amino-acid pool stability | opencell-tooling | 0.00246855 | 0.1 | 0.02469 | PASS | threshold_max satisfied |
| KP10 | Cell dry mass (g) at division | validation-and-organism-scaling | 1.08466e-14 | 3.94464e-15 | 1.75 | FAIL | tolerance exceeded |
| KP11 | Replication initiation timing (s) | karr-known-incomplete | NaN | NA | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP12 | Replication duration (s) | karr-known-incomplete | NaN | NA | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP13 | Cytokinesis duration (s) | karr-known-incomplete | 0 | 3869 | 1 | FAIL | ratio out of [0.4, 2.5] |
| KP14 | dNTP vs replication coupling | opencell-tooling | 0 | 0.5 | 1 | FAIL | below minimum threshold |
| KP15 | DNA-binding occupancy dynamics | biology-beyond-Karr | NA | True | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP15-DNA-OCCUPANCY) |
| KP16 | DNA content doubling | opencell-tooling | 1 | 2 | 0.5 | FAIL | tolerance exceeded |
| KP17 | DNA mass fraction | validation-and-organism-scaling | NaN | 0.1688 | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP18 | RNA mass fraction | validation-and-organism-scaling | NaN | 0.0434821 | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP19 | Protein mass fraction | validation-and-organism-scaling | NaN | 0.277002 | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP20 | Metabolite concentration profile | karr-known-incomplete | 0.0239602 | 1 | 0.02396 | PASS | threshold_max satisfied |
| KP21 | ATP/GTP production-use balance | opencell-tooling | NA | 0 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP21-ENERGY-LEDGER) |
| KP22 | Energy discrepancy phenotype | karr-known-incomplete | False | True | 1 | FAIL | qualitative boolean mismatch |
| KP23 | Burst-like protein synthesis stats | biology-beyond-Karr | True | True | 0 | PASS | qualitative boolean matched |
| KP24 | mRNA/protein distribution shape | biology-beyond-Karr | True | True | 0 | PASS | qualitative boolean matched |
| KP25 | Gene essentiality accuracy | biology-beyond-Karr | NA | NA | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP25-KO-SWEEP) |
| KP26 | Single-gene disruption phenotype class | biology-beyond-Karr | NA | NA | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP26-KO-CLASS) |
| KP27 | Host adhesion competence | biology-beyond-Karr | NA | True | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP27-HOST-ADHESION) |
| KP28 | Host immune activation cascade | biology-beyond-Karr | NA | True | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP28-HOST-IMMUNE-CASCADE) |
