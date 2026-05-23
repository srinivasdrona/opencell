# Phase-2 Fix: Audit's Deferred HIGH/MED Findings

## Context

The substrate cascade (Bug 1/2/3 + 3.5/3.6) is now resolved — 100t canary shows ATP min=0 instead of -43,750. The `bypass-precondition-audit` (commit on main, `docs/audits/bypass_precondition_audit.md`) identified findings BEYOND that cascade scope which should be addressed before a 32,400-tick run is realistic.

This session tackles **three independent fixes** on a fresh branch off `agent/substrate-cascade-fix` (so it inherits the cascade fix).

## Worktree setup

You are launched in `E:\opencell-worktrees\phase-2-fix` on branch `agent/phase-2-fix` (already created off `agent/substrate-cascade-fix`). If the worktree isn't set up yet, do:
```
cd /mnt/e/opencell
git worktree add /mnt/e/opencell-worktrees/phase-2-fix -b agent/phase-2-fix agent/substrate-cascade-fix
```

## Token budget

130k ceiling. Auto-handoff if you hit it (HANDOVER.md + commit + exit). Each of the three fixes below should fit comfortably; commit after each.

## The three findings

### Finding A: Bug 4 — Metabolism producer silence (audit HIGH D)

File: `opencell/vivarium/karr_metabolism.py:267`
Issue: per audit, the metabolism FBA process consumes its allocated substrates correctly but **does not emit positive substrate deltas for produced metabolites** (NTPs, AAs, ATP regeneration). This is why even with the cascade gating fixed, ATP stays at 0 after tick 1 instead of being replenished by metabolism.

Read the audit doc first: `docs/audits/bypass_precondition_audit.md` (lines around HIGH D).
Then read `karr_metabolism.py` around line 267 to confirm the producer-silence pattern.

Fix approach:
- Identify the FBA solution structure (likely `solution.fluxes` or similar) — what metabolites does the FBA solve for as products?
- In `next_update`, emit positive deltas to the `substrates` port for produced metabolites, mirroring how the consumers emit negative deltas.
- The producer-side delta logic should match the dt scaling and stoichiometry used for consumption.

Validate:
- Existing metabolism tests must still pass.
- Run the 100t canary again — ATP should now show non-monotonic dynamics (some production, some consumption) rather than flat at 0.

Commit: `Bug 4: karr_metabolism emits substrate production deltas`.

### Finding B: D2 discards substrates_allocated (audit HIGH B)

File: `opencell/vivarium/karr_macromolecular_complexation.py:203`
Issue: D2 reads `substrates_allocated` then explicitly discards it (`_ = ...`). Either:
- The process was supposed to use it for gating but the use was deleted, or
- The process doesn't need substrate gating and the port is vestigial.

Read the surrounding code to determine which. If gating is needed, wire the allocation into the consumption computation. If vestigial, remove the dead read AND the port wiring in the chassis builders (v5/v6) AND any consumer_map entries that put D2 in.

Validate:
- D2-related tests pass.
- 100t canary still clean.

Commit: `Audit HIGH B: D2 macromolecular_complexation substrates_allocated use or remove`.

### Finding C: ProteinDecay no clamp (audit MED B)

File: `opencell/vivarium/karr_protein_decay_light.py:193`
Issue: ProteinDecay consumes substrates without an allocation clamp. Lower-priority than the others but worth fixing for consistency.

Fix approach:
- Add allocation enrollment if not present (consumer_map in chassis_v6 + topology for `substrates_allocated`).
- Add the gating clamp in `next_update`.
- OR if protein decay's substrate cost is negligible (e.g., only water), document why no clamp is needed and leave it.

Validate:
- Existing tests pass.
- 100t canary still clean.

Commit: `Audit MED B: ProteinDecay allocation clamp (or document negligibility)`.

## Final step

After all three fixes:

Run:
```
source /mnt/e/opencell/.venv-wsl/bin/activate
cd /mnt/e/opencell-worktrees/phase-2-fix
python -m pytest tests/ -q --no-header 2>&1 | tail -10
python scripts/diagnose_substrate_leak.py --max-ticks 100 > artifacts/phase_2_fix/canary_100t.txt 2>&1
```

Write `STATUS_phase2.md` with:
- Per-finding: what was done, evidence file:line citations
- Test suite results (total pass/fail counts)
- 100t canary deltas (compare to v4's baseline: ATP min=0, delta `-1, 0, 0, ...`)
- Confidence: clean-ready-for-1000t / needs-investigation / regressed

## Hard constraints

- Do NOT touch karr_transcription_v3.py / karr_translation_v3.py / karr_composite.py (those are the cascade fix; reverting would re-break things)
- Do NOT modify chassis_v6 process inventory (29 processes including transcriptional_regulation stays)
- Commit per-finding so partial work survives compaction
