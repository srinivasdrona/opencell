# Phase C Turn 6 — DNADamage

**Status**: design ready (Karr-light v1) · **Estimated wall**: 25 min · **Karr process**: `Process_DNADamage`

## Primary source and evidence

- Primary source: `docs/karr_extracts/process/04_DNADamage.md` (verbatim extract of `DNADamage.m` header)
- Fixture: `data/karr_fixtures/per_process/DNADamage_flat.mat`
- Intended trace input: `data/m1_sources/karr_native/per_process_traces/DNADamage_100ticks.mat`

Notes from primary source used directly:
- DNADamage is stochastic and selects vulnerable DNA regions each tick.
- Damage classes include base damage, intrastrand cross-links, abasic sites, and strand breaks.
- DNADamage updates chromosome damage state; repair is handled by a separate process.

## Karr-light v1 scope

### In scope (this turn)

1. Add `opencell/vivarium/karr_dna_damage.py` as a stochastic per-tick damage generator.
2. Add `chromosome.damage_sites` as an accumulate-only append log with entries:
   - `{position: int, kind: str, age_ticks: int}`
3. Implement four Karr-light damage kinds required by task scope:
   - `uv_like`
   - `oxidative`
   - `alkylation`
   - `depurination`
4. For each kind, sample **Poisson-distributed** new events per tick using per-second rates.
5. Randomly assign genomic positions over chromosome length (1..`sequence_len_nt`).
6. Add advisory replication coupling:
   - if any new damage lands at an active fork position, emit `chromosome.replication_stall_flag += 1` (sticky accumulate flag).
7. Keep process substrate-neutral (no consumption or requests in v1).

### Deferred to v2 (explicit)

- Full Karr reaction-level motif vulnerability mapping (`reactionVulnerableMotifs`) per lesion chemistry.
- Explicit strand/base damage arrays (`gapSites`, `abasicSites`, `damagedBases`, etc.) parity with MATLAB state internals.
- Radiation/stimulus-dependent dynamic rates.
- Direct interoperability with DNARepair substrate coupling and lesion-specific stoichiometry.
- Per-site age incrementation semantics (v1 stores `age_ticks=0` at creation in append-only log).

## Rate model and trace policy

- Default rates are stored in `kind_rates_per_s` parameters and used as the process truth at runtime.
- Process attempts to load the DNADamage trace file if present to support calibration helpers.
- Because the 100-tick trace artifact is absent in this worktree, tests use a dual policy:
  - compare against trace-derived expected totals when trace file exists;
  - otherwise compare against Poisson expectation from configured per-kind rates.

Initial v1 defaults (Karr-light):
- `uv_like`: 6.0e-1 /s (doc extract table UV-B dimer order of magnitude)
- `oxidative`: 1.7e-11 /s (doc extract gamma-ray oxidation baseline order)
- `alkylation`: 0.0 /s (no direct fitted baseline available in local fixture extract)
- `depurination`: 8.4e-5 /s (doc extract spontaneous base loss order)

## Ports and state additions

```python
"chromosome": {
    "damage_sites": {
        "_default": [],
        "_updater": "accumulate",
        "_emit": True,
    },
    "fork_positions": {
        "_default": {"left": None, "right": None},
        "_updater": "set",      # read-only for this process
        "_emit": False,
    },
    "replication_stall_flag": {
        "_default": 0.0,
        "_updater": "accumulate",
        "_emit": True,
    },
}
```

Store semantics:
- `damage_sites` is append-only and monotone in v1.
- `replication_stall_flag` is advisory and sticky (non-zero means stalled due to encountered fork damage).

## Algorithm sketch

1. Read current `chromosome.damage_sites` and `chromosome.fork_positions`.
2. For each kind in `{uv_like, oxidative, alkylation, depurination}`:
   - `n_new ~ Poisson(rate_per_s * dt)`
   - sample `n_new` positions uniformly in `[1, sequence_len_nt]`
   - append event dicts with `age_ticks = 0`.
3. Determine if any new site position equals either active fork position.
4. Return accumulate updates:
   - append list under `chromosome.damage_sites`
   - `chromosome.replication_stall_flag = 1.0` if fork hit else no write.

## Substrate consumption

- None in v1.
- No `requests` / `substrates_allocated` ports in this process.
- Rationale: task scope is lesion generation only; repair chemistry and substrate coupling are explicitly deferred to pc-t7.

## Test plan

At least 5 tests in `tests/vivarium/test_karr_dna_damage.py`:

1. `test_instantiates_with_defaults`
- Process loads defaults, known kinds exist, and chromosome length is positive.

2. `test_single_tick_damage_delta_sign`
- With elevated deterministic rates, one tick produces non-negative count of newly appended damage entries and valid schema fields.

3. `test_no_substrate_allocation_contract`
- Process schema/update do not include `requests` or `substrates_allocated` writes.

4. `test_replication_stall_flag_on_fork_hit`
- With forced position sampler at fork, one tick emits `replication_stall_flag` positive accumulate delta.

5. `test_100_tick_total_within_tolerance`
- Run 100 ticks with fixed seed.
- Compare total created events against expected 100-tick total (trace-derived when available, otherwise rate-derived) within 20%.

6. `test_no_nan_no_negative_regression`
- Over 100 ticks: no NaN positions, no negative positions, no unknown kinds, no negative stall flag.

## Open questions

1. Trace file path in task prompt points to a location that does not exist in this worktree. v1 handles this with a tested fallback; once traces are synced, tests will auto-use trace expectations.
2. The exact baseline rate for alkylation in this fixture/extract set is not directly available; v1 keeps it explicit and configurable via `kind_rates_per_s`.
3. Age progression semantics under accumulate-only list updates will need v2 design if DNARepair requires real-time lesion age for prioritization.
