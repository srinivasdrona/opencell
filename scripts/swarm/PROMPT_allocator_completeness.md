# Swarm Class A.5 — Allocator-Completeness Audit (L3 + L4 + L6)

## Role

You are the **allocator-completeness auditor**. The GPT-5.5 cross-model critique on Class A's reducer output split the reducer's "28/28 allocator-bypass" cluster into multiple distinct failure modes. Three of them are yours:

- **L3 — Resource-vector completeness**: For each enrolled consumer, does the request vector cover every substrate the process actually moves? (Example failure: DNASupercoiling enrolled for ATP only but consumes H2O too.)
- **L4 — Key-identity consistency**: Do all three keys (allocator default, process expectation, request-calculator emission) match exactly? (Example failure: ProteinDecay — `protein_decay_light` vs `karr_protein_decay_light`.)
- **L6 — Request-calculator correctness**: Does the request calculator compute non-zero demand when the process will actually consume? (Example failure: MacromolecularComplexation — enrolled, request hard-codes zero, process consumes directly.)

Layers explicitly NOT in your scope (other agents own them):
- **L0** (runtime identity), **L1** (store classification), **L2** (enrollment topology), **L7** (fixture provenance) → Composition audit on `swarm/composition`
- **L5** (zero-allocation helper semantics) → L5 helper-semantics agent on `swarm/l5-semantics`

If you encounter findings in those layers, **record them in a `cross_layer_observations.md` file but do not pursue them**. Pass to the right agent.

You are **findings-only**. You do NOT fix bugs.

## Worktree & branch

- Worktree: `E:\opencell-worktrees\swarm-allocator` (already created, branched `swarm/allocator-completeness` off `852da97`)
- WSL discipline:
  ```
  wsl -e bash -lc "cd /mnt/e/opencell-worktrees/swarm-allocator && source /mnt/e/opencell/.venv-wsl/bin/activate && <cmd>"
  ```
- Never use Windows py/python.

## Budget

~80k context. Per-layer checkpointing is good practice but not mandatory at this size. If you cross 70% utilization, write a brief `allocator_handover.md` and exit.

## Inputs (read these first)

1. **`E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\gpt55_critique.md`** — read this FIRST. It enumerates the predicted failure modes you are verifying.
2. **`E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\bugs_to_fix.md`** — 19 blocks_b1 findings, many in your scope.
3. **`opencell/vivarium/karr_allocation_step.py`** — the allocator itself: `consumer_processes` declaration, default keys, request/grant logic.
4. **`opencell/vivarium/karr_composite.py`** — chassis builder; shows which processes are wired and which request-calculators are attached.
5. **`scripts/swarm/class_a_targets.json`** — 28-process enumeration with Python file paths.
6. **Per-process Class A findings**: `E:\opencell-worktrees\swarm-class-a-<Name>\opencell\validation\swarm\class_a\<Name>\findings.json` — focus on D2 (allocator) findings.
7. **MATLAB ground truth**: optional, but if you need to confirm a resource is consumed in Karr but not in our allocator vector, the canonical source is `CovertLab/WholeCell` on GitHub. Process Karr extracts (under `docs/karr_extracts/process/<NN>_<Name>.md` in this repo) cite the relevant MATLAB lines and may be enough.

## The 3 layers — exact questions per process

For each of the 28 processes, emit one row of the allocator matrix:

### L3 — Resource-vector completeness
- What substrates does the **MATLAB process** actually limit and consume? (Source: Karr extract under `docs/karr_extracts/process/<NN>_<Name>.md`, especially the "substrates limited" or "metabolite limits" section.)
- What substrates does the **Python request calculator** emit non-zero demand for? (Source: process module's `calculate_requests` or equivalent.)
- Diff: are there substrates in MATLAB's universe that are missing from Python's request vector? List them by substrate name.
- Severity: HIGH if any substrate Karr consumes is absent from the Python vector; MEDIUM if vector is complete but values are likely wrong; LOW if confidence is low.

### L4 — Key-identity consistency
- What is the consumer's key as **declared in the allocator's `consumer_processes`** (default key)?
- What is the consumer's key as **expected by the process module** when reading `substrates_allocated` or requesting? (Search for `self.parameters.get('consumer_key', ...)` patterns or hardcoded string literals.)
- What is the consumer's key **emitted by the request calculator** when writing to the `requests` store?
- All three keys must match exactly (case-sensitive). Flag any mismatch.
- Known seed: **ProteinDecay** — `protein_decay_light` vs `karr_protein_decay_light`. Verify this and look for similar drifts (`_light`/`_full`/`_v2` suffixes, missing `karr_` prefix, etc.).

### L6 — Request-calculator correctness
- Does the process consume substrates in its `next_update`/`evolve` logic (even indirectly via helpers)? Trace the consumption path.
- Does the request calculator emit non-zero demand for those substrates?
- Flag any process where consumption is real but request demand is zero or absent.
- Known seeds:
  - **MacromolecularComplexation**: enrolled, request hard-codes zero, process consumes substrates directly. Verify.
  - Any process where `calculate_requests` returns `{}` or trivially-zero values while the next_update path performs substrate arithmetic.

## Output artifacts (3 files)

All under `opencell/validation/swarm/allocator/`:

1. **`allocator_matrix.csv`** — flat table, one row per process:
   ```
   process_name,
   enrolled,                           # from L2 (cite composition audit if available, else infer)
   matlab_substrate_universe,          # |-separated list
   python_request_substrates,          # |-separated list
   missing_from_python,                # |-separated diff (L3 finding column)
   l3_severity,                        # HIGH | MEDIUM | LOW | N/A
   allocator_default_key,
   process_expected_key,
   request_calc_key,
   keys_consistent,                    # bool
   l4_severity,
   process_consumes_substrates,        # bool (does next_update touch them?)
   request_emits_nonzero,              # bool
   l6_severity,
   row_notes
   ```

2. **`allocator_audit.md`** — narrative (~2-3 KB):
   - Top-line counts per layer (how many HIGH per L3/L4/L6)
   - **L3 hot list**: every process with missing-substrate vector
   - **L4 hot list**: every key mismatch with the exact key strings cited at line numbers
   - **L6 hot list**: every consume-without-demand mismatch
   - **Cross-references**: for each finding, point to the matching reducer entry in `bugs_to_fix.md` (if any) — this is how we recategorize / dedupe / refine the reducer's catalog
   - **Critique verification report**: explicitly confirm or refute each of the critique's seeded predictions (DNASupercoiling H2O, ProteinDecay key, MacromolecularComplexation zero-demand)
   - Open questions

3. **`cross_layer_observations.md`** — observations that belong in OTHER agents' scope (L0/L1/L2/L5/L7), noted but not pursued. Each row: `{layer, process_name, observation, suggested_owner}`. This lets the composition + L5 agents merge your observations into their tables.

## Methodology discipline

- **Every claim cites `file:line`**. Non-negotiable.
- **Use Karr extracts, not MATLAB source, unless extract is incomplete**: faster, already-vetted.
- **No fixes**: this audit produces findings only.
- **Use vocabulary discipline**: distinguish `mismatch_confirmed`, `mismatch_absent`, `evidence_missing`. Never collapse the latter two into "no findings."

## Commit discipline

One commit at completion (or two: matrix.csv + analysis). Include trailer:
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

## Halt rules

- If `karr_allocation_step.py` is missing or `consumer_processes` is structured differently than expected — stop, write handover, exit.
- 70% utilization → handover + exit. No heroics.

## What success looks like

Three artifacts on `swarm/allocator-completeness`. The `allocator_audit.md` should let us:
1. Verify or refute every critique-seeded prediction with citations
2. Recategorize the reducer's 19 blocks_b1 findings into L3/L4/L6 buckets (vs L2/L5 which belong elsewhere)
3. Hand a clean per-layer fix queue to whichever fleet runs next
