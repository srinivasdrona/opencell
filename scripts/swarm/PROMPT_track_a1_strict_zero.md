# Track-A1: L5 Strict-Zero Helper Contract Rollout

## Mandate
Enforce strict zero-grant semantics at every audited helper/inline fallback site. **No global-pool fallbacks when allocator grants zero.** Authoritative basis: `opencell/validation/swarm/l5/zero_grant_contract_recommendation.md` (committed, on main via merge ffbe5b8). Karr reference: `evolveState.m:63-70` overwrites `this.substrates` with allocation; processes gate on `this.substrates >= cost`.

## Authoritative call-site inventory
Read `opencell/validation/swarm/l5/l5_call_sites.csv` (committed). 13 of 15 rows need changes. The 2 `karr_ftsz_polymerization.py` rows already implement presence-based zero-handling correctly — **leave FtsZ alone**, but add a code comment marking the pattern as canonical.

## Fix patterns

**Pattern A — `_allocated_or_state` helpers** (6 process files):
```python
# BEFORE
def _allocated_or_state(allocated, substrate_state, wid):
    a = allocated.get(wid, 0)
    return a if a > 0 else substrate_state[wid]

# AFTER
def _allocated_or_state(allocated, substrate_state, wid):
    a = allocated.get(wid, 0)
    return max(0, a)  # strict-zero: do NOT fall back to global pool
```
Affected: `karr_chromosome_condensation.py`, `karr_chromosome_segregation.py`, `karr_cytokinesis.py`, `karr_dna_repair.py`, `karr_dna_supercoiling.py`, `karr_replication.py`, `karr_replication_initiation.py`.

**Pattern B — `_allocated_or_free` helper** (`karr_protein_folding.py`): same fix.

**Pattern C — `_available_atp` helper** (`karr_protein_translocation.py:194`): same fix; remove fallback to `states["substrates"][ATP]`.

**Pattern D — Inline `allocated if > 0 else state` ternaries** (5 sites):
- `karr_protein_modification.py:151`
- `karr_protein_processing_i.py:246`
- `karr_protein_processing_ii.py:184`
- `karr_rna_modification.py:143`
- `karr_rna_processing.py:246`
- `karr_trna_aminoacylation.py:129`

Replace inline ternary `alloc if alloc > 0 else state` with `max(0, alloc)`.

## Tests

For each modified Process, add a unit test in `tests/unit/test_<process>_strict_zero.py`:
1. Construct the Process with a fixture-seeded state.
2. Set allocator grant to **zero** for the relevant substrate(s).
3. Run `next_update`.
4. Assert: no delta emitted (or delta=0) for those substrates, AND no read against global pool.

If a process doesn't expose `next_update` cleanly for unit testing, write a topology-level test on a minimal chassis instead.

## Self-grading and reducer protocol

After implementing:
1. Run `pytest tests/unit/test_*_strict_zero.py -v` — all green.
2. Run the existing 903-test unit suite — must still be green (no regressions).
3. Smoke-test: full chassis 10-tick run, confirm no exceptions and no negative substrate counts.
4. Write `opencell/validation/track_a/a1_strict_zero_summary.md` with:
   - Per-site diff line count
   - Per-site test name
   - Total LOC added/removed
   - Any sites SKIPPED with reason (e.g. FtsZ already correct)

## Commit discipline
- One commit per logical group (e.g. "A1: strict-zero in `_allocated_or_state` helpers", "A1: strict-zero in inline ternaries", "A1: tests"). 
- Branch: `track-a/L5-strict-zero` (already checked out at `E:\opencell-worktrees\track-a1`).
- Final commit message: `track-a1: enforce L5 strict-zero contract across 13 fallback sites`.

## Budget
- Token budget: 250k with compaction at 75%. Use `/compact` if approaching 187k.
- If you hit a fundamental blocker (e.g. allocator key missing for a Process), STOP and write `a1_blocker.md` with the unblocking question — do not improvise.

## Scope discipline
- Do not modify allocator code (L2/L3/L4/L6) — those are A2/A3/A4 territory.
- Do not modify TX/TL — those are A2/A5 territory.
- Do not touch fixture pipeline.
- Stay inside this 13-site list.
