# Phase E.2 — 28-Phenotype Scorecard (post-wave2 baseline)

`E2_PASS=6/28 OC=3/8 VAL=1/8 INC=0/5 BEY=2/7 BLOCKED=8`

**Run**: trackA/wave2-base @ commit `75609c7` (post-wave2 ensemble seed 43)
**Trajectory**: artifacts/ensemble_wave2_20260527_023611/seed_43/trajectory.pkl (source root: `E:\opencell\artifacts`)
**Wall-time**: `0.00` s
**Pass count**: `6/28`
**Bucket summary**: opencell-tooling 3/8 · validation-and-organism-scaling 1/8 · karr-known-incomplete 0/5 · biology-beyond-Karr 2/7

## Framing note — this is a fragile baseline, not a stable one

> **Read this section before citing any number below.** Wave-2 closed the
> five A2/A3/A4/tracer/A6 audit findings cleanly, but the resulting baseline
> is fragile, not stable:
>
> - **Final ATP varies ~5,900× across seeds** (42 → 3,587 · 43 → 1,056 · 44 → 0.61 · 45 → 578). Seed 44 effectively cratered; the system is hovering at the boundary of feasibility on three of four random seeds.
> - **No seed initiated replication**; no seed reached division; mass grew +1.9% then plateaued as amino acids and ATP exhausted.
> - The 6/28 PASS count is a **regression from the 7/28 pre-strip baseline**
>   on a single KP (KP20 metabolite-profile flipped PASS → FAIL at 3.08× tolerance).
> - Bucket-status stability across seeds (28/28, see Cross-seed section below)
>   is **not a sign of biological stability** — it is the natural consequence
>   of all four seeds failing the same KPs for the same reasons. A scorecard
>   that doesn't move when the underlying state varies by orders of magnitude
>   is undersensitive, not robust.
> - Root cause of the AA/ATP plateau is the dead `karr_trna_aminoacylation`
>   process (Tier 0 in the dead-process triage). That gate must close before
>   any wave-3 ensemble can produce a non-fragile baseline.
>
> This scorecard is published as an honest negative-result snapshot of where
> the model stands at wave-2, not as evidence that the model is converged.
> Phase 5 tier-0 / tier-1 enrollment is the prerequisite for the next pass.

## Pre-fix vs Post-wave2

This is the POST-WAVE2 baseline. The earlier `E2_scorecard_post_strip.md`
was the pre-fix baseline on broken chassis_v6 @ ee52141 (allocation-bypass
cascade). Compare KP-by-KP to see which KPs the wave-2 fixes moved.
**KP20 regression** (PASS → FAIL) is the headline delta — wave-2 fixes are
net-additive on plumbing but surfaced a real biology gap on metabolite
profile that the pre-strip baseline was hiding.

## Per-KP detail
| KP | Label | Bucket | Opencell | Karr | rel_err | Status | Disposition |
|---|---|---|---:|---:|---:|---|---|
| KP01 | Growth rate (g/s) | opencell-tooling | 4.42492e-21 | 2.11927e-05 | 1 | FAIL | tolerance exceeded |
| KP02 | Doubling time (s) | validation-and-organism-scaling | NaN | 47186.1 | NA | FAIL | Extractor returned NaN/non-finite value. |
| KP03 | Flux-oracle agreement | opencell-tooling | NA | 0 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP03-FLUX-ORACLE) |
| KP04 | Glucose uptake (PTS) | validation-and-organism-scaling | NA | 2725 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP04-TX_GLCPTS) |
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
| KP15 | DNA-binding occupancy dynamics | biology-beyond-Karr | NA | True | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP15-DNA-OCCUPANCY) |
| KP16 | DNA content doubling | opencell-tooling | 1 | 2 | 0.5 | FAIL | tolerance exceeded |
| KP17 | DNA mass fraction | validation-and-organism-scaling | 0 | 0.1688 | 1 | FAIL | tolerance exceeded |
| KP18 | RNA mass fraction | validation-and-organism-scaling | 0 | 0.0434821 | 1 | FAIL | tolerance exceeded |
| KP19 | Protein mass fraction | validation-and-organism-scaling | 0.0167298 | 0.277002 | 0.9396 | FAIL | tolerance exceeded |
| KP20 | Metabolite concentration profile | karr-known-incomplete | 3.0788 | 1 | 3.079 | FAIL | threshold_max exceeded |
| KP21 | ATP/GTP production-use balance | opencell-tooling | NA | 0 | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP21-ENERGY-LEDGER) |
| KP22 | Energy discrepancy phenotype | karr-known-incomplete | False | True | 1 | FAIL | qualitative boolean mismatch |
| KP23 | Burst-like protein synthesis stats | biology-beyond-Karr | True | True | 0 | PASS | qualitative boolean matched |
| KP24 | mRNA/protein distribution shape | biology-beyond-Karr | True | True | 0 | PASS | qualitative boolean matched |
| KP25 | Gene essentiality accuracy | biology-beyond-Karr | NA | NA | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP25-KO-SWEEP) |
| KP26 | Single-gene disruption phenotype class | biology-beyond-Karr | NA | NA | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP26-KO-CLASS) |
| KP27 | Host adhesion competence | biology-beyond-Karr | NA | True | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP27-HOST-ADHESION) |
| KP28 | Host immune activation cascade | biology-beyond-Karr | NA | True | NA | BLOCKED | Extractor unavailable for emitted schema. (E2-V1_1-KP28-HOST-IMMUNE-CASCADE) |

## Cross-seed comparison (seeds 42-45)

| Seed | Trajectory | PASS | FAIL | BLOCKED |
|---|---|---:|---:|---:|
| 42 | artifacts/ensemble_wave2_20260527_023611/seed_42/trajectory.pkl | 6 | 14 | 8 |
| 43 | artifacts/ensemble_wave2_20260527_023611/seed_43/trajectory.pkl | 6 | 14 | 8 |
| 44 | artifacts/ensemble_wave2_20260527_023611/seed_44/trajectory.pkl | 6 | 14 | 8 |
| 45 | artifacts/ensemble_wave2_20260527_023611/seed_45/trajectory.pkl | 6 | 14 | 8 |

No KP changed PASS/FAIL/BLOCKED status across seeds 42-45; status stability is 28/28.
Largest numeric spread *within a single KP's tolerance band* was KP07 (mRNA short-horizon
stability), from 0.000595 to 0.00227, which remained below the threshold_max target (0.1)
for all four seeds.

**Do not read this as biological stability.** Bucket-status invariance across seeds
co-exists with a ~5,900× spread in final ATP across the same four seeds
(42 → 3,587 · 43 → 1,056 · 44 → 0.61 · 45 → 578). The scorecard's KPs are
either (a) measured before the divergence point, (b) tolerance-banded too
loosely to register seed-44's near-crash, or (c) gated BLOCKED and therefore
not contributing signal at all. KP01 (growth rate) does register the crash
(4.42e-21 g/s, effectively zero) but is already FAIL on the median seed, so
it can't distinguish "fragile" from "broken" at this baseline. Add an
ensemble-divergence canary (proposed: flag any KP whose cross-seed CV
exceeds 10×) before the next wave to make this kind of fragility visible
in the scorecard itself, not just in the raw trajectory pickles.

