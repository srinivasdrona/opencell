# TerminalOrganelleAssembly Semantic Audit

Process: `TerminalOrganelleAssembly`
Authority: primary `TerminalOrganelleAssembly.m`, current
`karr_terminal_organelle_assembly.py`, and chassis-v6 topology.
Scope: exhaustive eight-protein documentation.

## Current implementation status

MATLAB repeatedly transfers the **full** eligible unincorporated compartment
counts into incorporated compartments until no further localization reaction
can fire. OC now operates on the same authoritative compartmental
ProteinMonomer state, evaluates the incorporated and unincorporated requirement
planes in their source order, and applies the full-count fixed-point transfer.
The former activity gate, assembled counters, target cap, generic compartment
keys, and `trace_hint` path have been removed.

## Claim table

| Claim ID | Category | Documented claim and evidence | Verdict |
|---|---|---|---|
| TOA-S1-01 | S1 | The row lists all eight unincorporated component WIDs as potential consumes; this matches the primary MATLAB substrate set (`TerminalOrganelleAssembly.m:124-140`). | VERIFIED |
| TOA-S2-01 | S2 | Each listed WID is read from and written to the authoritative mature `(WID, compartment)` state (`karr_terminal_organelle_assembly.py:238-326`). | VERIFIED |
| TOA-S3-01 | S3 | The produce list is exhaustive for the same eight WIDs in their incorporated projection. | VERIFIED |
| TOA-S4-01 | S4 | The row now states MATLAB's full-count transfer and fixed-point `while` loop accurately (`TerminalOrganelleAssembly.m:316-337`). | VERIFIED |
| TOA-S4-02 | S4 | OC derives the 8x2 incorporated/unincorporated view from `protein.compartment_counts.mature`; TOA owns no private state, matching Karr's `Process.m` copy-from/copy-to contract. | VERIFIED |
| TOA-S4-03 | S4 | OC transfers the complete eligible unincorporated count and repeats until no reaction can progress; constructed multi-copy and three-hop tests distinguish this from +1 and single-pass implementations. | VERIFIED |
| TOA-S4-04 | S4 | OC maps `localizationReactions(:,:,1)` to incorporated requirements and `(:,:,2)` to unincorporated requirements; the planted plane-swap canary fails. | VERIFIED |
| TOA-S5-01 | S5 | MATLAB and OC both route cytosol/membrane into terminal-organelle cytosol/membrane using biological `c/m/tc/tm` identities. | VERIFIED |
| TOA-S5-02 | S5 | Chassis-v6 maps TOA's sole `protein` port to the shared authority; no orphan substrate, cell, enzyme, or trace-hint port remains. | VERIFIED |
| TOA-S6-01 | S6 | MATLAB's current request is all zeros and OC omits the hook. The row correctly treats this as a benign structural/resource-equivalent difference, not the assembly defect. | VERIFIED |

## Aggregate counts

- VERIFIED: 10
- ROW_WRONG: 0
- CODE_DEVIATES: 0
- MISSING: 0

## Open implementation deviations

None in the audited TerminalOrganelleAssembly surface.

## Documentation corrections completed

- Added the previously omitted three WIDs, making consume/produce/bypass lists
  exhaustive.
- Corrected “one count” wording to MATLAB's full-pool fixed-point behavior.
- Distinguished the actual assembly/topology deviations from the benign
  zero-request allocator shape.
- Replaced stale trace-hint/fallback anchors with the authoritative
  compartment-state and fixed-point implementation.
- Added the requirement-plane orientation claim exposed by the prewritten
  inversion test.
