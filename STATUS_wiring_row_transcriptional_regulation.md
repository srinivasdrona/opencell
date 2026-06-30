# STATUS - wiring row for TranscriptionalRegulation

What I authored:
- `data/schemas/per_process_wiring/TranscriptionalRegulation.yaml`
- A schema-valid per-process wiring row for `TranscriptionalRegulation` that captures the current OC port, the available Karr extract, allocator bypass mode, direct TF inputs, empty substrate stoichiometry, dependency direction, ordering notes, source anchors, provenance, and known deviations.

What I kept conservative:
- I treated the raw MATLAB `.m` file as absent in this checkout and used the checked-in Karr extract plus the process design notes as the local source surrogate.
- I left `consume_stoichiometry` and `produce_stoichiometry` empty because this process is regulatory-only and does not move material substrates in the current OC port.
- I set allocator mode to `bypass` on both sides because the OC implementation reads `protein.counts` and `complex.counts` directly and does not expose a request-calculator path.

Uncertainties:
- I could not verify the raw MATLAB method bodies directly because the canonical `.m` file is not present in this worktree snapshot.
- I could not identify any process-specific ordering rule beyond the global `tRNAAminoacylation < Translation` constraint in `Simulation.evolveState`.
- The schema in this checkout does not expose separate structured provenance fields for `last_audited`, `audited_by`, `oc_commit_sha`, or the referenced file lists, so I recorded those details in the allowed provenance notes field instead.

Observed divergences:
- OC skips Karr's documented t=0 pre-binding sweep and instead seeds `tf_binding` from the first `next_update` tick.
- OC has no allocator request surface for this process, so the row stays bypass-mode rather than inventing a request formula.
- The row uses extract/design-doc anchors because the raw MATLAB source file is missing locally.

Validation:
- I have not run the YAML schema validator yet in this message.
- Next step is to run the repo's YAML parse check and then commit the row and this status file.
