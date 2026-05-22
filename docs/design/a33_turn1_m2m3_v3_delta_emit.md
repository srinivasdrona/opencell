# A3.3 Turn 1 — M2v3 + M3v3 delta-emit conversion

**Status**: design ready · **Codex worktree**: `agent/a33-m2m3-v3` · **Estimated wall**: 25 min

## Why this module exists

Probe 4 (commit `466eb39`, merged `15331f8`) proved that mixed `_updater: "set"` + `_updater: "accumulate"` writes to the same Vivarium store leaf in one tick are silently order-sensitive and break mass balance. Decision logged at `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` as `opencell | vivarium-all-accumulate-no-set`: **every per-tick state-leaf writer in the OpenCell Vivarium chassis MUST use accumulate**.

M2v2 (`karr_m2_v2.py`) and M3v2 (`karr_m3_v2.py`) currently write `rna.counts.<wid>` and `protein.counts.<wid>` with `_updater: "set"` (lines 71 and 69 respectively). Once D.2-real lands in Turn 3 with `_updater: "accumulate"` on the same leaves for subunit consumption, M2/M3's set semantics would silently flip to accumulate and the chassis would emit deltas instead of absolute counts — catastrophic.

This turn ships M2v3 + M3v3 ahead of D.2-real so the topology is correct when D.2 arrives.

## Scope

**Net new files** (additive, per `migrate-by-addition-not-rewrite`):
1. `opencell/vivarium/karr_m2_v3.py` (~140 LOC, clone of v2 with delta-emit)
2. `opencell/vivarium/karr_m3_v3.py` (~140 LOC, clone of v2 with delta-emit)
3. `tests/vivarium/test_karr_m2_v3.py` (~120 LOC)
4. `tests/vivarium/test_karr_m3_v3.py` (~120 LOC)

**Modified files**: NONE in this turn. `karr_m2_v2.py` and `karr_m3_v2.py` are kept untouched so all existing tests against `build_karr_chassis_v2` continue to pass.

## Algorithm: how v3 differs from v2

For both M2 and M3, two changes only:

### Change 1: Updater type

```python
# v2 (current — DO NOT change in this turn)
"_updater": "set"

# v3 (new file)
"_updater": "accumulate"
```

Applied to:
- M2v3 `rna.counts.<wid>` schema entries
- M3v3 `protein.counts.<wid>` schema entries

### Change 2: Emit delta instead of absolute count

For each kinetically-updated leaf, instead of emitting the new absolute count, emit `(new − prior)` as the accumulate delta.

```python
# v2 (current — DO NOT change in this turn)
update["protein"] = {
    "counts": {
        pid: float(protein_next[i]) for i, pid in enumerate(self.protein_ids)
    }
}

# v3 (new file)
prior_counts = {pid: float(states["protein"]["counts"][pid]) for pid in self.protein_ids}
update["protein"] = {
    "counts": {
        pid: float(protein_next[i]) - prior_counts[pid]
        for i, pid in enumerate(self.protein_ids)
    }
}
```

Same pattern for M2v3 on `rna.counts.<wid>`.

### Unchanged

- `substrates.<wid>` already uses `_updater: "accumulate"` in v2 — it emits per-metabolite deltas. Keep as-is in v3.
- `complex.counts.<wid>` ports (read-only) — already `_emit: False` accumulate. Keep as-is.
- All kinetic math (`_step_protein`, `predict_synthesis_per_s`, RNA equivalent in M2). Bit-identical to v2.
- Class names: keep as `KarrTranslationV2Process` in the v2 file. The v3 file gets a new class `KarrTranslationV3Process` (and `KarrTranscriptionV3Process` for M2). Process `name` attribute likewise: `karr_translation_v3`, `karr_transcription_v3`.
- All defaults, parameters, fallbacks.

## Test plan

For each of M2v3 and M3v3, write a test file with at least these cases:

### Test 1: delta-equals-v2-absolute
Run M2v2 and M2v3 over a single tick from the same start-of-tick state and same kinetics model. After one tick:
- M2v2 emits absolute counts; final state should be `emitted_value`.
- M2v3 emits deltas; final state should be `prior + emitted_delta`.
- **Assert: M2v3 final state == M2v2 final state, bit-identical (within float tolerance 1e-9 per WID).**

This is the load-bearing test: it proves the v3 conversion is mathematically equivalent to v2.

### Test 2: schema-only-accumulate
Inspect `KarrTranslationV3Process(...).ports_schema()` and assert:
- Every leaf under `protein.counts.<wid>` has `_updater == "accumulate"`
- No leaf anywhere in the schema has `_updater == "set"`

Same for `KarrTranscriptionV3Process` on `rna.counts`.

### Test 3: order-insensitivity (the Probe 4 confirmation)
Build a tiny composite with two `KarrTranslationV3Process` instances (different parameter sets, both writing to `protein.counts`) and confirm that running them in two different registration orders gives the same final state. This re-uses the Probe 4 pattern but on the actual production process, not a toy.

### Test 4: substrate delta unchanged
Pin one or two metabolite deltas in `substrates.<wid>` to known v2-emitted values and confirm v3 emits the same delta. (The metabolite path was already accumulate in v2; this test guards against accidentally changing it.)

## Acceptance criteria

- [ ] `tests/vivarium/test_karr_m2_v3.py` and `tests/vivarium/test_karr_m3_v3.py` pass (4+ tests each)
- [ ] All 168 existing tests still pass against v2 chassis (no regressions): `pytest tests/ -x --ignore=tests/probes`
- [ ] `karr_m2_v2.py` and `karr_m3_v2.py` byte-identical to pre-turn state (no accidental edits)
- [ ] STATUS.md reports counts of new files + tests + total LOC, and confirms full test suite passes

## Out of scope

- `build_karr_chassis_v3` — that's Turn 5
- Modifying `karr_composite.py` — Turn 5
- D.2 real, ProteinDecay-light, allocation step — Turns 2–4
- Replacing v2 chassis — never (per `migrate-by-addition`)
