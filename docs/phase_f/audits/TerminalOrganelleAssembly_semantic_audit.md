# TerminalOrganelleAssembly Semantic Audit

Process: `TerminalOrganelleAssembly`
Authority: primary `TerminalOrganelleAssembly.m`, current
`karr_terminal_organelle_assembly.py`, and chassis-v6 topology.
Scope: exhaustive eight-protein documentation.

## Current implementation status

MATLAB repeatedly transfers the **full** eligible unincorporated compartment
counts into incorporated compartments until no further localization reaction
can fire. Current OC instead drives `protein.activity`-gated assembled counters.
It also has a separate `trace_hint.substrates_next` path and a one-copy fallback
substrate path; chassis-v6 does not connect those substrate/trace-hint ports.

## Claim table

| Claim ID | Category | Documented claim and evidence | Verdict |
|---|---|---|---|
| TOA-S1-01 | S1 | The row lists all eight unincorporated component WIDs as potential consumes; this matches the primary MATLAB substrate set (`TerminalOrganelleAssembly.m:124-140`). | VERIFIED |
| TOA-S2-01 | S2 | Each listed WID has a real OC trace-hint/fallback substrate-delta path (`karr_terminal_organelle_assembly.py:357-401`). | VERIFIED |
| TOA-S3-01 | S3 | The produce list is exhaustive for the same eight WIDs in their incorporated projection. | VERIFIED |
| TOA-S4-01 | S4 | The row now states MATLAB's full-count transfer and fixed-point `while` loop accurately (`TerminalOrganelleAssembly.m:316-337`). | VERIFIED |
| TOA-S4-02 | S4 | OC assembly state is based on activity gates and coarse assembled counters, not MATLAB's live two-column substrate matrix (`karr_terminal_organelle_assembly.py:304-355,403-447`). | CODE_DEVIATES |
| TOA-S4-03 | S4 | OC applies a trace-hint target delta when supplied, otherwise at most one copy per WID in the fallback; neither is MATLAB's autonomous full-count fixed-point transfer (`karr_terminal_organelle_assembly.py:357-401`). | CODE_DEVIATES |
| TOA-S5-01 | S5 | MATLAB routes cytosol/membrane to terminal-organelle cytosol/membrane. OC preserves two projected keys but loses the biological terminal-organelle labels (`compartment_1 -> compartment_0`). | CODE_DEVIATES |
| TOA-S5-02 | S5 | Chassis-v6 maps only `protein` and `cell`; the declared `substrates` and `trace_hint` paths are not connected (`karr_composite.py:2195-2198`). | CODE_DEVIATES |
| TOA-S6-01 | S6 | MATLAB's current request is all zeros and OC omits the hook. The row correctly treats this as a benign structural/resource-equivalent difference, not the assembly defect. | VERIFIED |

## Aggregate counts

- VERIFIED: 5
- ROW_WRONG: 0
- CODE_DEVIATES: 4
- MISSING: 0

## Open implementation deviations

- Activity/assembled abstraction instead of substrate-matrix-derived assembly.
- Trace-hint/one-copy substrate behavior instead of autonomous full-count
  fixed-point transfer.
- Chassis-v6 does not connect the substrate or trace-hint path.
- Terminal-organelle compartment labels are projected to generic keys.

## Documentation corrections completed

- Added the previously omitted three WIDs, making consume/produce/bypass lists
  exhaustive.
- Corrected “one count” wording to MATLAB's full-pool fixed-point behavior.
- Distinguished the actual assembly/topology deviations from the benign
  zero-request allocator shape.
