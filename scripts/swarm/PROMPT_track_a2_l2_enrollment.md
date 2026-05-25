# Track-A2: L2 Enrollment for Metabolism + TX/TL v3

## Mandate
Enroll three direct-writer processes — **Metabolism**, **karr_transcription_v3** (TX), **karr_translation_v3** (TL) — into the allocator's `consumer_processes` topology so they request and receive allocated substrate budgets instead of writing direct deltas to shared substrate counts. This is the **B1 keystone fix**.

## Authoritative references (all merged on main)
- `opencell/validation/swarm/composition/composition_audit.md` — L2 enrollment hot list
- `opencell/validation/swarm/consolidated/CONSOLIDATED_AUDIT_REPORT.md` — finding rows 8, 16, 17
- `opencell/validation/swarm/class_a_v3/Transcription/findings.json` — TX D2 confirmed
- `opencell/validation/swarm/class_a_v3/Translation/findings.json` — TL D2 confirmed
- `opencell/vivarium/karr_composite.py:1380-1409, 1510-1514` — current `consumer_processes` list
- `opencell/vivarium/karr_request_calculators.py` — pattern to follow for new calculators

## Implementation plan

### Part 1 — TX (karr_transcription_v3)
1. Add a `RequestCalculatorTranscription` class (or equivalent) in `karr_request_calculators.py` modeled on existing calculators. Request vector must include all substrate IDs TX currently writes deltas for. Read `karr_transcription_v3.py` to enumerate them (NTPs + side products).
2. Add `karr_transcription` to `consumer_processes` in `karr_composite.py` (search for the analogous block).
3. Modify `karr_transcription_v3.py` `next_update`:
   - Read allocated substrates via the new strict-zero pattern (`max(0, allocated.get(wid, 0))`) — DO NOT fall back to global pool. This matches A1's L5 contract.
   - Compute deltas from allocated budget, not from global pool.
4. Add a `substrates_allocated` port to TX's topology.

### Part 2 — TL (karr_translation_v3)
Same pattern as Part 1. Substrate vocabulary includes 20 AAs (the existing v3 set). Note from TL audit D3: Karr also tracks FMET/GTP/GDP/Pi/H2O/H+; **for A2 scope, enroll only what TL actually emits today** (20 AAs). Adding the missing channels is a separate biology change, out of A2 scope.

### Part 3 — Metabolism
Same pattern. Metabolism has the broadest substrate footprint; read `karr_metabolism.py` carefully to enumerate. Be conservative: enroll the actual consumed/produced substrates, not the full FBA stoichiometry matrix.

## Tests
For each newly enrolled process, add `tests/integration/test_<process>_allocator_enrollment.py`:
1. Construct v6 chassis.
2. Assert `karr_<process>` is in `KarrAllocationStep.consumer_processes`.
3. Assert process exposes a `substrates_allocated` (or equivalent) port in its topology.
4. Run 10 ticks; assert no `substrates` count goes negative (the B1 fix invariant).

Run the existing B1 sanity test that A5 noted as failing:
```
py -3.12 -m pytest tests/integration/test_b1_substrate_sanity.py -v
```
This test MUST go from red to green as a direct result of A2.

## Self-grading
Write `opencell/validation/track_a/a2_l2_enrollment_summary.md` with:
- Per-process: substrate IDs added to request vector, lines modified in composite, new calculator class
- B1 sanity test outcome before/after
- Whether the 10-tick negative-count check passes for all three processes
- Any substrates intentionally deferred (e.g., TL FMET) with rationale

## Commit discipline
- Branch: `track-a/L2-enrollment` (worktree `E:\opencell-worktrees\track-a2`).
- Commits:
  1. `track-a2: add request calculators for Metabolism + TX/TL v3`
  2. `track-a2: enroll Metabolism + TX/TL v3 in allocator consumer_processes`
  3. `track-a2: switch next_update to allocated-budget reads (strict-zero)`
  4. `track-a2: integration tests + B1 sanity verification`

## Python interpreter
**Use `py -3.12`** for all pytest invocations. Default `python` resolves to 3.14 which has broken `vivarium`/`pint`/`numpy`/`jax` deps. This was the env blocker A1 hit; A5 proved `py -3.12` is clean (354 passed).

## Budget
- Token budget: 350k with compaction at 75%. This is the largest A-PR.
- If a fundamental ambiguity arises (e.g., "which Metabolism substrates count as allocator-traffic vs telemetry"), STOP and write `a2_scope_question.md`.

## Scope discipline
- Do not modify L5 helpers (A1 territory, already done).
- Do not touch L4 default keys (A3 territory).
- Do not add new resource vectors (A4 territory; A4's DNASupercoiling+ProteinTranslocation work is independent).
- Do not touch fixture pipeline.
- DO read the A1 commits on `track-a/L5-strict-zero` as reference for the strict-zero read pattern — but do not depend on A1 being merged.
