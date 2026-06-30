# STATUS: HostInteraction wiring row

Authored `data/schemas/per_process_wiring/HostInteraction.yaml` for the Karr HostInteraction process.

What it captures:
- Process identity and method correspondence for `HostInteraction.m` vs `opencell/vivarium/karr_host_interaction.py`
- Allocator mode, with Karr marked as allocation-capable and current OC marked as bypass
- Empty substrate stoichiometry / compartment routing, because HostInteraction has no substrate WIDs
- Dependency edges on the terminal-organelle and protein pipeline inputs that the OC port actually reads
- Source anchors for the MATLAB extract, the OC module, and the chassis wiring
- Provenance details, including the audit date, commit SHA, fixture files, and the mirror path used for the missing local `.m`

Main uncertainty:
- The canonical local MATLAB file path was absent from this worktree, so I used the upstream mirror plus the checked-in extract doc for line anchoring.
- `kb_version` was not obvious from the current source, so the row records it as `unknown`.

Observed divergence:
- The current OC port is intentionally Karr-light. It models stochastic aggregate adhesion/unbinding and emits `cell.host_adhesion_strength` / `cell.host_attached`, rather than reproducing the full MATLAB boolean cascade over `isBacteriumAdherent`, `isTLRActivated`, `isNFkBActivated`, and `isInflammatoryResponseActivated`.

Validation pending:
- YAML schema check still needs to be run after this write.
