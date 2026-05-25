# Swarm Class A.5 — Composition / Fixture-Contract Audit

## Role

You are the **composition auditor**. Class A (28 per-process audits) finished and a GPT-5.5 cross-model critique identified a missing audit layer: the per-process agents could not see the **chassis-wide composition contract** — runtime identity, store classification, allocator enrollment topology, and fixture provenance. That seam is yours.

You are **findings-only**. You do NOT fix bugs. You enumerate the contract surface across all 28 processes and produce one master table + an analysis writeup.

## Worktree & branch

- Worktree: `E:\opencell-worktrees\swarm-composition` (already created, branched `swarm/composition` off `852da97`)
- WSL discipline: every test/python invocation goes through the WSL venv:
  ```
  wsl -e bash -lc "cd /mnt/e/opencell-worktrees/swarm-composition && source /mnt/e/opencell/.venv-wsl/bin/activate && <cmd>"
  ```
- Never use Windows py/python.

## Critical context windows + handover protocol

**Budget**: ~200k context. You MUST proactively self-monitor and produce a handover doc at **~75% utilization (~150k tokens consumed)**.

**Per-layer checkpointing** (mandatory, not optional):

After completing each layer (L0, L1, L2, L7), write the partial JSON IMMEDIATELY to disk:
```
opencell/validation/swarm/composition/composition_l0.json
opencell/validation/swarm/composition/composition_l1.json
opencell/validation/swarm/composition/composition_l2.json
opencell/validation/swarm/composition/composition_l7.json
```

This means: if you die mid-flight, the next agent can resume from the last completed layer. Do NOT batch all four layers into a final dump.

**Handover doc** (if you cross 75% utilization):
- Write `opencell/validation/swarm/composition/composition_handover.md`
- Contents: what layers are done, what processes within current layer are done, exact resume instructions, any open questions, any files you opened that the next agent should re-open.
- Then commit and exit cleanly. Do NOT try to push through to completion at 90%+ — you will die mid-output and lose the analysis.

## The 4 layers you audit

For each of the 28 Karr processes (list in `scripts/swarm/class_a_targets.json` under `.processes`), answer these questions and emit one row of the composition table:

### L0 — Runtime identity
- Which Python class is **actually instantiated** by `build_karr_chassis_v6` for this process? (Hint: the entry point lives in `opencell/vivarium/karr_composite.py`; look for the v6 chassis builder. Some processes have multiple variants e.g. `karr_translation.py`, `karr_translation_v2.py`, `karr_translation_v3.py`; v6 may promote a specific variant.)
- Which Python file does that class live in? (Full path from repo root.)
- Compare against the Class A audit target for this process (`scripts/swarm/class_a_targets.json` → `.processes[].py`). Are they the **same class** or did Class A audit a different one?
- If different: flag as `RUNTIME_IDENTITY_MISMATCH` and record both classes.

### L1 — Store classification
- What stores does this process declare in its `ports_schema` / `topology`?
- For each store, classify it as one of:
  - `resource` — allocator-governed (substrate counts, allocator request/grant stores)
  - `state` — process-owned mutable biology state (RNA counts, protein counts, chromosome positions)
  - `telemetry` — writer-only diagnostic (fluxes, growth rates, monitors)
- The classification rule: if any allocator or other process **reads** this store as input to a decision, it is `resource` or `state`. If only this process writes and only humans/canary monitors read, it is `telemetry`.
- Flag mis-classifications (e.g. a store that looks like telemetry but is actually read by an allocator request calculator).

### L2 — Allocator enrollment topology
- Is this process registered in the allocation step's `consumer_processes` (or equivalent)? (Source: `opencell/vivarium/karr_allocation_step.py` + chassis composition in `karr_composite.py`.)
- If enrolled: what is its **consumer key** in the allocator? What key does the process itself expect (in its request calculator + grant reader)?
- Do all three keys (allocator default, process expectation, request-calculator emission) **match exactly**? Flag mismatches.
- If not enrolled: does the process **read or write substrate-like stores anyway** (direct global writes, bypassing the allocator)? Flag as `ENROLLMENT_GAP_WITH_SUBSTRATE_TRAFFIC` if yes.

### L7 — Fixture provenance
- For this process, what is the authoritative t=0 initial state source? (Hint: look at `karr_composite.py` for initial-state builders and at fixture loaders.)
- What fixture file corresponds to this process? (From `class_a_targets.json` → `.processes[].fixture_mat`; physical path under `opencell/karr_extracts/fixtures/` or similar — locate it.)
- Does the fixture expose **before/after tick I/O** suitable for replay? Spot-check the .mat structure: do you see `n_ticks > 1`, `inputs`, `outputs` keyed by store name? Or is it a single-snapshot fixture (`n_ticks=1, inputs=0, outputs=0`)? This was the Translation/DNARepair replay finding from Class A.
- Flag fixtures that are single-snapshot-only — they cannot support replay-fidelity audits.

## Output artifacts (5 files)

All under `opencell/validation/swarm/composition/`:

1. **`composition_l0.json`** — list of {process_name, runtime_class_in_chassis, runtime_file, class_a_audited_class, class_a_audited_file, mismatch: bool, notes}. Written after L0 completes.

2. **`composition_l1.json`** — list of {process_name, stores: [{store_name, declared_type, classification: resource|state|telemetry, classification_evidence, classification_confidence}], misclassifications: [...]}. Written after L1 completes.

3. **`composition_l2.json`** — list of {process_name, enrolled: bool, allocator_default_key, process_expected_key, request_calc_key, keys_consistent: bool, substrate_traffic_outside_allocator: bool, notes}. Written after L2 completes.

4. **`composition_l7.json`** — list of {process_name, t0_initializer_source, fixture_file_path, fixture_n_ticks, fixture_has_io_channels, replay_capable: bool, notes}. Written after L7 completes.

5. **`composition_audit.md`** — narrative report (~2-3 KB) covering:
   - Top-line counts: how many processes per layer have findings
   - **L0 hot list**: every process where audited-class ≠ runtime-class. This invalidates the corresponding Class A finding's biology comparisons.
   - **L1 hot list**: every misclassified store (especially "observability-power" findings from Class A that turn out to be telemetry-by-design).
   - **L2 hot list**: every enrollment gap + key-identity mismatch, cross-referenced against `bugs_to_fix.md` from the reducer.
   - **L7 hot list**: every process whose fixture is single-snapshot, blocking replay-fidelity audits.
   - **Implications**: which entries in the reducer's `bugs_to_fix.md` are now invalidated or recategorized?
   - **Open questions / unresolved**

Plus **`composition_table.csv`** — flat join of all 4 JSON files, one row per process, columns:
`process_name, runtime_file, runtime_class, l0_mismatch, store_count, telemetry_count, resource_count, state_count, l1_misclass_count, enrolled, keys_consistent, substrate_traffic_outside, fixture_path, fixture_n_ticks, replay_capable`

## Critique-seeded priority cases (verify these first)

The GPT-5.5 cross-model critique (committed to `swarm/reducer` as `gpt55_critique.md`, also reachable at `E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\gpt55_critique.md` — READ THIS FIRST) identified specific concrete cases. **Verify them with code citations as your first pass per layer**; treat them as predictions of the audit, not assumptions of it. If a prediction is **refuted by code**, that itself is a high-value finding — record it.

### Predicted L0 mismatches (runtime identity)
- **Translation**: Class A audited `KarrTranslationProcess` in `karr_translation.py`; chassis v6 reportedly promotes `karr_translation_v3`. Verify which class `build_karr_chassis_v6` instantiates. If true, this invalidates the biology comparisons in Translation/findings.json.
- Sweep ALL 28 processes for similar wrapper-vs-runtime drift. The critique only inspected Translation but the pattern may repeat (e.g. `_v2`, `_v3`, `_light`, `_legacy` siblings).

### Predicted L1 misclassifications (store classification)
- **Metabolism `metabolic_reaction` store**: Class A flagged it under "observability-consumer-power" (HIGH severity, unpowered read port). Critique claim: it is **writer-only telemetry by design**, not a biological wiring defect. Classify carefully — does any allocator/process actually READ this store as input to a decision, or is it pure diagnostic emission?
- Apply the same store-by-store re-classification to every HIGH severity "unpowered consumer" / "read-port-unpowered" finding in the reducer's `bugs_to_fix.md`. Many may turn out to be telemetry.

### Predicted L2/L3/L4 cases (allocator enrollment + keys)
The critique partitions the reducer's "28/28 allocator-bypass" into 4+ distinct failure modes. Verify each:
- **DNADamage**: no `substrates`, `requests`, or `substrates_allocated` ports at all. Absent from allocator enrollment. (L2: enrollment gap with substrate traffic.)
- **Metabolism**: writes substrate deltas directly, not in `consumer_processes`. (L2.)
- **Transcription, Translation**: emit substrate drains, lack allocator enrollment. (L2.)
- **DNASupercoiling**: enrolled for ATP only, but MATLAB limits/consumes H2O too. (L3: partial resource vector — though L2 enrollment is intact. Record on the L2 row as `substrate_traffic_outside=true (H2O)` and pass detail to allocator-completeness agent.)
- **ProteinDecay**: allocator default key is `protein_decay_light` while process/request-calculators use `karr_protein_decay_light`. (L4 key mismatch — also pass to allocator-completeness, but record on your L2 row.)
- **MacromolecularComplexation**: enrolled, but request calculator hard-codes zero demand while the process consumes substrates directly. (Hybrid L2/L6 — record enrollment as `true`, flag `substrate_traffic_outside=true` because de-facto consumption bypasses the zero-demand declaration.)
- **ChromosomeSegregation, Cytokinesis, DNARepair, Replication, ReplicationInitiation, tRNAAminoacylation**: zero-allocation fallback via `_allocated_or_state` helper. (L5 helper-semantics — this is the L5 agent's territory, NOT yours. If you see calls to `_allocated_or_state` (or equivalent), record on your L2 row as `helper_semantics_dependency: true` and move on.)

### Predicted L7 cases (fixture provenance)
- **Translation**: real monomer-default mismatch at t=0; fixture loads with `n_ticks=1, inputs=0, outputs=0` (NOT replay-capable).
- **DNARepair**: explicitly "no findings" for D5 with fixture-aligned tracked-substrate values. The "no findings" verdict is NOT evidence of absence — it carries positive fixture evidence. Flag your L7 row with a `had_fixture_evidence_despite_no_findings: true` column if applicable.
- **Metabolism**: the D5 mismatch the reducer aggregated is isolated to a **standalone M1 smoke harness**, NOT the v5/v6 chassis path. Verify which t=0 initializer is canonical and record both paths.
- Sweep ALL 28 fixtures for the `n_ticks=1, inputs=0, outputs=0` pattern — this is the replay-blocker the critique calls out as a precondition issue.

### Vocabulary discipline (avoid Class A's aggregation bug)
The reducer aggregated "D5 evidence exists" into "D5 mismatch exists" — too coarse. In your audit, distinguish:
- `mismatch_confirmed` (fixture value ≠ runtime default, both observed)
- `mismatch_absent` (fixture value == runtime default, both observed) — POSITIVE evidence, not "no findings"
- `evidence_missing` (cannot check — fixture absent, channel absent, or runtime path unidentified)

Use these in your L7 rows explicitly. Never collapse the latter two into "no findings."

## Reference inputs (read these)

- `scripts/swarm/class_a_targets.json` — process name + Python file + fixture file enumeration (28 entries)
- `opencell/vivarium/karr_composite.py` — chassis builder, contains `build_karr_chassis_v6` and store wiring
- `opencell/vivarium/karr_allocation_step.py` — allocator code with `consumer_processes` and request/grant logic
- `E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\bugs_to_fix.md` — reducer's 19 blocks_b1 findings (the L0/L1/L2 hot lists need to cross-reference this)
- `E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\swarm_report.md` — reducer's narrative
- Class A per-process findings.json (under each `swarm/class-a/<Name>` worktree at `opencell/validation/swarm/class_a/<Name>/findings.json`) — when checking a specific process's audited-class identity, read its findings.json D1 entry.
- Karr MATLAB source on GitHub: `CovertLab/WholeCell` (you may fetch via `gh` or git clone read-only if you need to cross-check, but fixtures are the binding ground truth).

## Methodology discipline

- **Cite line numbers**: every claim in `composition_audit.md` must cite `file:line` (e.g. `karr_composite.py:142`). This is non-negotiable; the Class A audits set this bar.
- **No biology re-audits**: you are not re-doing D1-D5 from Class A. You are auditing the chassis composition contract that Class A could not see. Stay in your lane.
- **Spot-check fixtures with code, not assumption**: when checking `fixture_n_ticks`, actually `scipy.io.loadmat()` the file in WSL python and report the structure. Do not infer from filename or class-a notes.
- **Confidence levels**: HIGH for code-traceable claims (citation present), MEDIUM for cross-referenced inference, LOW for "appears to be" judgments. Default to MEDIUM if uncertain.

## Commit discipline

- One commit per checkpoint layer is OK (`composition: L0 runtime-identity sweep complete (28/28)`), or one final commit for all artifacts — your call.
- Always commit before exiting (even on handover).
- Trailer: `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

## Halt rules

- If `composition_l0.json` shows >5 RUNTIME_IDENTITY_MISMATCH cases — stop the audit, write the handover with what you have, flag this as a project-level concern. >5 means Class A's biology audits are widely invalid and we need to re-plan before continuing.
- If you cannot locate `build_karr_chassis_v6` or the allocator file — stop immediately, write a handover stating what you tried, exit.
- If you hit 75% context — stop, handover, exit. No heroics.

## What success looks like

5 artifacts committed on `swarm/composition`. `composition_audit.md` lets the operator + Copilot revise `bugs_to_fix.md` with confidence — knowing exactly which findings are real, which are misclassified, and which are aimed at the wrong class. This unblocks Track-A scoping and narrows Class B.
