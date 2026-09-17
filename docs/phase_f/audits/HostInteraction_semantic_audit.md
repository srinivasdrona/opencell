# HostInteraction Semantic Audit

Process: `HostInteraction`
Authority: primary `HostInteraction.m`, current `karr_host_interaction.py`, and
chassis-v6 topology.
Scope: strict documentation completeness.

## Current implementation status

Current OC is a literal boolean port, not the retired stochastic
aggregate-adhesion approximation. MATLAB's resource request is an all-zero
vector over an empty substrate list. OC's absent request-calculator is therefore
a benign structural bypass, not a behavioral deviation. Initialization still
differs: MATLAB evaluates the cascade before tick 0, while OC v6 starts from
false schema defaults.

## Claim table

| Claim ID | Category | Documented claim and evidence | Verdict |
|---|---|---|---|
| HI-S1-01 | S1 | The consume set is empty on both sides; MATLAB declares no substrate WIDs and OC emits no substrate delta. | VERIFIED |
| HI-S2-01 | S2 | No fabricated consume path is documented. | VERIFIED |
| HI-S3-01 | S3 | The produce set is empty on both sides; all outputs are host booleans. | VERIFIED |
| HI-S4-01 | S4 | Adherence is the literal conjunction of all terminal-organelle and adhesin counts (`HostInteraction.m:274-279`; `karr_host_interaction.py:195-198`). | VERIFIED |
| HI-S4-02 | S4 | TLR1/2/6, NF-kB, and inflammatory-response formulas match the MATLAB boolean cascade (`HostInteraction.m:281-302`; OC `:200-217`). | VERIFIED |
| HI-S5-01 | S5 | There is no substrate compartment-routing surface. OC writes the six booleans to `cell` and reads required counts from `protein.counts`. | VERIFIED |
| HI-S5-02 | S5 | For this zero-request process, Karr's `this.enzymes` is unpartitioned; the row documents why OC's raw shared protein counts are the equivalent input surface. | VERIFIED |
| HI-S6-01 | S6 | MATLAB defines `calcResourceRequirements_Current` but returns `zeros(size(this.substrates))` (`HostInteraction.m:265-268`); OC omits the hook. Resource behavior is identical. | VERIFIED |
| HI-S6-02 | S6 | Neither MATLAB nor OC has a HostInteraction-specific scheduler edge; the old `soft_after: TerminalOrganelleAssembly` claim has been removed. | VERIFIED |
| HI-S6-03 | S6 | MATLAB `initializeState` calls `evolveState` (`HostInteraction.m:259-263`), and the measured active trace has all six booleans true in `states_before` tick 0 (`HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md:288-304`). OC ports default all six to false and v6 does not precompute them, correcting them only on the first process tick (`karr_host_interaction.py:132-173`). | CODE_DEVIATES |

## Aggregate counts

- VERIFIED: 9
- ROW_WRONG: 0
- CODE_DEVIATES: 1
- MISSING: 0

## Open implementation deviation

- Tick-0 host booleans are false in OC v6 instead of MATLAB's initialized
  cascade result.

## Documentation corrections completed

- Replaced the retired stochastic approximation description with the literal
  boolean cascade.
- Classified zero resource demand as benign/equivalent.
- Added the distinct initialization mismatch.
- Removed the nonexistent executable ordering constraint.
- Corrected MATLAB method symbols in source anchors.
