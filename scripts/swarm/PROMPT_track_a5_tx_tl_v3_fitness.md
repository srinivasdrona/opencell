# Track-A5: TX/TL v3 Runtime-Identity Guardrails + TL t=0 Monomer Fix

## Mandate
Two distinct concerns, one PR:

**Concern 1 (Runtime identity guardrails)**: Composition audit surfaced an L0 mismatch — original Class A audit targeted `karr_transcription.py` / `karr_translation.py` (v1) but `build_karr_chassis_v6` actually registers `karr_transcription_v3` / `karr_translation_v3`. Add chassis-level assertions and a CI gate so this can never silently regress.

**Concern 2 (TL t=0 monomer fix)**: TL v3 D5 finding (`opencell/validation/swarm/class_a_v3/Translation/findings.json:97-110`) — fixture tick-0 monomers are all zero, v3 chassis seeds `protein.unprocessed_counts` from `counts_mature` (296 non-zero proteins, sum=16177). For Karr parity, t=0 must match fixture. Either:
- (a) Add an init flag `seed_from_fixture: bool = True` and have chassis honor it, OR
- (b) Make chassis init unconditionally fixture-aligned for v3 processes.

Choose (a) if there are legitimate non-replay use cases for non-zero init, (b) otherwise. Justify your choice in a code comment + the summary doc.

## Authoritative references
- `opencell/validation/swarm/class_a_v3/Translation/findings.json` (D1 = identity match, D5 = t=0 mismatch)
- `opencell/validation/swarm/class_a_v3/Transcription/findings.json` (D1 = identity match)
- `opencell/validation/swarm/composition/composition_audit.md` (L0 section)
- `opencell/vivarium/karr_composite.py:1380-1409,1468-1470,1487-1490,1510-1514,1885-1890`
- `opencell/vivarium/karr_translation_v3.py:31-34,67-70,107-145`
- `opencell/vivarium/karr_transcription_v3.py` (analogous lines)

## Implementation plan

**Part 1 — Runtime-identity guardrails (~40-70 LOC)**:
1. In `karr_composite.py` (or a new `opencell/validation/runtime_identity.py`), add:
   ```python
   def assert_chassis_runtime_identity(chassis):
       expected = {
           "karr_transcription": "KarrTranscriptionV3Process",
           "karr_translation": "KarrTranslationV3Process",
       }
       for key, cls_name in expected.items():
           proc = chassis.processes[key]
           assert type(proc).__name__ == cls_name, ...
   ```
2. Wire it into `build_karr_chassis_v6` so any build that registers v1 fails fast.
3. Add `tests/integration/test_chassis_runtime_identity.py` that constructs v6 chassis and asserts.
4. Extend the assertion to any other process where Composition audit's L0 layer flagged a mismatch — read `composition_audit.md` for the full L0 list.

**Part 2 — TL t=0 monomer fix (~30-60 LOC)**:
1. Read `karr_translation_v3.py:67-70` and trace how `counts_mature` flows to chassis init.
2. Verify fixture-zero is the correct init: load `data/karr_fixtures/per_process/Translation_flat.mat`, confirm `monomers` is 482-vector of zeros.
3. Implement choice (a) or (b). Recommendation: **(a) with default = fixture-aligned**, since chassis-without-replay use cases may legitimately want non-zero seed for debugging.
4. Mirror the same logic for **Transcription v3** if `findings.json:88-95` reveals an analogous initialization gap (read the file before assuming).
5. Add `tests/integration/test_tx_tl_v3_init_parity.py` that:
   - Loads fixture
   - Constructs chassis with `seed_from_fixture=True`
   - Asserts chassis `protein.unprocessed_counts` matches fixture monomers at t=0

## Tests
- All new tests must pass.
- Existing 903-test unit suite must remain green.
- Run `pytest tests/integration/test_chassis_runtime_identity.py tests/integration/test_tx_tl_v3_init_parity.py -v`.

## Self-grading
Write `opencell/validation/track_a/a5_tx_tl_v3_fitness_summary.md` with:
- The (a)-vs-(b) decision and rationale
- Files modified + LOC
- Test names + assertions
- Any L0 mismatches discovered beyond TX/TL that you fixed or chose to defer

## Commit discipline
- Branch: `track-a/L0-tx-tl-v3-fitness` (already checked out at `E:\opencell-worktrees\track-a5`).
- Commits:
  1. `track-a5: add runtime-identity guardrails for TX/TL v3 chassis registration`
  2. `track-a5: fix TL t=0 monomer initialization (and TX if mirrored)`
  3. `track-a5: integration tests for chassis runtime identity + t=0 parity`

## Budget
- Token budget: 200k with compaction at 75%.
- If a third Process beyond TX/TL needs runtime-identity guarding and the fix balloons, STOP and write `a5_scope_question.md`.

## Scope discipline
- Do not touch allocator enrollment (that's A2).
- Do not touch helper zero-grant semantics (that's A1).
- Do not modify fixture extraction pipeline.
