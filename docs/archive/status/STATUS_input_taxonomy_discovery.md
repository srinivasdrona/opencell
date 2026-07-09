## Input Taxonomy Discovery Status

- Started discovery from real MATLAB source on 2026-07-09.
- Read `SESSION_CONTEXT.md`; this task is reconnaissance-only with no process/spec/fixture edits.
- Confirmed 28 target process classes under `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/`.
- Confirmed base taxonomy machinery in `Process.m`:
  - `optionNames__`, `fixedConstantNames__`, `fittedConstantNames__`, `localStateNames__` are abstract constant annotations.
  - dependent getters expand `optionNames`, `fixedConstantNames`, `fittedConstantNames`, and `localStateNames`.
  - `storeObjectReferences` wires base simulation state objects: `Geometry`, `Stimulus`, `Metabolite`, `Rna`, `ProteinMonomer`, `ProteinComplex`.
- Confirmed inherited source needed for faithful taxonomy recovery:
  - `ReactionProcess.m` computes default `stimuliWholeCellModelIDs`, `substrateWholeCellModelIDs`, and `enzymeWholeCellModelIDs` from KB reaction matrices.
  - `ChromosomeProcessAspect.m` appends the `Chromosome` state via `storeObjectReferences`.
- Current extraction plan:
  - Parse per-process property assignments plus `initializeConstants` overrides for stimuli/substrates/enzymes.
  - Compute final `localStateNames` / constant-name lists from base getters plus subclass `__` constants.
  - Derive per-process global state names from `Process.m` base state wiring, subclass `simulation.state(...)` calls, and `ChromosomeProcessAspect` usage.
  - Emit JSON + markdown matrix with real `file:line` evidence for every category.

- Current source-derived counts:
  - substrates: LITERAL=16, KB_COMPUTED=12
  - enzymes: LITERAL=19, KB_COMPUTED=9
  - stimuli: LITERAL=27, KB_COMPUTED=1
- Wrote deliverables: `docs/phase_f/karr_input_taxonomy.json` and `docs/phase_f/KARR_INPUT_TAXONOMY.md`.
- Final verification:
  - 28 process entries present in the JSON.
  - No category fell through to `declared: false`.
  - Part C captures every KB_COMPUTED substrate/enzyme case with `origin_expression` and resolvability verdicts.
  - Ambiguous parse entries unresolved: 0.
