# Phase E.2 - 28-Phenotype Scorecard

`E2_PASS=7/28 OC=4/8 VAL=1/8 INC=0/5 BEY=2/7 FAIL=16 BLOCKED=0 DEFERRED=2 NEEDS_EMITTER=3`

**Run**: chassis_v6 @ commit `unknown`
**Wall-time**: `0.00` s
**Pass count**: `7/28` (pre-fix baseline gate >=6)
**Bucket summary**: opencell-tooling 4/8 · validation-and-organism-scaling 1/8 · karr-known-incomplete 0/5 · biology-beyond-Karr 2/7
**Blocked**: `0` (None)
**Deferred**: `2` (KP25, KP26)
**Needs emitter**: `3` (KP15, KP27, KP28)

## Pre-fix vs Post-fix

This scorecard is the **BEFORE-fix baseline** captured on the known broken chassis_v6 (allocation-bypass cascade from E.1). Failures and blocked rows are expected inputs to E.3. A second E.2 run will be produced after the allocation-consumer fix lands.

## Per-KP detail

| KP | Label | Bucket | Opencell | Karr | rel_err | Status | Disposition |
|---|---|---|---:|---:|---:|---|---|
| KP01 | Growth rate (g/s) | opencell-tooling | 4.42492e-21 | 2.11927e-05 | 1 | FAIL | tolerance exceeded |
| KP02 | Doubling time (s) | validation-and-organism-scaling | NaN | 47186.1 | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP03 | Flux-oracle agreement | opencell-tooling | 2.91967 | 0 | 2.92e+12 | FAIL | threshold_max exceeded |
| KP04 | Glucose uptake (PTS) | validation-and-organism-scaling | 0.308138 | 2725 | 0.9999 | FAIL | tolerance exceeded |
| KP05 | Total mRNA abundance | validation-and-organism-scaling | 670 | 784 | 0.1454 | PASS | within tolerance |
| KP06 | Total protein abundance | validation-and-organism-scaling | 29125 | 16177 | 0.8004 | FAIL | tolerance exceeded |
| KP07 | mRNA short-horizon stability | opencell-tooling | 0.000711523 | 0.1 | 0.007115 | PASS | threshold_max satisfied |
| KP08 | Protein short-horizon stability | opencell-tooling | 0.0007654 | 0.1 | 0.007654 | PASS | threshold_max satisfied |
| KP09 | Amino-acid pool stability | opencell-tooling | 0.0109728 | 0.1 | 0.1097 | PASS | threshold_max satisfied |
| KP10 | Cell dry mass (g) at division | validation-and-organism-scaling | 1.096e-14 | 3.94464e-15 | 1.778 | FAIL | tolerance exceeded |
| KP11 | Replication initiation timing (s) | karr-known-incomplete | NaN | NA | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP12 | Replication duration (s) | karr-known-incomplete | NaN | NA | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP13 | Cytokinesis duration (s) | karr-known-incomplete | 0 | 3869 | 1 | FAIL | ratio out of [0.4, 2.5] |
| KP14 | dNTP vs replication coupling | opencell-tooling | 0 | 0.5 | 1 | FAIL | below minimum threshold |
| KP15 | DNA-binding occupancy dynamics | biology-beyond-Karr | NA | True | NA | NEEDS_EMITTER | missing emitted trajectory field(s) (E2-V1_1-KP15-DNA-OCCUPANCY) |
| KP16 | DNA content doubling | opencell-tooling | 1 | 2 | 0.5 | FAIL | tolerance exceeded |
| KP17 | DNA mass fraction | validation-and-organism-scaling | 0 | 0.1688 | 1 | FAIL | tolerance exceeded |
| KP18 | RNA mass fraction | validation-and-organism-scaling | 0 | 0.0434821 | 1 | FAIL | tolerance exceeded |
| KP19 | Protein mass fraction | validation-and-organism-scaling | 0.0167298 | 0.277002 | 0.9396 | FAIL | tolerance exceeded |
| KP20 | Metabolite concentration profile | karr-known-incomplete | 3.0788 | 1 | 3.079 | FAIL | threshold_max exceeded |
| KP21 | ATP/GTP production-use balance | opencell-tooling | 2.82179e-13 | 0 | 2.822e-13 | PASS | within tolerance |
| KP22 | Energy discrepancy phenotype | karr-known-incomplete | False | True | 1 | FAIL | qualitative boolean mismatch |
| KP23 | Burst-like protein synthesis stats | biology-beyond-Karr | True | True | 0 | PASS | qualitative boolean matched |
| KP24 | mRNA/protein distribution shape | biology-beyond-Karr | True | True | 0 | PASS | qualitative boolean matched |
| KP25 | Gene essentiality accuracy | biology-beyond-Karr | NA | NA | NA | DEFERRED | multi-run KO sweep required (E2-V1_1-KP25-KO-SWEEP) |
| KP26 | Single-gene disruption phenotype class | biology-beyond-Karr | NA | NA | NA | DEFERRED | multi-run KO sweep required (E2-V1_1-KP26-KO-CLASS) |
| KP27 | Host adhesion competence | biology-beyond-Karr | NA | True | NA | NEEDS_EMITTER | missing emitted trajectory field(s) (E2-V1_1-KP27-HOST-ADHESION) |
| KP28 | Host immune activation cascade | biology-beyond-Karr | NA | True | NA | NEEDS_EMITTER | missing emitted trajectory field(s) (E2-V1_1-KP28-HOST-IMMUNE-CASCADE) |
