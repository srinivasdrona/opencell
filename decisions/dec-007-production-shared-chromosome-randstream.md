# DEC-007: Production state-owned shared `ChromosomeStateRandStream` (Stage A+B RNG-only TxReg migration); additive to and preserving dec-006

**Status:** Active
**Date:** 2026-10-14
**Decision:** Production OpenCell gains exactly ONE state-owned shared chromosome
RNG stream — a `ChromosomeStateRandStream` (MATLAB-compatible `mcg16807`) owned
by the `opencell.state.chromosome_store.ChromosomeStore` authority and serialized
in the chromosome state at the leaf `chromosome._shared_rand_stream_state` as an
int64 `[seed, mcg_state]` pair. It stands in for Karr's single shared
`Chromosome.randStream`. This decision is **additive to and preserves dec-006**:
dec-006's captured per-tick draw ledger remains a **test-only input oracle** and
is **not** superseded. This card is the Stage A+B **implementation gate**: no
Stage A+B production/test code merges without it ratified (shared-chromosome
design §13, §15, §18/A18; `docs/design/shared_chromosome_state_subsystem.md`).

## Context

Karr's `Chromosome.randStream` is a property of the shared `Chromosome` **state**
object (`Chromosome < CellState`), advanced by every chromosome-binding process
in a tick through `bindProteinToChromosome`/`sampleAccessibleRegions`/
`setSiteDamaged`/`setSiteProteinBound`. OpenCell already has a single chromosome
**state** authority (`ChromosomeStore`, wired via a `chromosome` port into 8 of
the 9 chromosome-binders), but its shared **RNG** authority was fragmented into
per-process stand-in streams (`TxRegMcgRandStream`, `ChromCondMcgRandStream`,
DNASupercoiling's release ledger, DNADamage's `KarrMcg16807Stream`), each
independently seeded and advanced.

dec-006 (`decisions/dec-006-shared-chromosome-randstream-input-oracle.md`,
Active) resolved the **test/replay** question: the captured per-tick
`chromosome.randStream` draw ledger is a legitimate L2.1 **input oracle**, never
an oracle answer, and `Production code paths are unaffected ... the ledger stream
is ONLY ever constructed and injected by an L2.1 replay TEST harness, never by
next_update itself`. dec-006 therefore deliberately left the **production**
shared stream unbuilt. dec-007 builds exactly that one missing production piece,
without disturbing dec-006's test-only ledger contract.

## Decision

1. **One production authority for the shared chromosome RNG.** A single
   `ChromosomeStateRandStream` (unifying the byte-identical per-process
   `mcg16807` shims) is owned by the `ChromosomeStore` state authority. No
   process keeps a private production shared-stream copy, and no second state
   authority is created. The per-process **decision** streams (e.g.
   ChromosomeCondensation region/position, DNASupercoiling/DNADamage process
   draws) remain local and untouched (MIXED model): only chromosome
   accessibility/commit/release draws advance the shared stream.

2. **Serialized representation (exact).** The stream state lives in the
   chromosome state at the leaf `chromosome._shared_rand_stream_state`, typed as
   `numpy.int64` shape-`(2,)` = `[seed, mcg_state]` (generator fixed as the
   constant `mcg16807`; `mcg_state ∈ [1, 2**31-2]`). Vivarium schema entry:
   `{"_default": [-1, -1] (int64 sentinel), "_updater": "set", "_emit": True}`.
   It round-trips through `ChromosomeStore.to_state`/`from_state_mapping` under a
   reserved key (`CHROMOSOME_RAND_STREAM_KEY = "_shared_rand_stream_state"`).

3. **Seed-once-at-init, fail-closed-per-tick (the correctness rule).**
   - **Initial-state construction only** (composite builder / explicit legacy
     adapter) may seed an absent key exactly ONCE from the run seed and write it
     into `initial_state`.
   - **Ordinary production `next_update`** that genuinely needs a draw MUST
     treat an absent/`_UNSEEDED`/`[-1,-1]` leaf as a **hard error**
     (`RuntimeError`) and MUST NEVER reseed. The post-tick `[seed, mcg_state]` is
     **written back every tick, including zero-draw ticks**, so the emitted trace
     records the stream position on every tick and the leaf is never stale.

4. **Stage A+B is an RNG-only, TxReg sole-consumer migration.** The first slice:
   - adds the `ChromosomeStateRandStream`, the serialized leaf, the narrow store
     handle (`rand_stream()`/`rand_state`/`set_rand_state`), and the
     `to_state`/`from_state_mapping` contract (Stage A);
   - wires the TxReg `chromosome` port and **swaps only** the
     `_chromosome_rng.randsample` provider in TxReg's
     `_sample_accessible_sites_batched` for the store-owned handle, writing the
     advanced state back (Stage B).
   TxReg's candidate selection, affinity weighting, accessibility, and
   exclude-overlap logic are **unchanged**. TxReg's private `tf_bound_promoters`
   occupancy surface remains a **known, temporary dual representation** through
   Stage B; single state-authority consolidation (removal of the private surface,
   store footprint writeback, and `sample_accessible_regions` centralization) is
   deferred to **Stage C** with its own index-for-index parity gate. (A1
   single-authority is NOT claimed at the first slice.)

5. **Explicit production non-dependencies in this slice.**
   - **No ledger/oracle in production.** The dec-006 ledger stream is never
     constructed or read by `next_update`; it is injected only by replay test
     harnesses. Any production import/construction of a `*LedgerRandStream` is a
     defect.
   - **No two-column fold-change.** Downstream `tx_rate_fold_change` stays
     single-copy (column 0); two-column emission is deferred to a later joint
     TR + DNASupercoiling + Transcription + Replication stage.
   - **No multi-consumer commit owner yet.** Stage A+B is single-consumer; TxReg
     draws within its own `next_update` (valid because it is the only consumer).

6. **Checkpoint honesty.** `opencell/core/checkpoint.py` persists only
   `time_s`, `counts`, a single top-level `rng_key`, `species_ids`, and
   `metadata` — it serializes **no** chromosome state and **no** chromosome RNG
   stream. Cross-run chassis checkpoint/restart of the shared chromosome RNG is
   therefore **deferred and explicitly NOT claimed** by this decision. Within a
   run, persistence is provided solely by the Vivarium store leaf +
   `to_state`/`from_state_mapping` round-trip (and trace-HDF5 for replay).

7. **Later multi-consumer stage is out of dec-007's bounded scope.** Routing a
   second shared-stream consumer (DNADamage favored; DNASupercoiling/Replication
   heavier) requires the **reviewed sequential chromosome-commit owner (a
   Vivarium Step) + static per-process single-writer intent leaves** with a
   generation sentinel, and the full per-process shared-draw family
   (bind/damage/release, with finite-rate releases drawing and `Inf` not) in
   exact intra-`evolveState` order. That mechanism is designed in
   `docs/design/shared_chromosome_state_subsystem.md` (DC-9/DC-10, Stage E) but
   is **outside this bounded first-slice decision**; it will be ratified by its
   own follow-on gate when that stage lands.

8. **Rollback and acceptance gates.** Each Stage A/B step is behavior-neutral or
   baseline-preserving; **rollback = revert the stage commit** (no permanent
   feature flag). Acceptance gates for Stage A+B:
   - **Stream equivalence & continuity:** the unified `ChromosomeStateRandStream`
     matches the prior per-process shims bit-for-bit (`rand`/`randsample`/
     `get_state`/`set_state`), and a `to_state → from_state_mapping → continue`
     dump/reload over ≥2 ticks (including a zero-draw tick) reproduces the next
     draws bit-identically.
   - **Candidate parity:** a controlled candidate fixture shows the Stage-B
     store-owned path produces the SAME selected indices AND the SAME
     `[seed, mcg_state]` progression, step-for-step, as the current in-process
     `_chromosome_rng` (not ledger outputs alone).
   - **Replay bit-identity:** the canonical seed-0 4000-tick active-window replay
     stays bit-identical under the dec-006 harness (trace `645a2e68…`, ledger
     `ac2426dc…`, draw digest `88c7c28c…`).
   - **Chassis integrity:** `pre_l25_honesty.py audit` stays `INTEGRITY_OK`,
     **5/28** eligible; L1b and baseline regressions stay green.

## Arguments For

1. **Matches source semantics.** Karr's shared draws all occur inside the single
   `Chromosome` state object; a state-owned, serialized stream is the faithful,
   single-authority mapping, and the only representation that survives OpenCell's
   reconstruct-from-mapping-each-tick chassis.
2. **Preserves dec-006 exactly.** dec-006 governs the test-only input oracle and
   remains in force; dec-007 fills the production gap dec-006 explicitly left
   ("production code paths are unaffected"). The two are additive and compatible;
   dec-006 is not superseded.
3. **Smallest honest first slice.** RNG-only, single-consumer, draw-sequence-
   preserving — so the existing dec-006 L2.1 replay is a ready bit-identity
   falsification test, and the hardest/lowest-value pieces (commit owner,
   two-column, scheduler permutation) are deferred.
4. **Fail-closed, no oracle laundering.** Seed-once-at-init + per-tick
   fail-closed-on-absence prevents silent reseeding; the no-ledger-in-production
   rule prevents the replay oracle from leaking into production.

## Arguments Against (and rejected reasons)

1. **"Serialize the stream as the stream's `get_state()` dict."** Rejected: an
   ambiguous dict scalar is harder to validate and HDF5-round-trip than a fixed
   int64 `[seed, mcg_state]` pair with the generator fixed as a constant.
2. **"Default an absent key to a freshly-seeded stream everywhere for
   back-compat."** Rejected: that would let `next_update` silently reseed and
   diverge; absent-key seeding is permitted ONLY at initial-state construction,
   and `next_update` must fail closed.
3. **"Fold the per-process ledger replay shims into the new class now."**
   Rejected: dec-006's per-process provenance-hash isolation for the TEST ledger
   path is preserved; the ledger subclasses stay in their current files.
4. **"Do the full state-authority consolidation in the first slice."** Rejected:
   Stage B is RNG-only; centralization and private-surface removal carry real
   parity risk and are deferred to Stage C behind an index-for-index parity gate.

## Invalidation triggers

This decision should be revisited (not silently re-affirmed) if any of the
following becomes true:

1. The dec-006 shared-stream premise is refuted (a future audit shows
   `chromosome.randStream` is NOT actually a single instance shared across the
   chromosome-binding processes for a given Karr build) — then the production
   single-stream authority loses its basis.
2. The serialized `[seed, mcg_state]` encoding is found insufficient to
   reconstruct the stream bit-identically (e.g. `mcg16807` state needs more than
   the two int64s), requiring a wider leaf schema.
3. A production code path is found constructing/reading a dec-006 ledger stream
   (would violate Decision #5's no-oracle-in-production rule).
4. Cross-run checkpoint of chromosome state becomes required (then
   `checkpoint.py` must be extended and Decision #6's deferral revisited).
5. The reviewed multi-consumer sequential commit owner + intents mechanism
   (design DC-9/DC-10) is implemented — a follow-on decision gate supersedes
   Decision #7's out-of-scope boundary for that stage.
6. The Stage-C centralization/parity gate shows the store-owned
   `sample_accessible_regions` cannot match the in-TxReg selection index-for-
   index (would reopen Decision #4's RNG-only boundary).

## Consequences

- NEW `opencell/util/chromosome_state_rand.py` (`ChromosomeStateRandStream`);
  the per-process dec-006 ledger subclasses remain in their current files.
- `opencell/state/chromosome_store.py` gains `CHROMOSOME_RAND_STREAM_KEY`, the
  narrow `rand_stream()`/`rand_state`/`set_rand_state` handle, and the
  `to_state`/`from_state_mapping` RNG round-trip (Stage A); store-centralized
  `sample_accessible_regions` is added later at Stage C.
- `opencell/vivarium/karr_transcriptional_regulation.py` swaps only the RNG
  provider at Stage B (candidate/accessibility logic unchanged); projection
  reads, footprint writeback, and private-surface removal land at Stage C.
- `opencell/vivarium/karr_composite.py` seeds the leaf once at initial-state
  construction and wires the TxReg `chromosome` port.
- `opencell/core/checkpoint.py` is explicitly NOT extended by this slice;
  cross-run chromosome checkpoint is a named, deferred follow-on.
- Production never constructs or reads a dec-006 ledger stream.

## Related Decisions

- **DEC-006** (`decisions/dec-006-shared-chromosome-randstream-input-oracle.md`,
  Active): the shared `Chromosome.randStream` captured draw ledger is a
  **test-only input oracle**. dec-007 is **additive** and **preserves** dec-006
  (does NOT supersede it): dec-006 continues to govern L2.1/replay harness input,
  while dec-007 governs the production state-owned stream. dec-006's own
  invalidation trigger ("A new process is found to consume the shared
  Chromosome.randStream and needs its own `<Process>ChromosomeLedgerRandStream`
  subclass registered") remains the mechanism for extending the test-side ledger
  family as later consumers migrate.
- **DEC-005** (`decisions/dec-005-full-simulation-source-hash-binding.md`,
  Active): source-hash binding for event-window traces; the ledger's
  `dnadamage_source_sha256` cross-check (a prerequisite for faithfully replaying
  any process that advances the shared stream, DNADamage included) is compatible
  with and unaffected by dec-007.
