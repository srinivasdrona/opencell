# DNADamage synthetic mechanism-fidelity profile

**Status:** preregistered predictions frozen (2026-06-14); OC-side canary
EXECUTED 2026-08-05 (N=50 seeds x M=20 ticks); still non-gating.

## Execution update (2026-08-05)

The canary described below has been executed:
`scripts/dna_damage_mechanism_canary.py` -> checked-in result
`DNADAMAGE_MECHANISM_CANARY_RESULT.json`. It runs the real
`KarrDNADamageProcess.next_update` across the frozen 50x20 design under
`no_stimulus`, `uvb_mechanism`, and `gamma_mechanism`, and compares OC's
empirical firing/payload against the Karr-analytical (fixture-derived, never
fabricated) expectation for every `primary_projection` channel in the
catalog. Result: both stimulus conditions verdict `MECHANISM_MISMATCH` (OC's
lumped per-kind Poisson rate model diverges sharply from Karr's per-reaction
`calcExpectedReactionRates` formula -- UVB overfires ~988/1000 pooled ticks
vs an analytical expectation of ~97; gamma underfires 0/1000 vs an
analytical expectation of ~96), `no_stimulus` stays `NOT_APPLICABLE` (never
scored as a pass), and `hollidayJunctions` is reported
`NOT_GATEABLE_MISSING_OC_CHANNEL` (OC's `ports_schema()` does not wire it).
This is real, non-trivial, source-backed OC-side evidence -- it is still
explicitly **not** a claim about the biological L2.2 event-class gate, which
remains `MISSING_EVIDENCE` in `evidence_index.json` because no
empirically-executed Karr trace exists under any stimulus condition (no
MATLAB toolchain available in this environment). See the result JSON's
`biological_l2_2_event_class_gate` for the precise required extraction
contract. `PROCESS_CATALOG.yaml`'s DNADamage `notes`/`blocked_on` fields have
been corrected accordingly (the prior "L2.2 GREEN. blocked_on cleared." note
was a zero==zero quiescent-replay artifact and has been retracted).

The local Karr source contains no nonzero calibrated UVB or gamma condition:
the concrete condition fixtures set radiation to zero. Therefore this profile
does **not** claim a biological dose or a cell-phenotype stress response.

It instead defines two source-valid mechanism conditions by injecting only
Karr's existing `UVB_radiation` or `gamma_radiation` substrate. Each value is
derived from `DNADamage.m::calcExpectedReactionRates` and the fixture so the
50-seed x 20-tick cohort has 100 expected pooled **damaged-site events**.
The gate's repeated-firing count is seed-tick incidence, for which the
preregistered expectations are 97.22 UVB and 96.02 gamma fire ticks
(1.94x/1.92x the floor). Values are frozen in
`DNADAMAGE_SYNTHETIC_MECHANISM_SPEC.json` before any MATLAB execution.

The negative control remains correctly quiescent and cannot pass by
zero-equals-zero. Stimulus conditions must reach Karr support or refuse.
Comparisons are distributional, using Karr-only seed-cluster nulls; exact
claims are limited to directionality, field mapping, bounds and separation
from DNARepair. Per-kind incidence is gateable only for preregistered kinds
whose own expected support clears the floor; unsupported rare kinds remain
descriptive rather than becoming zero-equals-zero passes. Gamma may write
`damagedBases` or `strandBreaks`; UVB writes `intrastrandCrossLinks`.
A fired tick is defined as a **net nnz increase** in those allowed fields;
an in-place subtype conversion at an existing site is deliberately not a
fire.

This work can support a later `CONDITION_GATED_CANDIDATE` decision. It cannot
change the current DNADamage verdict, unblock L2.5, or support L5 phenotype
claims. Live catalog, registry and evidence-index edits remain serialized and
are not part of this preregistration.
