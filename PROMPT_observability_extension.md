# Phase E.2 Follow-up — Observability Extensions for 5 Tractable BLOCKED KPs

You are a Codex session. Read `SESSION_CONTEXT.md` first (hard rules apply).

## Token budget
**~50k**. Five focused observable extensions + extractor unblocks + scorecard re-run. Commit per KP (5 expected commits + 1 final scorecard regen = 6 commits).

## Context (READ FIRST)
- E.2 just landed on main: `docs/phase_e/E2_scorecard.md` shows **6/28 PASS, 9 FAIL, 13 BLOCKED**.
- 13 BLOCKED rows are NOT model failures — they are "extractor unavailable for emitted schema": the chassis doesn't currently expose the observable.
- A separate Codex session (Bucket A: allocation-consumer enrollment) is fixing the cascade in parallel on a sibling worktree. **DO NOT touch** `karr_rna_decay.py`, `karr_host_interaction.py`, or the `KARR_ALLOCATION_CONSUMERS` registry inside `karr_composite.py`. Your edits to `karr_composite.py` are limited to topology wiring for new observables.

## In-scope KPs (5)

| KP | Label | Karr reference | What to emit | Likely source process |
|---|---|---|---|---|
| KP13 | Cytokinesis duration (s) | (computed from event timestamps) | `cytokinesis_start_tick_s`, `cytokinesis_complete_tick_s` (or `cytokinesis_duration_s`) | `karr_cytokinesis.py` |
| KP17 | DNA mass fraction | (sum DNA polymer mass / total dry mass) | `dna_mass_g` aggregator | DNA / replication state aggregator |
| KP18 | RNA mass fraction | 0.0434821 | `rna_mass_g = sum(rna_counts[i] * mw_rna[i])` | aggregator over RNA state |
| KP19 | Protein mass fraction | 0.277002 | `protein_mass_g = sum(protein_counts[i] * mw_protein[i])` | aggregator over protein state |
| KP20 | Metabolite concentration profile | (snapshot) | per-species metabolite pool dict at each tick | aggregator over metabolism state |

For each KP, the deliverable is:
1. Emit the observable from an existing process or via a thin aggregator step (do NOT rewrite biology).
2. Update `opencell/validation/phenotype_extractors.py` to consume the new emit.
3. In `opencell/validation/phenotype_registry.py`, flip the row's BLOCKED disposition: extractor now produces a value, status becomes PASS/FAIL based on tolerance.

## Hard rules
- Narrow pytest in the inner loop (`pytest -x tests/validation/test_e2_phenotype_scorecard.py` and per-process tests). ONLY full suite after final commit.
- Do NOT modify biology. You are exposing existing state, not changing dynamics. If an MW table is missing, source it from `data/karr_fixtures/karr_native_m2.json` (RNA) or `karr_native_m3.json` (protein) — same source the existing processes use.
- For aggregator steps, model them as `vivarium.core.Step` (read-only, no state mutation) wired in the topology. Run them AFTER all biology processes per tick.
- **Out of bounds** (this is Bucket A's territory):
  - `opencell/vivarium/karr_rna_decay.py`
  - `opencell/vivarium/karr_host_interaction.py`
  - The `KARR_ALLOCATION_CONSUMERS` constant in `karr_composite.py` (you may touch other sections of that file, e.g., topology wiring for new aggregator Steps)
- **Out of scope for this turn** (will be handled separately):
  - KP15 DNA-OCCUPANCY (biology-beyond-Karr, needs new TF/promoter modeling)
  - KP21 ENERGY-LEDGER (overlaps with Bucket A ATP-tracking work)
  - KP25/26 KO-SWEEPS (need KO harness, not a chassis emit)
  - KP27/28 HOST-* (touches host_interaction.py, owned by Bucket A)
  - KP03/04 FLUX-ORACLE / GLUCOSE-UPTAKE (need FBA flux extraction; deferred to a future turn)

## Acceptance criteria
1. All 5 in-scope KPs have non-`NA` opencell values.
2. Of the 5, at least 2 land as PASS (KP18 RNA-MASS and KP19 PROTEIN-MASS are the highest-confidence picks: Karr reference values are known and we have the counts + MW tables already).
3. Existing 6 PASSes do NOT regress (KP07, KP08, KP09, KP22, KP23, KP24).
4. `docs/phase_e/E2_scorecard.md` regenerated; new top-line should show `E2_PASS >= 8/28` and `BLOCKED <= 8`.
5. Full pytest passes (target: 896 + however many new tests you add, 0 failures, 4 xfails unchanged).
6. STATUS.md per-KP table: KP → status before → status after → file diff stat.

## Suggested commit boundaries
1. `obs-cp1: add RNA mass aggregator and unblock KP18`
2. `obs-cp2: add protein mass aggregator and unblock KP19`
3. `obs-cp3: add DNA mass observable and unblock KP17`
4. `obs-cp4: emit cytokinesis event timestamps and unblock KP13`
5. `obs-cp5: add metabolite profile snapshot and unblock KP20`
6. `obs-cp6: regenerate E2_scorecard.md with post-extension results`

Begin by reading `docs/phase_e/E2_scorecard.md` and `opencell/validation/phenotype_registry.py` end-to-end so you understand the registry conventions before touching any code.
