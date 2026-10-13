# Shared Chromosome-State Subsystem — Design

**Status:** DESIGN (planner artifact; no production/test/wiring in this doc)
**Branch / base:** `design/shared-chromosome-state-20261013` from `76fd1d8`
(`docs(pre-l25): integrate first chromosome iterations`)
**Authors' source of truth:** executable MATLAB under
`E:\opencell\data\m1_sources\WholeCell`, per-process fixtures/traces, the
chromosome RNG ledger, and current OC `ChromosomeStore`/topology/processes.
No network.
**Scope class:** revision-class. Decision cards + source anchors + staged
claims/tests/STOP gates. This subsystem is the prerequisite for
TranscriptionalRegulation (TxReg) production repair blockers B–E; it is **not**
a rewrite of the chromosome state.

---

## 0. Thesis (one paragraph)

The chromosome **state** authority already exists and is already single:
`opencell.state.chromosome_store.ChromosomeStore` owns the 11 Karr chromosome
fields (incl. `monomerBoundSites`/`complexBoundSites`) and is wired through a
`chromosome` topology port into 8 of the 9 chromosome-binding processes. The
missing substrate is the chromosome **RNG** authority: Karr's single shared
`Chromosome.randStream` has been approximated in OC by *per-process* stand-in
streams (`TxRegMcgRandStream`, `ChromCondMcgRandStream`, DNASupercoiling's
release ledger, DNADamage's `KarrMcg16807Stream`), each independently seeded
and advanced. `decisions/dec-006` deliberately froze the **replay ledger** as a
test-only input oracle and states "Production code paths are unaffected" — i.e.
it explicitly left the *production* shared stream unbuilt. This design builds
exactly that one missing piece: a single serialized chromosome-state RNG stream,
owned by the existing state authority, that the chromosome accessibility/commit
draws advance in deterministic order — **without** inventing a second state
authority, without making per-process decision streams shared, without making
production depend on the ledger, and without landing two-column fold-change
before a real second chromosome copy and consumer exist.

---

## 1. Source anchors (verbatim, primary first)

### 1.1 MATLAB — chromosome state & RNG ownership

| Fact | Anchor |
|---|---|
| `monomerBoundSites`/`complexBoundSites` are `[positions x strands]` sparse mats; chromosome copies live in the strand/compartment columns | `+state\Chromosome.m:203-204`; alloc `:451-452` (`CircularSparseMat([],[],[sequenceLen,nCompartments,numTimePoints],1)`) |
| Bound-site values are protein/complex indices; widths from `monomerDNAFootprints`/`complexDNAFootprints` | `+state\Chromosome.m:180-185,398-399,1192-1194,1263-1265` |
| Weighted accessible-site sampling draws from the **Chromosome state** `this.randStream` | `+state\Chromosome.m:482-505` (`:502` `this.randStream.randsample(...)`); `:579-581,617-618` |
| Release-rate draws use the **Chromosome state** `this.randStream` | `+state\Chromosome.m:2423-2427` |
| Deterministic commit `setSiteProteinBound` writes indices (delegates sampling to `sampleAccessibleRegions`) | `+state\Chromosome.m:2025-2048,2100-2106` |
| Each **Process** has its own `randStream`; each **CellState** (Chromosome) has its own separate `randStream` | `Process.m:69-71,282-290`; `CellState.m:19-22,42-50`; `Chromosome.m:30` (`Chromosome < CellState`) |
| Streams are seeded identically (`mcg16807`); states serialized/restored separately | `Simulation.m:400-405,454-458` |
| Per-tick process order is a fresh **random permutation** on the Simulation's own `randStream`; each process does `copyFromState → evolveState → copyToState`; chromosome commit is via `copyToState` | `@Simulation\evolveState.m:44-53,56-72` |
| t=0 init order is deterministic `processesInInitOrder`; per process `copyFromState → initializeState → copyToState` | `@Simulation\initializeState.m:267-273`; `Simulation.m:596-597` |
| CC **region + position decisions** draw from the **process** stream, then bind explicit positions | `ChromosomeProcessAspect.m:44-120` (`:96` `this.randStream.randsample`; `:99` `this.randStream.rand`) |
| TxReg binds TFs with affinity weights; the weighted draw happens in `sampleAccessibleRegions` (chromosome stream), so TxReg has **no** process decision draw | `TranscriptionalRegulation.m:348-379` (`:376` `bindProteinToChromosome`) → `Chromosome.m:500-504` |
| TxReg fold-change matrix is `nTU x 2` (one column per chromosome copy); site surface is `N x 2` | `TranscriptionalRegulation.m:381-399,405-407` |
| TxReg/CC t=0 sweeps: TxReg `initializeState → evolveState`; CC `initializeState` = 20 warm-up `evolveState` under infinite ATP/H2O | `TranscriptionalRegulation.m:325-331`; `ChromosomeCondensation.m:220-230,256-268` |

### 1.2 OC — current state, RNG, topology

| Fact | Anchor |
|---|---|
| `ChromosomeStore` single state authority; 11 fields; binding write API takes **pre-selected** positions | `opencell\state\chromosome_store.py:13-25,583-600`; `set_site_protein_bound:884-1019`; `set_region_protein_unbound:811-883`; `from_state_mapping:1034-1062` |
| Per-process chromosome RNG shims — **byte-identical** MCG16807 (probe §9.2) | `opencell\util\chromcond_mcg_rand.py:35-170`; `opencell\util\txreg_mcg_rand.py:81-264` |
| Test-only ledger replay stream; fails closed; `assert_fully_consumed()` | `opencell\util\txreg_mcg_rand.py:333-380` |
| TxReg production stand-in for the shared stream is a single continuously-advancing per-process `TxRegMcgRandStream`; replay swaps a fresh ledger stream per tick | `opencell\vivarium\karr_transcriptional_regulation.py:726-759` |
| TxReg already reconstructs a `ChromosomeStore` from its state mapping but has no `chromosome` port | `karr_transcriptional_regulation.py:898-899` |
| TxReg two-column **site occupancy** is implemented; downstream `tx_rate_fold_change` collapses to column 0 | `karr_transcriptional_regulation.py:882-892,1593-1660` |
| TxReg topology maps only `protein/complex/tf_binding/tx_rate_fold_change` — **no `chromosome` port** (the lone chromosome-binder missing it) | `karr_composite.py:1469-1474` (dup `:2234-2239`) |
| 8 chromosome-binders already carry a `chromosome` port | `karr_composite.py:2295-2352` (repinit, replication, dna_supercoiling, chromosome_condensation, chromosome_segregation(+_evolution), dna_damage, dna_repair) |
| OC intra-tick order = deterministic Vivarium `flow` DAG (design D5), **not** Karr's per-tick `randperm` | `karr_composite.py:253-262,2633,2731-2745` |
| DNASupercoiling chromosome-release ledger (per-tick chromosome stream states + draws) already exists | `opencell\vivarium\dnas_chromosome_release_ledger.py:1-14,74-151` |
| Frozen decision: shared `Chromosome.randStream` ledger is a **test-only input oracle**; production unaffected | `decisions/dec-006-shared-chromosome-randstream-input-oracle.md` |

---

## 2. Decision cards

Each card: **Decision → Why → Rejected alternative → Anchor**. These are the
load-bearing choices; sections 3–9 implement them.

### DC-1 — One state authority: reuse `ChromosomeStore`; create no second
**Decision.** `monomerBoundSites`, `complexBoundSites`, the TF promoter
occupancy projection (`tf_bound_promoters`), and the bound-enzyme views are
owned by `ChromosomeStore`. No process keeps a private authoritative copy.
**Why.** The store already holds these fields and the deterministic commit API;
8/9 chromosome-binders already route through it. **Rejected:** a TxReg-local
`tf_bound_promoters` authority (current state, `:1593-1660`) — it is the
dual-authority defect TR-S5-02/03. **Anchor:** `chromosome_store.py:13-25,
884-1019`; `karr_composite.py:2295-2352`.

### DC-2 — One shared, serialized, state-owned chromosome RNG stream
**Decision.** Introduce exactly one production chromosome-state RNG stream,
owned by the chromosome state authority and **serialized into the chromosome
state mapping** so checkpoint/restart and trace round-trips carry it. It stands
in for Karr's `Chromosome.randStream`.
**Why.** Karr's `randStream` is a property of the Chromosome *state* object
(`Chromosome < CellState`), advanced by every chromosome-binder in a tick. A
state-owned, serialized stream is the faithful, single-authority mapping and
the only representation that survives OC's reconstruct-from-mapping-each-tick
chassis. **Rejected:** keeping per-process stand-ins (today's state) — they
cannot interleave and are structurally unfaithful for L2.2/L2.4; and a global
module singleton — it breaks determinism under checkpoint/restart and parallel
seeds. **Anchor:** `Chromosome.m:30`, `CellState.m:19-22,42-50`;
`Simulation.m:400-405`.

### DC-3 — MIXED RNG model: decision streams local, shared owns accessibility/commit
**Decision.** Per-process **decision** draws stay on each process's own local
stream. Only the chromosome **accessibility sampling** (`sampleAccessibleRegions`/
`sampleAccessibleSites`) and **release-rate** draws advance the shared stream.
**Why.** Source-exact: CC's region/position draws are `this.randStream` (process)
at `ChromosomeProcessAspect.m:96,99`; the accessible-site/weighted draw and
release-rate draw are `this.randStream` on the *chromosome state* at
`Chromosome.m:502,2423-2427`. TxReg has **no** process decision draw — its whole
stochastic step is the shared draw. **Rejected (pre-mortem):** treating all
process decision streams as shared — this would corrupt CC and DNASupercoiling
process-stream provenance. **Anchor:** as cited.

### DC-4 — Unify the proven-identical MCG shims into one stream class
**Decision.** Fold the byte-identical `TxRegMcgRandStream`/`ChromCondMcgRandStream`
arithmetic into a single `ChromosomeStateRandStream` (mcg16807; `get_state`/
`set_state` for serialization). Per-process **ledger-replay subclasses stay**
(dec-006 provenance isolation) and become thin adapters over the unified base.
**Why.** §9.2 proves the two shims yield identical `rand`, `randsample`, and
state round-trips across seeds {0,1,42,123456789}; two copies of one generator
is latent drift, not two authorities. **Rejected:** a brand-new generator — it
would be a *second* RNG authority (pre-mortem red line). **Anchor:**
`chromcond_mcg_rand.py:35-186`; `txreg_mcg_rand.py:81-264`; probe §9.2.

### DC-5 — Deterministic flow-DAG order now; Karr `randperm` scheduler deferred
**Decision.** In autonomous production the shared stream advances in the
**deterministic Vivarium `flow` topological order** of chromosome-binders, with
the request→allocation phase completing before the commit/chromosome-draw phase
(Karr's allocate-then-evolve). OC does **not** reproduce Karr's per-tick
`randperm` process order in this subsystem.
**Why.** Karr randomizes process order via the *Simulation* stream each tick
(`evolveState.m:44-53`); reproducing that is a whole-scheduler change and is the
only way to get bit-identical interleaving — which the dec-006 ledger already
supplies for *replay*. Autonomous runs need determinism + per-seed
reproducibility (L2.2/L2.4), not Karr-order bit-identity. The order is chosen
from the flow DAG, **never from the ledger/oracle**. **Rejected:** reading Karr's
per-tick order from the trace to order production draws — that is oracle-in-
production (pre-mortem red line). **Anchor:** `evolveState.m:44-72`;
`karr_composite.py:253-262,2731-2745`.

### DC-6 — Replay ledger stays a test-only input oracle (preserve dec-006)
**Decision.** The per-tick chromosome RNG ledger may **seed/verify test
execution** (L2.1 bit-identity, and later shared-stream composition replay) but
is **never** constructed or read by `next_update` in production. Preserve
dec-006's frozen schema and fail-closed over/under-consumption contract.
**Why.** dec-006 §Decision #3-5, §Consequences ("ONLY ever constructed and
injected by an L2.1 replay TEST harness"). **Rejected:** feeding the shared
production stream from the ledger — pre-mortem red line and dec-006 violation.
**Anchor:** `dec-006`; `txreg_mcg_rand.py:333-380`;
`dnas_chromosome_release_ledger.py:122-151`.

### DC-7 — Defer two-column fold-change to a joint later stage
**Decision.** Keep two-column **site occupancy** (already implemented) but keep
emitting single-copy (`column 0`) `tx_rate_fold_change`. Two-column fold-change
emission is deferred to a joint TR + DNASupercoiling + Transcription +
Replication stage.
**Why.** A real second chromosome copy only exists after Replication populates
the second strand pair, and no current consumer reads a per-copy fold-change
(`tx_rate_fold_change` is scalar per TU). Emitting two columns now writes an
unconsumed, unvalidatable surface. **Rejected:** landing `nTU x 2` now
(pre-mortem red line). **Anchor:** `TranscriptionalRegulation.m:381-399`;
`karr_transcriptional_regulation.py:1598-1608`; `karr_composite.py:2308-2316`
(DNASupercoiling already consumes `tx_rate_fold_change`).

### DC-8 — CC reconciliation: CC decision RNG stays local; shared-commit participation represented but not required for CC Iter 2
**Decision.** ChromosomeCondensation keeps its process-local decision stream.
Its participation in the **shared commit draw** is *represented* in the stream
contract (so later composition composes correctly) but CC Iteration 2 (same-tick
request→allocation→consume) proceeds independently and is **not** gated on this
subsystem.
**Why.** CC's stochastic decisions are process-stream (DC-3). Its commit passes
**explicit** positions with **empty weights**, so `sampleAccessibleRegions`
draws zero extra sites (`Chromosome.m:500` `nMoreSites =
min(max(2*(nSites-numel(idxs)),10), nnz(weights))`, with `weights=[]` ⇒
`nnz=0` ⇒ `0`) — CC's shared-stream consumption is conditional/minimal.
**Rejected:** forcing CC onto the shared stream now (would couple CC Iter 2 to
this design and risk a false second consumer). **Anchor:**
`ChromosomeProcessAspect.m:44-120`; `Chromosome.m:500-504`.

---

## 3. Canonical ownership & representation (SLOT 3.1)

`ChromosomeStore` remains the sole authority. The four surfaces TxReg B–E need:

| Surface | Canonical representation | Store anchor |
|---|---|---|
| `monomerBoundSites` | sparse `(position, strand, monomer_index)` triplet; `strand` columns are chromosome copies/strands; value = global monomer index | `chromosome_store.py:13-25` field; commit `set_site_protein_bound(field_name="monomerBoundSites", …)` `:884-1019` |
| `complexBoundSites` | sparse `(position, strand, complex_index)` triplet | same, `field_name="complexBoundSites"` |
| TF promoter occupancy projection (`tf_bound_promoters`) | derived `(n_sites, 2)` boolean view over `monomer/complexBoundSites` at TF `tfPositionStrands`; the two columns are the two chromosome copies | MATLAB derivation `TranscriptionalRegulation.m:405-407` (`reshape(isDnaBound(...),[],2)`); OC read `karr_transcriptional_regulation.py:882-892` |
| Bound enzyme views (CC `boundEnzymes`, TxReg bound-TF counts) | read-through of bound-site occupancy by enzyme global index; **not** a private counter | CC `karr_composite.py:2317-2323`; MATLAB `ChromosomeCondensation.m:256-258` |

**Key representational decision.** MATLAB's `setSiteProteinBound` fuses *(a)*
stochastic accessible-site sampling (draws on chromosome `randStream`) with
*(b)* the deterministic index write. OC already split these: *(b)* lives in
`ChromosomeStore.set_site_protein_bound` (takes pre-selected `positions/strands`),
*(a)* lives in the process. This subsystem **re-homes (a)** onto the shared
state-owned stream by adding a `sample_accessible_regions(...)` method to
`ChromosomeStore` that draws from the store's own stream (DC-2) and returns the
selected positions, which the caller then commits via the existing
`set_site_protein_bound`. `tf_bound_promoters`/`bound_tfs` become **projections**
of the committed bound-site state, not a parallel authority (removes TR-S5-02).

---

## 4. Mixed RNG model — API, state, seeding, checkpoint, advance (SLOT 2)

### 4.1 Streams
- **Process decision stream** — one per process, unchanged (`Process.randStream`
  analogue). CC region/position; DNASupercoiling process draws. Local, seeded
  from the process seed. Not touched here.
- **Shared chromosome-state stream** — one per cell, `ChromosomeStateRandStream`
  (DC-4), owned by `ChromosomeStore`. Advances only on accessibility/commit/
  release draws (DC-3).

### 4.2 API (production)
```
ChromosomeStore.sample_accessible_regions(weights, positions, strands, lengths,
    footprints, …) -> selected positions/strands   # draws on store stream
ChromosomeStore.set_site_protein_bound(positions=…, strands=…, …)  # deterministic
ChromosomeStore.rand_state() -> opaque scalar       # get_state (serialization)
ChromosomeStore.set_rand_state(state)               # set_state (restore)
```
The store stream exposes `rand/randi/randperm/randsample/get_state/set_state`
(already present on the shims, DC-4). No process constructs its own shared
stream; processes receive the store (already wired via the `chromosome` port)
and call `sample_accessible_regions`.

### 4.3 State representation & seeding
- Stream state = `{"generator":"mcg16807","seed":…,"mcg_state":…}`
  (`txreg_mcg_rand.py:156-170`). Serialized as one scalar in the `chromosome`
  state mapping under a new reserved key (e.g. `chromosome` ⇒
  `_shared_rand_stream_state`), round-tripped by
  `ChromosomeStore.to_state`/`from_state_mapping` (`:1022-1062`).
- Seeded once from the run seed at `t0` (DC-2); default to a freshly-seeded
  stream when the key is **absent** (back-compat for existing traces, §8/§11).

### 4.4 Checkpoint / restart
Because the stream state lives inside the serialized chromosome state, HDF5
trace tick snapshots and chassis checkpoints already persist/restore it via the
existing chromosome state (de)serialization. **STOP gate:** a
dump→reload→continue probe must reproduce the next N draws bit-identically
before any second consumer is added.

### 4.5 How process order advances it
Within a tick, each chromosome-binder that reaches its commit phase pulls its
accessibility draws from the single store stream in flow-DAG order (DC-5); the
stream's `mcg_state` monotonically advances; `copyToState`-equivalent writeback
persists both the bound-site deltas and the advanced stream state.

---

## 5. Participant enumeration (SLOT 3.3)

**Verified shared-stream participants (MATLAB draws on `Chromosome.randStream`
via the bind/sample/release family):**

| Process | MATLAB anchor | OC `chromosome` port today | Role |
|---|---|---|---|
| TranscriptionalRegulation | `TranscriptionalRegulation.m:376` → `Chromosome.m:502` | **No** (`karr_composite.py:1469-1474`) | write TF + **sole** shared-draw consumer (no process stream) |
| Transcription | `Transcription.m:505-506,807-808` (stochastic bind) | n/a (no store import today) | write RNAP, read occupancy |
| DNASupercoiling | `DNASupercoiling.m:325-326,382-388,464-465` | Yes `:2308` | bind gyrase/topoIV, release (release-rate draw), read |
| DNARepair | `DNARepair.m:963-1043,1344` | Yes `:2344` | bind repair enzymes |
| Replication | `Replication.m:660,748-751,1265-1268` | Yes `:2302` | bind/release pol/helicase/clamp, read |
| ReplicationInitiation | `ReplicationInitiation.m:410-412,464-465,596` | Yes `:2295` | bind DnaA, read |
| ChromosomeCondensation | `ChromosomeCondensation.m:256-268` | Yes `:2317` | **decision on process stream** (DC-8); commit draw conditional/minimal |

**Deferred / non-participants (no bound-site bind/sample/release call found):**
`FtsZPolymerization`, `ChromosomeSegregation` (reads copy structure, no
bind/sample/release). Cytokinesis reads `chromosome` but does not sample.

**Migration posture:** only **TxReg** migrates onto the shared stream in this
subsystem's first stages. Transcription/DNASupercoiling/DNARepair/Replication/
RepInit are **enrolled in the contract** (so the stream is designed to compose)
but their draw-routing migration is sequenced later and is **not faked** —
each moves only when its own iteration runs.

---

## 6. Deterministic intra-tick ordering contract (SLOT 4)

1. **Phases per tick (Karr `evolveState` mapped to OC):**
   `request` → `allocation` (allocator grants) → `evolve/commit` (chromosome
   accessibility + bound-site writeback). Matches Karr allocate-then-evolve
   (`evolveState.m:56-72`; request/allocation already separate OC steps).
2. **Chromosome-draw order within the commit phase:** the fixed topological
   order of chromosome-binders in the Vivarium `flow` DAG (DC-5). Stable across
   ticks and seeds; it is the production order contract.
3. **No oracle in the order choice.** The order is derived from the flow DAG,
   not from the trace/ledger. Bit-identity to Karr's randomized order is a
   **replay-only** property supplied by the dec-006 ledger.
4. **Single-consumer invariant (first stages).** While TxReg is the sole
   migrated consumer, order is trivially well-defined; multi-consumer ordering
   is only exercised when a second process migrates (later stage), gated by a
   STOP test (§10).

---

## 7. Unified t0 initialization sweep (SLOT 5)

**Karr.** `initializeState` runs in deterministic `processesInInitOrder`;
`copyFromState → initializeState → copyToState` per process
(`initializeState.m:267-273`). TxReg `initializeState` calls `evolveState`
(binds TFs at t0 on the shared stream, `TranscriptionalRegulation.m:325-331`).
CC runs 20 warm-up `evolveState` under infinite ATP/H2O on its **process**
stream (`ChromosomeCondensation.m:220-230`).

**OC unified sweep (staged).**
1. Seed the shared chromosome stream once at `t0` into the chromosome
   `initial_state` (DC-2/§4.3).
2. Run a deterministic t0 binding pass over **only the processes that have a
   genuine OC initializeState path** — first stage = **TxReg pre-binding sweep**
   (currently absent, TR-S6-03). CC's 20-step warm-up stays on its own process
   stream and is out of scope (DC-8).
3. Persist the advanced stream state + bound-site deltas into `initial_state`
   so tick 1 continues from the exact post-init stream position.
4. **Staged rollout, no faking.** Processes without an OC init-binding path are
   **not** warmed up with invented draws; they join when their iteration lands.
   The init order for migrated processes follows Karr's `initOrder` for those
   processes only.

**STOP gate:** t0 sweep must leave the single-seed replay baseline (trace
`645a2e68…`, ledger `ac2426dc…`, draw digest `88c7c28c…`, 135 active ticks /
378 draws) bit-identical under the dec-006 replay harness.

---

## 8. TxReg topology migration (SLOT 6)

Current defect set: TR-S5-02 (no shared bound-site writeback), TR-S5-03 (no
`chromosome` port), TR-S6-02 (per-process stand-in stream), TR-S6-03 (no t0
sweep). Migration, in dependency order:

1. **Add the `chromosome` port** to TxReg topology (mirror the 8 wired
   processes, `karr_composite.py:2295-2352`): `"chromosome": ("chromosome",)`
   on both composite mappings (`:1469-1474`, `:2234-2239`).
2. **Read authoritative occupancy** (`tf_bound_promoters`, `bound_tfs`) as
   **projections** of `monomer/complexBoundSites` from the store, replacing the
   TxReg-local occupancy read (`:882-892`).
3. **Shared footprint writeback.** TF binds commit through
   `ChromosomeStore.set_site_protein_bound` (writes `monomer/complexBoundSites`),
   so downstream accessibility (Transcription/DNASupercoiling) sees TF
   footprints — closing TR-S5-02.
4. **Route the binding draw** through `ChromosomeStore.sample_accessible_regions`
   on the shared stream (replaces `_chromosome_rng`, `:759,1365-1374`).
5. **Remove the private dual authority only after readers migrate.** The
   TxReg-local `tf_bound_promoters` map is deleted only once the projection read
   (step 2) and any other reader are confirmed on the store (removal schedule
   §11).
6. **enzymes/boundEnzymes writeback** wired like CC (`:2317-2323`) so free/bound
   TF copy counts are authoritative.

---

## 9. Two-column fold-change deferral & prerequisites (SLOT 7)

Deferred to a **joint TR + DNASupercoiling + Transcription + Replication**
stage. Prerequisites before it may start:
1. Replication populates a real second strand pair (second chromosome copy) in
   the OC chassis, not a stub.
2. A real consumer reads per-copy fold-change: `tx_rate_fold_change` port
   widened from scalar-per-TU to `(TU, copy)` and consumed by Transcription
   initiation.
3. Shared bound-site writeback (§8) live for both copies so column-1 occupancy
   is populated by actual binds.
4. Multi-copy accessibility validated against a two-copy fixture/trace.
Until all four hold, keep column-0 emission (`karr_transcriptional_regulation.py:
1598-1608`).

---

## 10. Replay adapter boundary & anti-oracle tests (SLOT 8)

**Boundary.** The dec-006 ledger seeds/verifies **test** execution only:
- Production `next_update` constructs `ChromosomeStateRandStream` (seeded),
  never a ledger stream (DC-6).
- An L2.1 replay harness replaces the store stream, per tick, with a
  fresh ledger-replay adapter (`txreg_mcg_rand.py:333-380`), restoring Karr's
  exact per-tick input position (dec-006 §Decision #2-3).

**Anti-oracle tests (must exist for each migrated consumer):**
- **AO-1 No-ledger-in-production:** assert the production code path never
  imports/constructs a `*LedgerRandStream` nor reads a ledger file (static +
  runtime import guard).
- **AO-2 Fail-closed:** over-consumption raises (`RuntimeError`, probe §9.2
  confirmed), under-consumption trips `assert_fully_consumed()`
  (`txreg_mcg_rand.py:333-380`).
- **AO-3 Ledger-binding:** a ledger bound to a different trace SHA or different
  `Chromosome.m`/`RandStream.m` source bytes fails closed (dec-006 §Decision #3).
- **AO-4 Order-not-from-oracle:** mutate the trace's recorded per-tick process
  order and assert the **production** draw order (flow DAG) is unchanged
  (guards DC-5).

---

## 11. Migration stages (SLOT 9) & first slice

Stages sized for sequential test-writer → implementer → reviewer loops. Each
ends at a STOP gate (§12 tests).

- **Stage A — Substrate, behavior-neutral.** Add `ChromosomeStateRandStream`
  (DC-4, unify shims) + serialized stream state in the chromosome mapping +
  `ChromosomeStore.sample_accessible_regions`/`rand_state`. **No consumer wired.**
  Rollback = revert; no flag. Behavior-neutral (like the D5 pre/post pattern,
  `karr_composite.py:253-262`).
- **Stage B — TxReg sole consumer (FIRST IMPLEMENTABLE SLICE).** Add TxReg
  `chromosome` port; route the TxReg binding draw through
  `sample_accessible_regions` on the shared stream; keep projection reads. With
  TxReg the only consumer, the draw **sequence is unchanged** vs the current
  per-process stand-in, so the single-seed replay baseline stays bit-identical.
- **Stage C — Shared writeback + authority removal.** Commit TF footprints to
  `monomer/complexBoundSites`; switch `tf_bound_promoters`/`bound_tfs` to store
  projections; delete the TxReg-local occupancy authority.
- **Stage D — TxReg t0 pre-binding sweep** (§7) on the shared stream.
- **Stage E+ — Second consumer** (Transcription or DNASupercoiling): exercises
  true multi-consumer flow-DAG ordering (DC-5) and footprint cross-visibility.
- **Deferred joint stage** — two-column fold-change (§9).

**Why Stage B is the lowest-risk first slice (not big-bang):**
1. **Single consumer** ⇒ no interleaving semantics to get right yet.
2. **TxReg has no process decision stream** ⇒ no mixed-stream split to
   implement; the whole TxReg stochastic step maps 1:1 to the shared draw.
3. **Draw sequence is preserved** for a TxReg-only run ⇒ the existing dec-006
   L2.1 replay is a ready bit-identity falsification test, not a rewrite.
4. **Two-column fold-change and scheduler `randperm` are deferred** ⇒ the
   hardest, lowest-value pieces are out of the first slice.
A big-bang migration (all 7 binders + shared ordering + two-column + t0 at once)
would entangle the untestable scheduler-permutation faithfulness with the
testable single-consumer refactor and has no intermediate green gate.

---

## 12. Falsifiable tests & planted mutations (SLOT 10)

| Stage | Falsifiable claim | Test | Planted mutation that MUST fail it |
|---|---|---|---|
| A | stream state round-trips | dump→`set_state`→continue draws equal | perturb one `mcg_state` bit ⇒ divergent draws |
| A | unified stream == old shims | parametrized equivalence over seeds | change a multiplier/modulus ⇒ mismatch |
| B | TxReg-only draw sequence unchanged | dec-006 L2.1 replay bit-identity (trace `645a2e68…`) | advance shared stream by one extra draw ⇒ ledger exhaustion (AO-2) |
| B | `chromosome` port present & read | topology schema assert | drop the port ⇒ KeyError/none |
| C | TF footprints visible to readers | after TxReg bind, `complexBoundSites` has the TF index at `tfPositionStrands` | skip writeback ⇒ occupancy absent |
| C | no dual authority | single-source read assert | reintroduce local map ⇒ divergence vs store |
| D | t0 sweep bit-identical | replay from `initial_state` | reorder/duplicate t0 binds ⇒ draw-digest change |
| E | multi-consumer order deterministic | two-seed, two-consumer order stable | shuffle flow edges ⇒ order change (AO-4 guards against oracle order) |

**Evidence impacts.**
- **L2.1 (bit-identity, σ=0):** unchanged through Stage D (single consumer,
  preserved sequence); the dec-006 ledger remains the oracle.
- **L2.2 (distributional):** the shared stream is the *enabling* substrate; a
  genuine multi-seed TxReg distribution becomes possible once the stream is
  state-owned and seed-parameterized — but **multi-seed oracle traces do not
  exist** (only seed 0; `dec-006` "only seed 0 exists"), so L2.2 closure for
  TxReg remains **blocked on data**, not on this design.
- **L2.4 (chassis conservation):** Stage B/C must keep `INTEGRITY_OK 5/28` and
  the L1b 115/115, 28/28 and 27/27 regressions green; the stream adds no mass/
  energy and must not change conservation.

---

## 13. Blast radius, schema/topology, compatibility, rollback (SLOT 11)

**Files (expected edits, by stage):**
- NEW `opencell/util/chromosome_state_rand.py` — unified
  `ChromosomeStateRandStream` (Stage A). Per-process ledger subclasses remain in
  their current files (dec-006).
- MODIFY `opencell/state/chromosome_store.py` — attach/serialize stream state;
  add `sample_accessible_regions`, `rand_state`/`set_rand_state` (A).
- MODIFY `opencell/vivarium/karr_transcriptional_regulation.py` — consume shared
  stream; projection reads; footprint writeback; t0 sweep (B–D).
- MODIFY `opencell/vivarium/karr_composite.py` — add TxReg `chromosome` port
  (both mappings); serialize stream state in chromosome `initial_state` (B).
- TEST (separate authors) — Stage A/B/C/D suites + anti-oracle tests (§10).
- DEC (at implementation time, not here) — author **dec-007** referencing
  dec-006: dec-006 governs the *test* ledger oracle and stays in force; dec-007
  adds the *production* single shared stream (the gap dec-006 left — "production
  code paths are unaffected"). dec-007 does **not** supersede dec-006; it is
  additive and compatible.

**Schema/topology changes:**
- Topology: `+1` port (`chromosome`) on TxReg (both composite mappings).
- Chromosome state mapping: `+1` reserved scalar (`_shared_rand_stream_state`).
  Back-compat: **absent ⇒ freshly seeded stream** (existing traces unaffected;
  no re-extraction required to load).

**Compatibility removal schedule:**
- TxReg-local `tf_bound_promoters` authority removed at **Stage C** (only after
  projection readers migrate) — not before.
- Per-process production stand-in `_chromosome_rng` in TxReg removed at
  **Stage B** (replaced by the store stream).
- `_rng` (unused process stand-in, `:725`) left as-is (dec-006 posture).

**Rollback / feature-gate policy:** **prefer no permanent flag.** Each stage is
behavior-neutral or baseline-preserving, so rollback = revert the stage commit.
A **transient** config toggle is acceptable only within Stage E (first
multi-consumer bring-up) and must be removed in the same stage once the STOP
gate is green; no flag may persist past its stage.

---

## 14. CC reconciliation (SLOT 12)

- CC's **local decision RNG remains** (process stream; region/position draws,
  `ChromosomeProcessAspect.m:96,99`). This subsystem does not touch it.
- CC's **shared-commit participation is represented**: the stream contract
  (§4, §6) documents that CC's commit *may* conditionally advance the shared
  stream (empty-weights explicit-position binds draw zero extra sites today,
  DC-8), so when CC later composes with TxReg on the shared stream the ordering
  and draw-accounting already account for a (currently zero-draw) CC slot.
- **CC Iteration 2 proceeds independently.** Its same-tick
  request→allocation→consume repair (plan "Next iterative round" item 1) does
  not depend on, and is not blocked by, this subsystem; the two iterations do
  not edit the same shared chromosome production surface concurrently.

---

## 15. Recommended first implementation slice

**Stage A + Stage B.** Ship the shared-stream substrate (unified
`ChromosomeStateRandStream`, serialized stream state, store API) and wire
**TxReg as the sole consumer** with the `chromosome` port — stopping *before*
footprint-authority removal (Stage C). Rationale: §11 points 1–4. The STOP gate
is the dec-006 L2.1 single-seed replay staying bit-identical plus
`INTEGRITY_OK 5/28` and L1b/baseline regressions green.

---

## 16. Non-goals (explicit)

1. No second chromosome state authority; `ChromosomeStore` is reused (DC-1).
2. No making process **decision** streams shared (DC-3).
3. No production dependency on any ledger/oracle (DC-6).
4. No Karr `randperm` scheduler reproduction here (DC-5).
5. No two-column fold-change here (DC-7).
6. No CC forced onto the shared stream; no CC Iter-2 coupling (DC-8).
7. No multi-seed L2.2 closure (blocked on nonexistent multi-seed traces).
8. No edits to production/tests/audit/wiring/evidence/baseline/catalog in this
   planner artifact.

---

## 17. Unresolved questions

1. **Stream state key placement.** Nest `_shared_rand_stream_state` inside the
   `chromosome` mapping vs a sibling top-level state key — resolve against the
   HDF5 trace loader (`from_state_mapping`/`from_trace_tick`,
   `chromosome_store.py:1034-1100`) so existing seed-0 traces still load.
2. **Flow-DAG order vs Karr init order at t0.** The t0 sweep order for migrated
   processes should match Karr `processesInInitOrder`; confirm the OC flow DAG
   does not contradict it for the TxReg-only first slice (it cannot, single
   consumer) and define the rule before Stage E.
3. **dec-007 vs dec-006 boundary wording.** Exact phrasing that dec-006's
   test-only oracle stays in force while dec-007 governs production — author at
   implementation time; do not edit decision cards in this planner pass.
4. **`sample_accessible_regions` scope on the store.** How much of MATLAB's
   `isRegionAccessible`/`getReleasableProteins` accessibility logic
   (`Chromosome.m:651-752`) already lives in TxReg vs must move to the store to
   keep the draw count identical — verify draw-count parity under the ledger
   before Stage C.
5. **Second-consumer selection** (Stage E): Transcription vs DNASupercoiling —
   pick by which has an existing fixture/trace enabling a draw-order STOP test.

---

## 18. Acceptance matrix

| # | Requirement | Acceptance criterion | Stage |
|---|---|---|---|
| A1 | Single state authority | no new authoritative bound-site store; TxReg reads/writes `ChromosomeStore` | C |
| A2 | Single serialized shared RNG stream | one `ChromosomeStateRandStream`; state in chromosome mapping; checkpoint round-trip bit-identical | A |
| A3 | MIXED model exact | process decision draws unchanged; only accessibility/commit/release advance shared stream | B |
| A4 | Participants enumerated | §5 table with MATLAB file:line; verified vs deferred distinguished | (doc) |
| A5 | Deterministic order, no oracle | production draw order from flow DAG; AO-4 passes | B/E |
| A6 | Unified t0 sweep | TxReg t0 pre-binding sweep; replay baseline bit-identical; no faked processes | D |
| A7 | TxReg topology migrated | `chromosome` port present; writeback live; dual authority removed | B/C |
| A8 | Two-column fold-change deferred | column-0 emission retained; prerequisites §9 listed | — |
| A9 | Replay is test-only | AO-1/AO-2/AO-3 pass; no ledger in production path | B+ |
| A10 | Small sequential slices | each stage has an independent STOP gate | all |
| A11 | Falsifiable tests + mutations | §12 table; each planted mutation fails its test | per stage |
| A12 | Evidence impact stated | L2.1 preserved; L2.2 blocked-on-data; L2.4 `INTEGRITY_OK 5/28` held | per stage |
| A13 | Blast radius/schema/rollback | §13; back-compat absent-key default; no permanent flag | all |
| A14 | CC reconciled | CC decision RNG local; shared-commit represented; CC Iter 2 independent | (doc) |

---

## 19. Provenance & probe appendix

- **Base HEAD:** `76fd1d8` (verified clean worktree, nothing pushed).
- **Probe P1 (MCG shim equivalence, WSL venv).** `ChromCondMcgRandStream` vs
  `TxRegMcgRandStream` over seeds {0,1,42,123456789}: `rand` equal, weighted
  `randsample` equal, `get_state`/`set_state` round-trip equal — `ALL_EQUIVALENT=True`.
  Supports DC-4.
- **Probe P2 (ledger fail-closed).** `TxRegChromosomeLedgerRandStream`
  over-consumption raises `RuntimeError` — `LEDGER_FAILCLOSED=True`. Supports
  DC-6 / AO-2.
- **Probe P3 (source anchoring).** All §1 MATLAB/OC citations verified against
  files on disk under `E:\opencell\data\m1_sources\WholeCell` and the worktree.
- **Canonical replay baseline referenced:** trace `645a2e68…`, ledger
  `ac2426dc…`, draw digest `88c7c28c…`, 135 active ticks / 378 draws (plan
  operational-handoff, 2026-10-13).
