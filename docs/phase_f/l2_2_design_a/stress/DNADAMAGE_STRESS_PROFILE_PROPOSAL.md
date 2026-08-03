# DNADamage synthetic mechanism-fidelity profile

**Status:** preregistered, not executed, non-gating.

The local Karr source contains no nonzero calibrated UVB or gamma condition:
the concrete condition fixtures set radiation to zero. Therefore this profile
does **not** claim a biological dose or a cell-phenotype stress response.

It instead defines two source-valid mechanism conditions by injecting only
Karr's existing `UVB_radiation` or `gamma_radiation` substrate. Each value is
derived from `DNADamage.m::calcExpectedReactionRates` and the fixture so the
50-seed x 20-tick cohort has 100 expected pooled events, exactly twice the
existing support floor. Values are frozen in
`DNADAMAGE_SYNTHETIC_MECHANISM_SPEC.json` before any MATLAB execution.

The negative control remains correctly quiescent and cannot pass by
zero-equals-zero. Stimulus conditions must reach Karr support or refuse.
Comparisons are distributional, using Karr-only seed-cluster nulls; exact
claims are limited to directionality, field mapping, bounds and separation
from DNARepair.

This work can support a later `CONDITION_GATED_CANDIDATE` decision. It cannot
change the current DNADamage verdict, unblock L2.5, or support L5 phenotype
claims. Live catalog, registry and evidence-index edits remain serialized and
are not part of this preregistration.
