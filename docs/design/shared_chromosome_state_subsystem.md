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
| Weighted accessible-site sampling draws from the **Chromosome state** `this.randStream`; **empty `weights` are normalized to ones** before sampling, so any commit with `maxBindings≥1` and ≥1 candidate advances the stream | `+state\Chromosome.m:482-505` (`:493-494` `weights = ones(...)`; `:500-502` `this.randStream.randsample(...)`); `:579-581,617-618` |
| `bindProteinToChromosome` early-returns with **zero draws only when `maxBindings==0`** (no candidates / nothing to bind); else empty weights→ones and commit draws | `ChromosomeProcessAspect.m:286-345` (`:294-303` early return; `:308-310` ones; `:342` `setSiteProteinBound`) → `Chromosome.m:2043` |
| DNADamage draws reaction **order** from its **process** stream, and damage-**site** selection from the **Chromosome state** `this.randStream` via `setSiteDamaged` | `+process\DNADamage.m:537` (`randStream.randperm`), `:559` (`chromosome.setSiteDamaged`) → `Chromosome.m:2490+` (`sampleAccessibleSites`/`stochasticRound`/`randomlySelectNRows`) |
| DNADamage has an **empty `initializeState`** (no t0 damage sweep) | `+process\DNADamage.m:465` (`function initializeState(~)`) |
| Release-rate draws use the **Chromosome state** `this.randStream` | `+state\Chromosome.m:2423-2427` |
| Deterministic commit `setSiteProteinBound` writes indices (delegates sampling to `sampleAccessibleRegions`) | `+state\Chromosome.m:2025-2048,2100-2106` |
| Each **Process** has its own `randStream`; each **CellState** (Chromosome) has its own separate `randStream` | `Process.m:69-71,282-290`; `CellState.m:19-22,42-50`; `Chromosome.m:30` (`Chromosome < CellState`) |
| Streams are seeded identically (`mcg16807`); states serialized/restored separately | `Simulation.m:400-405,454-458` |
| Per-tick process order is a fresh **random permutation** on the Simulation's own `randStream`; each process does `copyFromState → evolveState → copyToState`; chromosome commit is via `copyToState` | `@Simulation\evolveState.m:44-53,56-72` |
| t=0 init order is deterministic `processesInInitOrder`; per process `copyFromState → initializeState → copyToState` | `@Simulation\initializeState.m:267-273`; `Simulation.m:596-597` |
| CC **region + position decisions** draw from the **process** stream, then the **commit draws from the shared chromosome stream** (empty weights→ones) on every real bind | `ChromosomeProcessAspect.m:44-120` (`:96` `randStream.randsample`; `:99` `randStream.rand`), commit `:286-345` → `Chromosome.m:493-494,500-502` |
| TxReg binds TFs with affinity weights; the weighted draw happens in `sampleAccessibleRegions` (chromosome stream), so TxReg has **no** process decision draw | `TranscriptionalRegulation.m:348-379` (`:376` `bindProteinToChromosome`) → `Chromosome.m:500-504` |
| TxReg fold-change matrix is `nTU x 2` (one column per chromosome copy); site surface is `N x 2` | `TranscriptionalRegulation.m:381-399,405-407` |
| TxReg/CC t=0 sweeps: TxReg `initializeState → evolveState`; CC `initializeState` = 20 warm-up `evolveState` under infinite ATP/H2O | `TranscriptionalRegulation.m:325-331`; `ChromosomeCondensation.m:220-230,256-268` |

### 1.2 OC — current state, RNG, topology

| Fact | Anchor |
|---|---|
| `ChromosomeStore` single state authority; 11 fields; binding write API takes **pre-selected** positions | `opencell\state\chromosome_store.py:13-25,583-600`; `set_site_protein_bound:884-1019`; `set_region_protein_unbound:811-883`; `from_state_mapping:1034-1062` |
| Per-process chromosome RNG shims — **byte-identical** MCG16807 (probe §19 P1) | `opencell\util\chromcond_mcg_rand.py:35-170`; `opencell\util\txreg_mcg_rand.py:81-264` |
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
**Why.** §19 P1 proves the two shims yield identical `rand`, `randsample`, and
state round-trips across seeds {0,1,42,123456789}; two copies of one generator
is latent drift, not two authorities. **Rejected:** a brand-new generator — it
would be a *second* RNG authority (pre-mortem red line). **Anchor:**
`chromcond_mcg_rand.py:35-186`; `txreg_mcg_rand.py:81-264`; probe §19 P1.

### DC-5 — Deterministic commit-owner order; Karr `randperm` scheduler deferred
**Decision.** Chromosome accessibility/commit/release draws are serialized by a
single sequential **chromosome-commit owner** (a Vivarium Step, DC-9) in a fixed
deterministic canonical order — **not** by the process `flow` DAG and **not** by
in-place draws inside each process's `next_update`. OC does not reproduce Karr's
per-tick `randperm` process order in this subsystem.
**Why.** Probe P6 (§19) proves ordinary Vivarium Processes each compute
`next_update` from the **same tick-start store view** — `engine.py run_for`
buffers every process update in `self.front` and applies them via
`_send_updates` only after all processes have computed; a stream mutated
in-place by process A is invisible to process B in that tick (and in-place
mutation is not even a declared update). Steps run after the process phase and
**do** see merged state (P6). Hence the only correct multi-consumer mechanism is
one owner advancing the single stream sequentially — which is also source-
faithful, since Karr's chromosome draws all occur inside the one `Chromosome`
state object as each `evolveState` calls into it. The canonical order is fixed
(not Karr `randperm`, deferred; not read from the oracle). **Rejected:** flow-DAG
ordering of per-process in-place draws (empirically broken, P6); reading Karr's
per-tick order from the trace (oracle-in-production red line). **Anchor:**
`engine.py` `run_for`/`_send_updates` (§19 P6); `evolveState.m:44-72`;
`Chromosome.m` `setSiteProteinBound`/`setSiteDamaged`.

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

### DC-8 — CC reconciliation: CC decision RNG local; CC **is** a shared-commit consumer; CC Iter 2 still independent
**Decision.** ChromosomeCondensation keeps its process-local **decision** stream
(region/position). Its **commit draws from the shared chromosome stream on every
real bind** and MUST be represented as a genuine shared-stream consumer in the
ordering/draw-accounting (DC-9). CC Iteration 2 (same-tick request→allocation→
consume) still proceeds independently — it concerns allocation timing, not the
shared RNG stream.
**Why — CORRECTED (prior "zero-draw" claim was wrong).**
`bindProteinToChromosome` early-returns with zero draws **only when
`maxBindings==0`** (no candidate positions, or nothing to bind;
`ChromosomeProcessAspect.m:294-303`). Otherwise empty `weights` are normalized
to ones (`:308-310`, and again in `sampleAccessibleRegions`,
`Chromosome.m:493-494`), so `nnz(weights)>0`; `setSiteProteinBound:2043` always
calls `sampleAccessibleRegions`, whose `this.randStream.randsample`
(`Chromosome.m:500-502`) advances the shared stream. Thus CC draws from **both**
streams: process (region/position, `ChromosomeProcessAspect.m:96,99`) and shared
chromosome (commit resample among CC's pre-selected positions). The exact
zero-draw condition is `maxBindings==0` only. CC Iter 2 stays independent because
its allocation-timing repair neither needs nor edits the shared stream.
**Rejected:** treating CC commit as zero/negligible draw (source-refuted);
coupling CC Iter-2 to this subsystem (false dependency). **Anchor:**
`ChromosomeProcessAspect.m:286-345`; `Chromosome.m:493-494,500-502,2043`.

### DC-9 — Single sequential chromosome-commit owner (Step) receives intents
**Decision.** For any stage with **more than one** shared-stream consumer,
introduce one `ChromosomeCommitStep` (Vivarium Step) that owns the shared
chromosome state + stream. Chromosome-binding processes emit binding/damage
**intents** (enzyme, process-stream-selected candidate positions/weights,
`maxBindings`) as updates to an intent-buffer port during the process phase. The
Step, running after that phase via the `flow` DAG, consumes the merged intents
in a fixed canonical order and — per intent — runs accessibility+selection
drawing from the single shared stream against the **accumulating** chromosome
state, commits bound-sites/damage via `set_site_protein_bound`/`setSiteDamaged`,
and advances the stream once. The single-consumer stages (B–D) are the explicit
exception: TxReg, as sole consumer, may draw within its own `next_update` and
write back the stream state (no cross-process visibility problem).
**Why.** Only a single owner can serialize shared draws across consumers under
Vivarium's compute-from-tick-start-state model (DC-5/P6); Steps see merged
post-process state (P6), so intents emitted by processes are visible to the Step.
It is source-faithful: Karr advances the one `Chromosome.randStream` sequentially
as each `evolveState` calls into the single state object. **Rejected:** each
process drawing+writing the stream in its own `next_update` beyond one consumer
(P6-broken, collides draws). **Anchor:** §19 P6; `engine.py` `run_steps`;
`Chromosome.m setSiteProteinBound/setSiteDamaged`.

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
(already present on the shims, §19 P1). No process constructs its own shared
stream. **Single consumer (Stages B–D):** TxReg receives the store (via the
`chromosome` port) and calls `sample_accessible_regions` directly. **Multiple
consumers (Stage E+):** processes do not call it; they emit intents and the DC-9
`ChromosomeCommitStep` owner calls `sample_accessible_regions` on their behalf,
in canonical order, against the accumulating state.

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

### 4.5 How the stream advances within a tick
- **Single consumer (Stages B–D):** TxReg draws from the store stream inside its
  own `next_update` (reading the serialized tick-start stream state) and writes
  the advanced stream state back as a `set`-updater scalar. Correct because
  TxReg is the only consumer, so no other process reads/advances the stream that
  tick (DC-9 exception).
- **Multiple consumers (Stage E+):** processes do **not** draw in-place
  (Vivarium gives each the same tick-start state, P6). Each emits a binding/
  damage **intent**; the single `ChromosomeCommitStep` owner (DC-9) consumes the
  merged intents in a fixed canonical order, advances the one stream
  sequentially, commits, and writes back the bound-site deltas + advanced stream
  state. This reproduces Karr's single-owner sequential advancement
  (`Chromosome.randStream` advanced inside the one state object).

---

## 5. Participant enumeration (SLOT 3.3)

**Verified shared-stream participants (MATLAB draws on `Chromosome.randStream`
via the bind/sample/release family):**

| Process | MATLAB anchor | OC `chromosome` port today | Role |
|---|---|---|---|
| TranscriptionalRegulation | `TranscriptionalRegulation.m:376` → `Chromosome.m:493-494,500-502` | **No** (`karr_composite.py:1469-1474`) | write TF; **sole** shared-draw consumer (no process decision stream) |
| DNADamage | process order `DNADamage.m:537`; site selection `:559` → `Chromosome.m:2490+` (`setSiteDamaged`) | Yes `:2338` | **dual-stream**: process (reaction order) + shared (damage-site selection) |
| Transcription | `Transcription.m:505-506,807-808` (stochastic bind) | n/a (no store import today) | **dual-stream** (process region/pos + shared commit); write RNAP, read occupancy |
| DNASupercoiling | `DNASupercoiling.m:325-326,382-388,464-465` | Yes `:2308` | **dual-stream** (process + shared); bind gyrase/topoIV, release (release-rate draw), read |
| DNARepair | `DNARepair.m:963-1043,1344` | Yes `:2344` | shared commit; bind repair enzymes |
| Replication | `Replication.m:660,748-751,1265-1268` | Yes `:2302` | shared commit; bind/release pol/helicase/clamp, read |
| ReplicationInitiation | `ReplicationInitiation.m:410-412,464-465,596` | Yes `:2295` | shared commit; bind DnaA, read |
| ChromosomeCondensation | `ChromosomeCondensation.m:256-268` → `Chromosome.m:493-494,500-502` | Yes `:2317` | **dual-stream**: process (region/position) + shared (commit on every bind, DC-8) |

**Deferred / non-participants (no bound-site bind/sample/release call found):**
`FtsZPolymerization`, `ChromosomeSegregation` (reads copy structure, no
bind/sample/release). Cytokinesis reads `chromosome` but does not sample.

**Migration posture:** only **TxReg** migrates onto the shared stream in this
subsystem's first stages. DNADamage, Transcription, DNASupercoiling, DNARepair,
Replication, and RepInit are **enrolled in the contract** (so the stream + the
DC-9 owner are designed to compose) but their draw-routing migration is
sequenced later and is **not faked** — each moves only when its own iteration
runs. DNADamage and DNASupercoiling are the strongest second-consumer
candidates: both already have chromosome-stream ledger/replay infrastructure
(dec-006 named DNADamage and TxReg as the two discovery lanes;
`dnas_chromosome_release_ledger.py` exists for DNASupercoiling).

---

## 6. Deterministic intra-tick ordering contract (SLOT 4)

1. **Phases per tick (Karr `evolveState` → OC):** `request` → `allocation`
   (allocator grants) → `process phase` (each binder emits its intent, computed
   from tick-start state + its process-stream decisions) → `commit phase` (the
   DC-9 `ChromosomeCommitStep` owner consumes intents, draws from the shared
   stream, commits, writes back). Matches Karr allocate-then-evolve
   (`evolveState.m:56-72`; request/allocation already separate OC steps).
2. **Chromosome-draw order (commit phase):** a **fixed canonical order over the
   intents** inside the single owner — e.g. a frozen participant list derived
   from Karr's `processMetadata.evalOrder` (static), applied deterministically
   every tick. It is **not** the `flow` DAG over processes (which cannot
   serialize per-process in-place draws, P6), **not** Karr's per-tick `randperm`
   (deferred), and **not** read from the oracle.
3. **No oracle in the order choice (AO-4).** The order is a static constant;
   bit-identity to Karr's randomized interleaving is a **replay-only** property
   supplied by the dec-006 ledger.
4. **Single-consumer invariant (Stages B–D).** While TxReg is the sole migrated
   consumer there is exactly one intent per tick, so order is trivial and the
   owner Step is not yet required (TxReg self-draws, DC-9 exception). The owner +
   canonical order are introduced at the first multi-consumer stage (E), gated by
   a STOP test (§12).
5. **Accumulating-state faithfulness.** Because each intent is applied against
   the chromosome state the owner has already mutated for earlier intents this
   tick, a later binder sees earlier binders' footprints — matching Karr's
   sequential `copyToState` between processes. Processes cannot do this in their
   own `next_update` (tick-start state only, P6); the owner is what restores it.

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
   processes only. DNADamage is a concrete example of correct non-participation:
   its `initializeState` is empty (`DNADamage.m:465`), so it performs **no** t0
   chromosome draw and must not be warmed up.

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
- **AO-2 Fail-closed:** over-consumption raises (`RuntimeError`, probe §19 P2
  confirmed), under-consumption trips `assert_fully_consumed()`
  (`txreg_mcg_rand.py:333-380`).
- **AO-3 Ledger-binding:** a ledger bound to a different trace SHA or different
  `Chromosome.m`/`RandStream.m` source bytes fails closed (dec-006 §Decision #3).
  This includes the **`dnadamage_source_sha256`** cross-check: because DNADamage
  advances the shared stream (§5), a ledger's recorded draw sequence is only
  valid for the exact DNADamage source bytes it was reconstructed against, so a
  mismatch must fail closed (dec-006 integration addendum; the TxReg Iteration-0
  migration landed exactly this metadata).
- **AO-4 Order-not-from-oracle:** mutate the trace's recorded per-tick process
  order and assert the **production** draw order (the DC-9 owner's fixed
  canonical order) is unchanged (guards DC-5).

---

## 11. Migration stages (SLOT 9) & first slice

Stages sized for sequential test-writer → implementer → reviewer loops. Each
ends at a STOP gate (§12 tests).

- **Stage A — Substrate, behavior-neutral.** Add `ChromosomeStateRandStream`
  (DC-4, unify shims) + serialized stream state in the chromosome mapping +
  `ChromosomeStore.sample_accessible_regions`/`rand_state`. **No consumer wired.**
  Rollback = revert; no flag. Behavior-neutral (like the D5 pre/post pattern,
  `karr_composite.py:253-262`).
- **Stage B — TxReg sole consumer (part of the FIRST SLICE).** Add TxReg
  `chromosome` port; route the TxReg binding draw through
  `sample_accessible_regions` on the shared stream; TxReg self-draws in its own
  `next_update` and writes back the advanced stream state (DC-9 exception, valid
  for a single consumer). Keep projection reads. With TxReg the only consumer the
  draw **sequence is unchanged** vs the current per-process stand-in, so the
  single-seed replay baseline stays bit-identical.
- **Stage C — Shared writeback + authority removal.** Commit TF footprints to
  `monomer/complexBoundSites`; switch `tf_bound_promoters`/`bound_tfs` to store
  projections; delete the TxReg-local occupancy authority. Still single consumer.
- **Stage D — TxReg t0 pre-binding sweep** (§7) on the shared stream.
- **Stage E — Second consumer + the DC-9 commit owner (implementable spec).**
  This is where multi-consumer ordering lands. Concretely:
  1. Add `ChromosomeCommitStep(Step)` with ports `{chromosome, intents,
     substrates_allocated}`; it owns the serialized stream state and the
     `monomer/complexBoundSites` writeback.
  2. Add an `intents` store leaf (list/dict buffer, `set`-updater, cleared each
     tick by the owner) and give each participating process an `intents` output
     port. Each process's `next_update` emits
     `{"intents": {proc_key: {enzyme, positions, strands, weights, maxBindings}}}`
     computed from tick-start state + its process-stream decisions — it performs
     **no** shared-stream draw.
  3. Register the owner in `flow` with a dependency on every intent-emitting
     process so it runs in the step phase after they compute (Steps see merged
     state, P6).
  4. The owner iterates intents in the **fixed canonical order** (§6.2); per
     intent it calls `sample_accessible_regions` (shared-stream draw against the
     accumulating chromosome state) then `set_site_protein_bound`/`setSiteDamaged`,
     advancing the one stream; finally it writes the stream state + bound-site
     deltas back.
  5. Migrate TxReg from self-draw (Stage B) to intent-emit; add the second
     consumer (DNADamage or DNASupercoiling) as a second intent-emitter.
  STOP gate: deterministic two-consumer order over two seeds; each consumer's own
  draw count matches its isolated L2.1; no draw collision.
- **Deferred joint stage** — two-column fold-change (§9).

**Why the first slice is Stage A+B shipped together (not Stage A alone, not
big-bang):**
1. **Stage A alone is consumer-less infrastructure.** A landed stream class +
   serialization with no reader is exactly the "infrastructure cosplay" the
   operator's smallest-thing principle rejects — it adds a schema field and a
   module that nothing exercises end-to-end. So Stage A is **not** landed as a
   standalone slice; it ships with its first real consumer (B).
2. **A+B is still the smallest thing that delivers behavior:** one substrate +
   one real consumer (TxReg), nothing more. TxReg has no process decision stream,
   so the whole TxReg stochastic step maps 1:1 to the shared draw — no
   mixed-stream split, no owner Step yet (single consumer, DC-9 exception).
3. **Draw sequence is preserved** for a TxReg-only run ⇒ the existing dec-006
   L2.1 replay is a ready bit-identity falsification test, not a rewrite.
4. **Independent STOP gates within the one slice.** Gate A (stream round-trip +
   shim-equivalence unit tests) and Gate B (TxReg L2.1 replay bit-identity +
   `INTEGRITY_OK 5/28`) are separately runnable and separately attributable even
   though shipped in one slice, satisfying "each STOP gate independent."
5. **The hardest, lowest-value pieces are deferred** — the DC-9 owner (Stage E),
   two-column fold-change, and the `randperm` scheduler are all out of the first
   slice.
A big-bang migration (all 7 binders + the owner + two-column + t0 at once) would
entangle untestable multi-consumer ordering with the testable single-consumer
refactor and has no intermediate green gate.

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
| E | commit owner serializes draws | two-consumer run: each consumer's draw count == its isolated L2.1 count; no collision | let two processes self-draw the stream in `next_update` ⇒ identical (colliding) draws, count mismatch (proves P6 hazard) |
| E | multi-consumer order deterministic & not-from-oracle | two-seed, two-consumer owner order stable | shuffle the canonical intent order ⇒ draw sequence change; mutate trace process order ⇒ production unchanged (AO-4) |
| E | DNADamage dual-stream routed correctly | DNADamage reaction order on its process stream; damage-site draws on shared stream via owner | route DNADamage damage-site draw to its process stream ⇒ shared-stream draw count wrong vs ledger |
| E | ledger DNADamage-hash bound | AO-3 with `dnadamage_source_sha256` | swap DNADamage source bytes ⇒ ledger load fails closed |

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
  (both mappings); serialize stream state in chromosome `initial_state` (B); at
  Stage E add the `ChromosomeCommitStep` to `steps`/`flow`, the `intents` store
  leaf, and `intents` output ports on participating processes.
- NEW `opencell/vivarium/chromosome_commit_step.py` — the DC-9 sequential commit
  owner (Stage E).
- MODIFY (Stage E, each when its iteration runs) the second consumer's module —
  **DNADamage** (`karr_dna_damage.py`) or DNASupercoiling (`karr_dna_supercoiling.py`):
  emit intents instead of self-drawing; keep the process-stream decision draw
  (DNADamage reaction order, `DNADamage.m:537`).
- TEST (separate authors) — Stage A/B/C/D suites + Stage-E owner/second-consumer
  suite + anti-oracle tests (§10).
- DEC (at implementation time, not here) — author **dec-007** referencing
  dec-006: dec-006 governs the *test* ledger oracle and stays in force; dec-007
  adds the *production* single shared stream + the DC-9 commit owner (the gap
  dec-006 left — "production code paths are unaffected"). dec-007 does **not**
  supersede dec-006; it is additive and compatible.

**Schema/topology changes:**
- Topology: `+1` port (`chromosome`) on TxReg (both composite mappings) at
  Stage B; at Stage E, `+1` `intents` output port per participating process and a
  new `ChromosomeCommitStep` in `steps`/`flow`.
- Chromosome state mapping: `+1` reserved scalar (`_shared_rand_stream_state`).
  Back-compat: **absent ⇒ freshly seeded stream** (existing traces unaffected;
  no re-extraction required to load). Stage E: `+1` `intents` store leaf
  (transient per-tick buffer, not persisted across ticks).

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
- CC **is a genuine shared-commit consumer** (CORRECTED): every real SMC bind
  advances the shared chromosome stream via `setSiteProteinBound →
  sampleAccessibleRegions` with empty weights normalized to ones
  (`Chromosome.m:493-494,500-502`); the only zero-draw case is `maxBindings==0`
  (`ChromosomeProcessAspect.m:294-303`). So CC occupies a **non-trivial** slot in
  the DC-9 owner's canonical order and draw-accounting when it later composes —
  it is not a zero-draw placeholder.
- **CC Iteration 2 proceeds independently.** Its same-tick
  request→allocation→consume repair (plan "Next iterative round" item 1) concerns
  allocation timing, not the shared RNG stream; it neither needs nor edits the
  shared stream, and the two iterations do not edit the same shared chromosome
  production surface concurrently.

---

## 15. Recommended first implementation slice

**Stage A+B shipped as one slice** (substrate + its first real consumer),
**not** Stage A alone. Ship the unified `ChromosomeStateRandStream`, the
serialized stream state, and the store API **together with** wiring **TxReg as
the sole consumer** via the `chromosome` port — stopping *before* footprint-
authority removal (Stage C) and before the DC-9 owner (Stage E). Rationale: §11
"first slice" points 1–5 — Stage A alone is consumer-less infrastructure
(operator anti-pattern), while A+B is the smallest end-to-end-testable unit.
**Two independent STOP gates** within the slice: Gate A = stream round-trip +
shim-equivalence unit tests; Gate B = dec-006 L2.1 single-seed replay staying
bit-identical plus `INTEGRITY_OK 5/28` and L1b/baseline regressions green.

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
2. **Canonical commit order source.** The DC-9 owner's fixed order should derive
   from Karr's static `processMetadata.evalOrder` (not `randperm`, not oracle);
   confirm that ordering is available in OC metadata and define the frozen list
   before Stage E. For t0, the sweep order for migrated processes should match
   Karr `processesInInitOrder`.
3. **dec-007 vs dec-006 boundary wording.** Exact phrasing that dec-006's
   test-only oracle stays in force while dec-007 governs production + the DC-9
   owner — author at implementation time; do not edit decision cards in this
   planner pass.
4. **`sample_accessible_regions` scope on the store.** How much of MATLAB's
   `isRegionAccessible`/`getReleasableProteins` accessibility logic
   (`Chromosome.m:651-752`) already lives in TxReg vs must move to the store to
   keep the draw count identical — verify draw-count parity under the ledger
   before Stage C.
5. **Second-consumer selection** (Stage E): **DNADamage** vs DNASupercoiling —
   both have existing chromosome-stream ledger/replay infrastructure (dec-006
   named DNADamage; `dnas_chromosome_release_ledger.py` exists for
   DNASupercoiling). Pick by which has a ready multi-consumer draw-order fixture/
   trace; DNADamage is favored because dec-006 already froze its source-hash
   binding.
6. **Intent-buffer cleanup semantics.** Confirm the owner can authoritatively
   clear the per-tick `intents` leaf (set-updater to empty) and that no process
   reads stale intents — a Vivarium updater-ordering check before Stage E.

---

## 18. Acceptance matrix

| # | Requirement | Acceptance criterion | Stage |
|---|---|---|---|
| A1 | Single state authority | no new authoritative bound-site store; TxReg reads/writes `ChromosomeStore` | C |
| A2 | Single serialized shared RNG stream | one `ChromosomeStateRandStream`; state in chromosome mapping; checkpoint round-trip bit-identical | A |
| A3 | MIXED model exact | process decision draws unchanged; only accessibility/commit/release advance shared stream | B |
| A4 | Participants enumerated | §5 table with MATLAB file:line; verified vs deferred distinguished | (doc) |
| A5 | Deterministic order, no oracle | production draw order = DC-9 owner's fixed canonical order (Karr `evalOrder`-derived); AO-4 passes | B(single)/E(multi) |
| A6 | Unified t0 sweep | TxReg t0 pre-binding sweep; replay baseline bit-identical; no faked processes (DNADamage empty-init not warmed) | D |
| A7 | TxReg topology migrated | `chromosome` port present; writeback live; dual authority removed | B/C |
| A8 | Two-column fold-change deferred | column-0 emission retained; prerequisites §9 listed | — |
| A9 | Replay is test-only | AO-1/AO-2/AO-3 (incl. `dnadamage_source_sha256`) pass; no ledger in production path | B+ |
| A10 | Small sequential slices | each stage has an independent STOP gate (first slice = two gates) | all |
| A11 | Falsifiable tests + mutations | §12 table; each planted mutation fails its test | per stage |
| A12 | Evidence impact stated | L2.1 preserved; L2.2 blocked-on-data; L2.4 `INTEGRITY_OK 5/28` held | per stage |
| A13 | Blast radius/schema/rollback | §13; back-compat absent-key default; no permanent flag | all |
| A14 | CC reconciled | CC decision RNG local; CC is a genuine shared-commit consumer (not zero-draw); CC Iter 2 independent | (doc) |
| A15 | Multi-consumer correctness | DC-9 owner serializes shared draws (processes emit intents, do not self-draw past one consumer); P6-proven | E |

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
- **Probe P4 (CC/empty-weights draw semantics — Blocker 1).** Read
  `ChromosomeProcessAspect.m:286-345` (`:294-303` zero-draw iff `maxBindings==0`;
  `:308-310` empty weights→ones; `:342` `setSiteProteinBound`),
  `Chromosome.m:493-494` (ones normalization), `:500-502` (`randsample` on
  `this.randStream`), `:2043` (`setSiteProteinBound` always calls
  `sampleAccessibleRegions`). Conclusion: a real CC bind advances the shared
  stream; the "zero-draw" claim was false. Corrects DC-8/§5/§14.
- **Probe P5 (DNADamage dual-stream — Blocker 2).** `DNADamage.m:537`
  (`randStream.randperm` = process stream, reaction order), `:559`
  (`chromosome.setSiteDamaged` → `Chromosome.m:2490+` draws on chromosome
  `randStream` via `sampleAccessibleSites`/`stochasticRound`/
  `randomlySelectNRows`), `:465` (empty `initializeState`). Adds DNADamage as a
  verified participant with no t0 sweep.
- **Probe P6 (Vivarium Engine update visibility — Blocker 3, runtime).** Two
  ordinary `Process`es share a store leaf `x`; a `Writer` returns `{x:+1}`, a
  `Reader` records what it sees. Result: `process_reader_saw=[('process_reader',
  0)]` (Reader did **not** observe Writer's within-tick update), while a `Step`
  saw the merged value `[('step_reader',0),('step_reader',1)]` and `final_x=1`.
  Confirms ordinary Processes compute from tick-start state (`engine.py run_for`
  buffers updates in `self.front`, applies via `_send_updates` after all compute)
  and Steps see merged state — so a shared in-place RNG stream cannot serialize
  draws across processes; the DC-9 commit owner is required. Drives the DC-5/DC-9
  redesign.
- **Self-audit:** see §20 for the blocker→correction map.
- **Canonical replay baseline referenced:** trace `645a2e68…`, ledger
  `ac2426dc…`, draw digest `88c7c28c…`, 135 active ticks / 378 draws (plan
  operational-handoff, 2026-10-13).

---

## 20. Self-audit — review blockers → corrections

| Blocker (review) | Finding (source/probe) | Corrected sections |
|---|---|---|
| **1. CC "zero-draw" commit claim wrong** | `bindProteinToChromosome` zero-draws **only if `maxBindings==0`** (`ChromosomeProcessAspect.m:294-303`); empty weights→ones (`:308-310`, `Chromosome.m:493-494`); `setSiteProteinBound:2043` always calls `sampleAccessibleRegions` whose `randStream.randsample` (`Chromosome.m:500-502`) advances the shared stream. CC draws from **both** streams. Probe P4. | §1.1 table (new rows); DC-8 (rewritten); §5 table (CC row); §6.5; §14; A14; P4 |
| **2. DNADamage missing as participant** | `DNADamage.m:537` process-stream reaction order; `:559` `setSiteDamaged` → `Chromosome.m:2490+` chromosome-stream draws; `:465` empty `initializeState`. Ledger must bind `dnadamage_source_sha256` (dec-006 addendum) because DNADamage advances the shared stream. Probe P5. | §1.1 table (2 new rows); §5 table (DNADamage row) + posture; §6; §7 step 4; §10 AO-3; §11 Stage E; §12 (2 rows); §13; §17 Q5; P5 |
| **3. Engine serializes process draws? NO** | Ordinary Processes compute from the same tick-start store view (`engine.py run_for` buffers `self.front`, applies via `_send_updates` after all compute); Steps see merged state. Probe P6. Shared in-place stream cannot serialize cross-process draws ⇒ single sequential commit **owner (Step)** receiving intents. | DC-5 (rewritten); DC-9 (new); §4.5 (rewritten); §6 (rewritten); §11 Stage E (implementable spec) + Stage B exception; §12 (owner rows); §13 (owner file/ports); A5/A15; P6 |
| **First-slice reconsideration** | Stage A alone = consumer-less infrastructure (operator anti-pattern); A+B is the smallest end-to-end-testable unit with two independent STOP gates. | §11 "first slice" (rewritten); §15 (rewritten) |
