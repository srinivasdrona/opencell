# Phase E.2 - 28-Phenotype Scorecard

`E2_PASS=6/28 OC=3/8 VAL=0/8 INC=1/5 BEY=2/7 BLOCKED=13`

**Run**: chassis_v6 @ commit `unknown`
**Wall-time**: `2330.35` s
**Pass count**: `6/28` (pre-fix baseline gate >=6)
**Bucket summary**: opencell-tooling 3/8 · validation-and-organism-scaling 0/8 · karr-known-incomplete 1/5 · biology-beyond-Karr 2/7
**Blocked**: `13` (KP03, KP04, KP13, KP15, KP17, KP18, KP19, KP20, KP21, KP25, KP26, KP27, KP28)

## Pre-fix vs Post-fix

This scorecard is the **BEFORE-fix baseline** captured on the known broken chassis_v6 (allocation-bypass cascade from E.1). Failures and blocked rows are expected inputs to E.3. A second E.2 run will be produced after the allocation-consumer fix lands.

## v1 vs v2 framing (READ BEFORE INTERPRETING PASSES)

OpenCell v1.0 is scoped as **"Karr-on-Vivarium with prescribed parameters"** — kinetic rates, half-lives, expression levels, and FBA bounds are taken verbatim from Karr's WCKB fixtures. The validation oracle is therefore *numerical correctness of the integration* (28 processes, allocation cycle, topology preserved), NOT independent biology.

- A v1.0 PASS row means: "our integration of Karr's parameters into Vivarium reproduces the Karr-published value within tolerance."
- It does **not** mean: "we derived this rate from first-principles biophysics."
- KP07/08/09 short-horizon stability passes are partly tautological under v1 — the parameters were fit to make these hold.
- v2 (per-submodel direction, not a single milestone): each submodel earns v2 status when its rates are derived from molecular counts × biophysics, and Karr's fitted values become a cross-check oracle instead of the parameter source. See decision log entry `v1-prescribed-rates-v2-first-principles` (2026-05-23, `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md`).

## Per-KP detail

| KP | Label | Bucket | Opencell | Karr | rel_err | Status | Disposition |
|---|---|---|---:|---:|---:|---|---|
| KP01 | Growth rate (g/s) | opencell-tooling | -9.33941e-19 | 2.11927e-05 | 1 | FAIL | tolerance exceeded |
| KP02 | Doubling time (s) | validation-and-organism-scaling | NaN | 47186.1 | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP03 | Flux-oracle agreement | opencell-tooling | NA | 0 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP03-FLUX-ORACLE) |
| KP04 | Glucose uptake (PTS) | validation-and-organism-scaling | NA | 2725 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP04-TX_GLCPTS) |
| KP05 | Total mRNA abundance | validation-and-organism-scaling | 1261.18 | 784 | 0.6086 | FAIL | tolerance exceeded |
| KP06 | Total protein abundance | validation-and-organism-scaling | 91126.8 | 16177 | 4.633 | FAIL | tolerance exceeded |
| KP07 | mRNA short-horizon stability | opencell-tooling | 0.00400804 | 0.1 | 0.04008 | PASS | threshold_max satisfied |
| KP08 | Protein short-horizon stability | opencell-tooling | 0.0110741 | 0.1 | 0.1107 | PASS | threshold_max satisfied |
| KP09 | Amino-acid pool stability | opencell-tooling | 0.015194 | 0.1 | 0.1519 | PASS | threshold_max satisfied |
| KP10 | Cell dry mass (g) at division | validation-and-organism-scaling | -3.38576e-14 | 3.94464e-15 | 9.583 | FAIL | tolerance exceeded |
| KP11 | Replication initiation timing (s) | karr-known-incomplete | NaN | NA | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP12 | Replication duration (s) | karr-known-incomplete | NaN | NA | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP13 | Cytokinesis duration (s) | karr-known-incomplete | NA | NA | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP13-CYTOKINESIS-TRACE) |
| KP14 | dNTP vs replication coupling | opencell-tooling | 0 | 0.5 | 1 | FAIL | below minimum threshold |
| KP15 | DNA-binding occupancy dynamics | biology-beyond-Karr | NA | True | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP15-DNA-OCCUPANCY) |
| KP16 | DNA content doubling | opencell-tooling | 1 | 2 | 0.5 | FAIL | tolerance exceeded |
| KP17 | DNA mass fraction | validation-and-organism-scaling | NA | NA | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP17-DNA-MASS) |
| KP18 | RNA mass fraction | validation-and-organism-scaling | NA | 0.0434821 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP18-RNA-MASS) |
| KP19 | Protein mass fraction | validation-and-organism-scaling | NA | 0.277002 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP19-PROTEIN-MASS) |
| KP20 | Metabolite concentration profile | karr-known-incomplete | NA | NA | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP20-METABOLITE-PROFILE) |
| KP21 | ATP/GTP production-use balance | opencell-tooling | NA | 0 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP21-ENERGY-LEDGER) |
| KP22 | Energy discrepancy phenotype | karr-known-incomplete | True | True | 0 | PASS | qualitative boolean matched |
| KP23 | Burst-like protein synthesis stats | biology-beyond-Karr | True | True | 0 | PASS | qualitative boolean matched |
| KP24 | mRNA/protein distribution shape | biology-beyond-Karr | True | True | 0 | PASS | qualitative boolean matched |
| KP25 | Gene essentiality accuracy | biology-beyond-Karr | NA | NA | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP25-KO-SWEEP) |
| KP26 | Single-gene disruption phenotype class | biology-beyond-Karr | NA | NA | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP26-KO-CLASS) |
| KP27 | Host adhesion competence | biology-beyond-Karr | NA | True | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP27-HOST-ADHESION) |
| KP28 | Host immune activation cascade | biology-beyond-Karr | NA | True | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP28-HOST-IMMUNE-CASCADE) |
