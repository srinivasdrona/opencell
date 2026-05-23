# Phase C Turn 2 — Replication (Karr-LIGHT v1)

**Status**: design ready  
**Task slug**: `pc-t2-replication`  
**Karr process**: `Process_Replication`  
**Primary source**: `docs/karr_extracts/process/03_Replication.md`  
**Trace target**: `data/m1_sources/karr_native/per_process_traces/Replication_100ticks.mat`

## Why this turn

`ReplicationInitiation` (pc-t1) only flips `chromosome.replication_state` to
`"initiating"`. This turn implements the downstream fork advancement state
machine and shared-substrate demand so replication can progress and terminate.

## Karr source findings used in v1

From `data/karr_fixtures/per_process/Replication.json`:

- `fixture/dnaPolymeraseElongationRate = 100` (bp/s)
- `fixture/stepSizeSec = 1`
- `fixture/oriCPosition = 1`
- `fixture/terCPosition = 290038`
- dNTP substrate IDs: `DATP, DCTP, DGTP, DTTP`

From `data/karr_fixtures/per_process/Chromosome.json`:

- `fixture/sequenceLen = 580076`
- `fixture/sequenceGCContent = 0.31689123494162835`

Trace note: the current `Replication_100ticks.mat` export is readable
(`metadata.process_name = Replication`, `n_ticks = 100`) but has empty
`states_after` cells in this snapshot format, so per-tick substrate deltas are
not directly recoverable here. For v1, we anchor the fork rate to the fixture
constant above and document this as an open validation gap.

## Scope

### In scope (Karr-LIGHT v1)

1. Read `chromosome.replication_state`.
2. If state is `"initiating"`, transition to `"elongating"` and initialize fork
   positions at 0 bp from oriC.
3. Track two bidirectional forks:
   - `chromosome.fork_position_bp.left`
   - `chromosome.fork_position_bp.right`
4. Advance forks at 100 bp/s per fork (bounded by `terCPosition` remaining and
   substrate allocation).
5. Use allocation contract:
   - write `requests.karr_replication.*`
   - read `substrates_allocated.karr_replication.*`
   - consume only allocated amounts
6. When both forks reach `terC`, set `replication_state = "complete"` and emit
   one completion event.

### Deferred to v2 (explicit)

1. SSB binding/release cycle.
2. Okazaki fragment initiation/termination mechanics.
3. Leading/lagging strand asymmetry and fragment-level ligation events.
4. RNAP collision stalls/head-on dwell handling.
5. Ligase NAD coupling and strand-break bookkeeping.

## State ports / stores

New process file: `opencell/vivarium/karr_replication.py`

Ports:

- `chromosome`
  - `replication_state` (`set`): `"idle" | "initiating" | "elongating" | "complete"`
  - `fork_position_bp.left` (`accumulate`, emitted)
  - `fork_position_bp.right` (`accumulate`, emitted)
  - `events.replication_complete` (`accumulate`, emitted; one-shot +1)
- `substrates`
  - `DATP, DCTP, DGTP, DTTP, ATP` (`accumulate`)
- `requests.karr_replication`
  - per-substrate request (`set`)
- `substrates_allocated.karr_replication`
  - per-substrate allocation (`accumulate`)

## Substrate consumption model (v1)

Let `aL`, `aR` = actual bp advance for left/right forks in a tick.

- total advanced bp across both forks: `a_total = aL + aR`
- total polymerized nucleotides: `2 * a_total`

dNTP split by chromosome base composition:

- `f_gc = sequenceGCContent`
- `f_at = 1 - f_gc`
- `fA = fT = f_at / 2`
- `fC = fG = f_gc / 2`

So requested/consumed dNTP counts are integer-rounded partitions of
`2 * a_total` over `{DATP, DCTP, DGTP, DTTP}` with those fractions.

Helicase ATP cost (v1 approximation): `ATP = a_total * helicase_atp_per_bp`,
default `helicase_atp_per_bp = 1.0`.

If allocations are limiting, compute a shared proportional scale:

`scale = min(1, allocated_i / requested_i for all requested substrates i)`

then reduce `aL, aR` by `scale` (integer floor), recompute substrate
consumption from reduced advancement, and enforce non-negative availability.

## Test plan

New test module: `tests/vivarium/test_karr_replication.py`

1. Process instantiates and loads fixture defaults.
2. `replication_state = "idle"` => no fork movement and zero requests.
3. `"initiating"` => transitions to `"elongating"` with no immediate advance.
4. After N elongation ticks, fork positions increase ~`N * 100` (subject to
   substrate limits) and dNTP pools decrease.
5. At `terC`, state changes to `"complete"` and completion event emits once.
6. Allocation-limited case: partial allocation scales fork advance
   proportionally.
7. 1000-tick partial run: fork positions monotonic, finite, non-negative;
   cumulative substrate deltas match cumulative consumed request (v1 mass check).

## Open questions

1. `Replication_100ticks.mat` currently lacks non-empty `states_after`; once a
   full trace export is available, calibrate/verify v1 ATP and dNTP demand
   against native deltas.
2. Confirm helicase ATP stoichiometry from a higher-fidelity Replication source
   extract for v2 (v1 uses 1 ATP/bp across both strand copies).
