# The OpenCell L-Ladder — Canonical Definitions

**What this is.** The single normative definition of every OpenCell validation
rung, the vocabulary used to describe per-process evidence, the terminal
states a gate may report, and the ordering rules between rungs.

**Authority.** Where this note and any other document disagree *about what a
rung means*, this note wins. Per-process sampling parameters, channel
definitions and scope flags remain owned by
`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`; per-gate methodology
remains owned by that gate's own design doc (indexed in §8). This note does
not restate, and never overrides, either.

**Read §7 before quoting anything from here as status.** This file is
deliberately status-free.

---

## 0. The denominator: 28 processes

OpenCell ports **28 Karr processes**. That is the process denominator, always,
in every claim about coverage, completeness or progress.

Two smaller numbers appear constantly in the evidence tree and must never be
mistaken for the denominator:

- **22** — processes flagged `in_scope_L2_2: true`, i.e. those with a
  stochastic surface worth a *distributional* gate at all
  (`docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md` §3). The remaining
  processes are `DETERMINISTIC`-bucket and are out of L2.2 scope by design,
  not by omission.
- **18** — of those 22, the rows routed to the Design-A per-tick harness
  (`harness_type: design_a_per_tick`). The other 4 route to
  `harness_type: event_class`.

**18 is a validation-profile subset. It is never a process denominator.**
A statement of the form "18/28 green" is a category error: it compares a
per-tick-harness row count against the whole process roster, and silently
reports the 10 processes that Design-A per-tick was never the right
instrument for as if they had failed it. The correct forms are "n of 18
Design-A per-tick rows", "n of 22 L2.2 in-scope processes", or "n of 28
processes at rung X".

The same discipline applies to every profile: `event_class`,
windowed/continuous, optimization/FVA, stress and condition-gated evidence
each have their own applicable subset, and each subset's size is a property
of the instrument, not of the port.

---

## 1. The ladder

Rungs are ordered by **diagnostic dependency**: each rung's verdict is
interpretable only if the rungs it depends on hold. This is not the order in
which the rungs were invented, nor an order of structural complexity.

| Rung | Question | Integration scope |
|---|---|---|
| **L1a** | Does the process fire at all? | 1 process, runtime |
| **L1b** | Does the wiring record match the code? | 1 process, static |
| **L2.0** | Do the declared channels match the oracle's? | 1 process, static |
| **L2.0a** | Does the allocator hand each process the right inputs? | 28 processes, 1 tick |
| **L2.1** | Same seed, same trace — does replay reproduce it? | 1 process, 1 trace |
| **L2.2** | Across seeds — is the *distribution* right? | 1 process, ensemble |
| **L2.4** | Run free: is the chassis self-consistent? | 28 processes, ≤100 ticks |
| **L2.5** | Do processes compose through the shared pool? | k∈[2,4] processes |
| **L3** | Do processes compose through direct hand-off? | 2 processes, N ticks |
| **L4** | Does a biological cluster match a Karr submodel? | process cluster |
| **L5** | Does the whole cell reproduce phenotype? | 28 processes, full cycle |

### Oracle use

| Rung | Karr oracle at process outputs? | Where the oracle sits |
|---|---|---|
| L1a | no | — (self-evidence only) |
| L1b | no | Karr source/method inventory, statically |
| L2.0 | no | channel *names* only |
| L2.0a | no | the allocation boundary (pool + requests → allocation) |
| L2.1 | **yes** | per-process trace, input and output |
| L2.2 | **yes** | per-process trace ensemble, distributional |
| L2.4 | no | internal conservation identity |
| L2.5 | **yes** | per-process traces of each composed participant |
| L3 | **yes** | joint 2-process trace |
| L4 | **yes** | Karr submodel oracle |
| L5 | **yes** | published phenotype scorecard |

L1a, L1b, L2.0, L2.0a and L2.4 deliberately run **without** a Karr oracle at
process outputs. They are *structural* gates: they can prove a port is
internally incoherent, but never that it is biologically right. Any claim of
Karr fidelity must cite L2.1 or higher.

### Entry and exit

| Rung | May be evaluated when | Green means |
|---|---|---|
| L1a | always | the process executes and mutates state |
| L1b | always | every wiring-row assertion resolves to real code |
| L2.0 | L1b holds | declared channels are the oracle's channels |
| L2.0a | L2.0 holds | allocator arithmetic equals Karr's, per (process, WID) |
| L2.1 | L2.0a holds | replay matches the trace under the process's oracle type |
| L2.2 | L2.1 holds for the process | distributional distance is within a pre-registered threshold |
| L2.4 | L1b holds for all 28 | `Δpool == Σ(produced − consumed)`, integer-exact, per WID |
| L2.5 | L2.4 holds; L2.2 holds per stochastic participant | each participant matches its own trace *while composed* |
| L3 | L2.5 holds for the pair | the direct hand-off reproduces the joint trace |
| L4 | L3 holds within the cluster | the cluster matches its Karr submodel |
| L5 | L4 holds | phenotype scorecard threshold met across a seed ensemble |

"Green means" is a statement about the *property proven*, not about a command
exiting 0. A gate that exits 0 without having exercised the property is not
green; it is broken (see §6).

### Per-rung notes

**L1a — aliveness.** The weakest rung: the process runs and writes something.
No standing gate script exists in-tree; L1a is the baseline the L1b design
doc contrasts itself against (`docs/phase_f/L1B_WIRING_CONFORMANT_GATE.md`).

**L1b — wiring conformance.** Two halves, both required: (A) method
completeness — every Karr runtime-required method has an implemented,
anchored OpenCell counterpart; (B) wiring-row conformance — exhaustive, not
exemplar, per-process integration semantics.
Gates: `scripts/l1b_method_completeness.py`, `scripts/l1b_verify_wiring.py`.

**L2.0 — schema.** Static channel-name comparison between `ports_schema` and
the Karr observable set. Deliberately narrow: it proves names, never values.
Gate: `scripts/probe_l2_0_schema_audit.py`.

**L2.0a — allocator input arithmetic.** Given Karr's pre-tick pool and the
per-process requirements, does `KarrAllocationStep` produce Karr's per-process
input state? Without it, any residual L2.1/L2.2 divergence that is not
process-local math is ambiguous between an allocator bug, compartment
routing, and a state-update off-by-one.
Design: `docs/phase_f/L2_0A_ALLOCATOR_INPUT_GATE.md`.
Probe: `scripts/probe_l2_0a_allocator_input.py`.

**L2.1 — deterministic / same-seed replay evidence.** Per-process replay
against a single Karr trace at a fixed seed. The rubric is **oracle-type
aware**: `bit_identity` for deterministic processes, and for stochastic
processes a biology-firing check rather than per-tick bit equality, because
per-tick RNG variance is legitimate there. L2.1 catches wiring-class bugs
(dropped update, swapped index, missing term). It cannot catch a wrong rate
constant that happens to land on the trace.
Rubric: `tests/vivarium/test_l2_1_strict_rubric.py`,
`docs/phase_f/L2_1_STRICT_RUBRIC_BASELINE.md`.

**L2.2 — stochastic / distributional evidence.** Across independent
(seed, tick) samples, does the OpenCell process produce outputs whose
*distribution* matches Karr's? Catches rate-constant errors, wrong
distribution shape, and ordering effects that pass L2.1 by coincidence.
Spec: `docs/phase_f/l2_2_design_a/L2_2_DESIGN_A_SPEC.md`.
Scope and sampling: `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`.

**L2.4 — autonomous chassis conservation.** All 28 processes run free — no
trace injection, no oracle at outputs — and every substrate WID must satisfy
`Δpool == Σ_p (produced − consumed)` exactly, with a fail-closed write-surface
audit and documented open-boundary exclusions. This is the rung that proves
the allocator and shared-pool projection are wiring-correct.
Design: `docs/phase_f/L2_4_CHASSIS_CONSERVATION_GATE.md`.
Gate: `scripts/l2_4_verify_conservation.py`.

**L2.5 — allocator-mediated shared-pool composition.** k∈[2,4] processes run
together on the shared `substrates` store with `KarrAllocationStep` mediating,
each validated against its own per-process trace. Failures are classified by
the `CAUSE_1..CAUSE_7` taxonomy (WID-set mismatch, oracle-injection
misalignment, composition-order error, upstream state pollution, intrinsic
replay divergence, harness bug, oracle-trace defect). Strictness levels
L2.5.0 smoke / L2.5.1 hint-equivalent / **L2.5.2 honest (no `trace_hint`)** /
L2.5.3 owner-manifest-validated; **L2.5.2 is the level that counts**.
Design: `docs/phase_f/L2_5_HARNESS_DESIGN.md` (filename predates the rename).
Plan: `docs/phase_f/L2_5_PLAN.md`.
Rubric: `docs/phase_f/L2_5_ACCEPTANCE_RUBRIC.md`.

**L3 — direct coupling.** A producer→consumer pair joined by a **direct port
hand-off**, bypassing the shared pool and the allocator entirely. L3 and L2.5
are peers testing different mechanisms, not the same test at different sizes
(see §5). No L3 design doc exists in-tree yet; `docs/phase_f/L2_5_PLAN.md`
forward-references an `L3_PCV_FRAMEWORK.md` that has not been written.

**L4 — submodel / cluster.** A natural biological cluster (central dogma,
metabolism, DNA dynamics, cell division) reproduces a Karr submodel-level
oracle.

**L5 — whole-cell phenotype.** The full chassis, ensemble across seeds, over a
full cell cycle, scored against the published phenotype scorecard.

---

## 2. L2.P — per-process fidelity disposition

**Status: non-operative explanatory umbrella. Not canonical terminology.**

"L2.P" names a *concept*, not a rung, not a gate, and not a verdict. It refers
to the aggregate question:

> For process *P*, what is the total fidelity evidence we hold, across every
> modality that applies to *P*?

The concept exists because the ladder's L2 family is not a checklist that
every process walks end to end. Below L2.4 the L2 rungs are **evidence
modalities selected by profile and applicability**:

| Modality | Applies to | Selected by |
|---|---|---|
| L2.1 replay | all 28 | oracle type (`bit_identity` / `distributional`) |
| L2.2 Design-A per-tick | the 18 per-tick rows | `harness_type: design_a_per_tick` |
| L2.event | the 4 event-class rows | `harness_type: event_class` |
| optimization / FVA | Metabolism | `fva_feasibility` aggregation |
| windowed / continuous | continuous-kinetics processes | per-process profile spec |
| stress / condition-gated | processes with a quiescent natural regime | pre-registered condition |

A process is not "behind" because it has no Design-A per-tick row, and a
process is not "ahead" because it has one. The modality is chosen by what the
process *is*; the disposition is the union of whatever applies.

**Rules for the term.**

1. L2.P **must not** appear in `PROCESS_CATALOG.yaml`, `event_registry.yaml`,
   `evidence_index.json`, any verdict string, any gate name, any test id, or
   any CI job name. It has no machine meaning and adding one would require
   renaming artifacts for zero gain in rigour.
2. L2.P **may** be used in prose to say "the per-process fidelity disposition
   of X", where enumerating the modalities would be tedious.
3. L2.P is **not** a rung and confers **no** ordering. It never appears in a
   dependency argument. Ordering statements cite the concrete rungs (§4).
4. Nothing is "at L2.P". Things are at L2.1, or have L2.2 evidence, or hold a
   condition-gated candidate artifact — those are the statements that carry
   authority.

This is the least disruptive accurate formulation: it gives the missing word
for the aggregate idea without inventing a rung nobody can gate on.

---

## 3. Applicability and terminal states

Every evidence row terminates in exactly one of the classes below. **Green is
a narrow class**; most terminal states are honest, permanent, and *not* green.

| Class | Green? |
|---|---|
| **PASS / VALIDATED** | **yes** |
| **FAIL** | no |
| **INSUFFICIENT_EVIDENCE** | no |
| **CONDITION_GATED / OBSERVED_REGIME** | no |
| **NOT_APPLICABLE / DEFERRED** | no |

Concrete tokens in-tree, by class:

- **PASS / VALIDATED** — `PASS`; channel `PASS` or `SEED_NOISE`; L2.1
  `GENUINE`; `H12_CONFIRMED`.
- **FAIL** — `FAIL`, `SCHEMA_INVALID`, `STALE_VS_TREE`, `SENTINEL_FAIL`,
  `NM_MISMATCH`, `PROCESS_NAME_MISMATCH`.
- **INSUFFICIENT_EVIDENCE** — `MISSING_EVIDENCE`, `INSUFFICIENT_SAMPLES`,
  `PRIMARY_INSUFFICIENT_SAMPLES`, `NO_GATEABLE_CHANNELS`,
  `MISSING_EVALUATOR`, `PRIMARY_CHANNEL_VACUOUS`, `PRIMARY_ACTIVITY_MISSING`.
- **CONDITION_GATED / OBSERVED_REGIME** — `H12_OBSERVED_REGIME`,
  `CONDITION_GATED_CANDIDATE`.
- **NOT_APPLICABLE / DEFERRED** — `in_scope_L2_2: false`,
  `in_scope_v4: false`, `EVENT_CHANNEL_DEFERRED`,
  `analytical_check.applicable: false`, `DEFERRED`, N/A gate cells.

Three distinctions matter more than the token names:

**Green vs terminal-but-non-green.** `FAIL` says the port is wrong.
`INSUFFICIENT_EVIDENCE` says we do not know. `NOT_APPLICABLE` says the
question is malformed for this process. `CONDITION_GATED`/`OBSERVED_REGIME`
says the branch was not observed in the accepted natural population and any
conditioned evidence remains non-gating; reachability may be structurally
excluded or explicitly `UNRESOLVED`. All four are honest reports, and the last
three are legitimate resting states. None of them is green, and none may be counted toward a green tally, aggregated into a
percentage alongside green rows, or reported as "effectively green".

**A permanently non-green state is not a bug.** Some branches can never reach
`H12_CONFIRMED` for a documented structural reason — a genuine Monte Carlo
competition with no closed form, a stimulus that is zero in every calibrated
Karr condition. The correct response is a hash-bound, non-gating conditional
artifact plus an honestly recorded reachability status, never a relaxed
threshold.

**No condition-gated proposal silently unblocks anything.** A
`CONDITION_GATED_CANDIDATE`-class artifact is *candidate* evidence: it is
non-gating by construction, it does not change the process's verdict, it does
not satisfy an L2.2 channel, and it does not confer L2.5 or L3 entry. Only an
explicitly enacted taxonomy change — reviewed, implemented in
`scripts/l22_evidence/`, and reflected in the evidence index — can change what
a verdict means. Note the current split: `CONDITION_GATED_CANDIDATE` is an
implemented *candidate-artifact* classification
(`scripts/l22_evidence/h12_condition_gated.py`), whereas the enacted
`H12_CONDITION_GATED` verdict value remains a **proposal**
(`docs/phase_f/l2_2_design_a/h12/CONDITION_GATED_TAXONOMY_PROPOSAL.md`).
Likewise, the FtsZ windowed and DNADamage stress profiles are pre-registered,
non-gating and unapplied; their proposed catalog/registry patches sit in
`proposed_patches/` precisely so that a proposal cannot become a verdict by
proximity.

---

## 4. Ordering and why it is what it is

**L1b before L2.4.** L2.4 attributes conservation drift to processes. If a
wiring row lies about what its code does, L2.4 misattributes.

**L2.4 before L2.5.** L2.5 exercises the allocator and the shared-pool
projection. If those are not conservation-proven, an L2.5 failure cannot be
told apart from an allocator bug — this is not hypothetical: composition
failures were mis-attributed for weeks under the earlier ordering, which is
why the rung now sits before L2.5 rather than after it.

**L2.2 before L2.5, for stochastic participants.** L2.5 can absorb
stochastic divergence through L2.1's calibrated tolerances. Composing
processes whose distributions were never gated means L2.5 rides on those
tolerances and can pass while the biology is wrong.

**L2.5 before L3 entry certification.** L2.5 tests the wiring the chassis
actually uses. If shared-pool composition is broken, a green L3 is
irrelevant to the chassis.

**L2.5 and L3 are peers, not sizes of the same test.** They differ in
*mechanism*:

- **L2.5, allocator-mediated composition** — participants never touch each
  other. They read and write a shared `substrates` store; `KarrAllocationStep`
  partitions the pool between them. What is under test is contention,
  allocation arithmetic, write-conflict resolution, composition order and
  shared WID-space alignment.
- **L3, direct hand-off** — a producer writes a port that a consumer reads
  directly, with no pool and no allocator in the path. What is under test is
  the biological hand-off itself: state-object transfer, units, and timing
  between the pair.

A pair can pass one and fail the other. Both must hold before L4 or L5 means
anything.

---

## 5. Evidence authority rules

These are gate-independent. They apply to every rung.

1. **Live mechanical re-derivation.** A verdict is whatever re-deriving it
   from raw numbers *right now* produces. Stored verdict strings inside
   `result.json` are never trusted; every channel verdict is recomputed from
   raw fields by `scripts/l22_evidence/verdict.py`.
2. **No stored-verdict authority.** A test asserting that a hand-maintained
   verdict table equals another hand-maintained verdict table is not evidence.
   Hand-written verdict pins, status documents, tracker tables and model
   confidence are all non-authoritative, always.
3. **Raw portable artifacts.** Evidence must be verifiable from a fresh clone.
   The live evidence root is gitignored; the tracked portable mirror is
   `docs/phase_f/l2_2_design_a/evidence_bundle/`, carrying the mandatory
   authority files and sidecars byte-for-byte — the sole exception being
   `input_manifest.json`, whose input paths are normalized to repo-relative
   POSIX form while its gated content is preserved exactly.
4. **Source and input hashes are the gating link.** Every recorded input
   sha256 is re-compared against the file's current on-disk sha256; drift is
   `STALE_VS_TREE`, naming the path. **Content hashes, not git plumbing, are
   authority** — git SHA and dirty flags are recorded and surfaced for humans
   but are not part of pass/fail logic. Hashing a file no verdict ever reads
   is authority theater and is not done.
5. **No zero == zero pass.** A gate must refuse rather than pass on absent
   activity: vacuous primary channels, missing activity, zero comparison pairs
   and empty event support are all non-green. A harness must refuse processes
   its instrument is wrong for, rather than emit a zero-distance pass — this
   is exactly why event-class rows are routed away from the per-tick harness
   and reported as missing evidence instead of passing it.
6. **No trace-hint or oracle-after laundering.** Where an implementation reads
   the oracle's own post-state (`trace_hint`, `states_after`) and emits it, the
   comparison is circular. Exact agreement with the oracle on a primary channel
   is treated as laundering by default and demotes the row; it may only be
   re-admitted by independent, hash-bound structural evidence that the
   agreement is genuine algorithmic convergence. The honest level of a
   composition test is the one that runs with no hints at all (L2.5.2).
7. **Source-selection hierarchy.** For any fidelity question, the source order
   is: (1) the Karr MATLAB source, (2) the fixture data, (3) the published
   paper, (4) the supplementary methods, (5) our own derived summaries.
   Never design or extract from a derived summary when a more primary source
   is on disk; inventory local and worktree-local artifacts before extracting
   anything new. Full rule: `.github/copilot-instructions.md`
   ("Primary-Source Discipline").

---

## 6. Deprecated vocabulary — crosswalk

Historical documents, blog posts, checkpoints and prior decision entries keep
their original wording as a record and are **not** to be retro-edited. Use
this table to read them.

| Deprecated / historical | Current | Note |
|---|---|---|
| `L1` (single "Implemented" rung) | `L1a` + `L1b` | split 2026-07-01 |
| `L1c` | `L2.4` | renamed, moved before L2.5, 2026-07-02 |
| `L2.2.k`, "L2.2 composition" | `L2.5` | renamed 2026-06-04 |
| `L2` (single "Isolated fidelity") | `L2.0`/`L2.0a`/`L2.1`/`L2.2` | conflated four questions |
| "event class" as a bucket | `harness_type: event_class` | routing flag for 4 rows |
| L2.2 `VERIFIED_GENUINE` | re-derived `PASS` in the index | old dicts were circular |
| L2.1 `PARTIAL`/`UNINFORMATIVE`/`COINCIDENTAL` | still emitted | non-green, not `GENUINE` |
| "the L2.2 harness" | Design-A per-tick *or* L2.event | name the harness |
| "18/28 green", "22/28 green" | see §0 | profile scope ≠ denominator |
| `L2_2_HARNESS_DESIGN.md`, `L2_2_D1_UNION_MASTER_LIST.md` | **L2.5** docs | filenames predate the rename |
| `L3_PCV_FRAMEWORK.md` | does not exist | L3 has no design doc yet |

Two shapes of error this table exists to stop: quoting a rung label from a
document written before its rename, and quoting a profile-scoped count as if
it were coverage of the port.

---

## 7. What this file does not contain

No current pass counts. No per-process verdicts. No dates, branch names,
commit SHAs or "as of" claims. No roadmap, sequencing plan or next actions.
No statement about which gates are built, running, paused or blocked.

Those are properties of a moment, and this file must survive moments. For
current state, read the artifact that owns it:

- Dated reconciled checkpoint — `docs/phase_f/CHECKPOINT_2026-08-03.md`
- Mechanically re-derived L2.2 evidence status —
  `docs/phase_f/l2_2_design_a/evidence_index.json` (re-derive before trusting;
  see §5 rule 1)
- H12 side-index — `docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json`
- L2.event adapter status — `docs/phase_f/l2_event/event_registry.yaml`
- Operational state and open work — `plan.md`
- Ratified project decisions — the PM-OS decisions log (`.pm-os/DECISIONS.md`,
  outside this repository)

The older L2.2, L2.5 and 29-row trackers are historical inputs until a dated
checkpoint explicitly reconciles them; they are not current authority merely
because their filenames say "tracker" or "status".

If a status claim cannot be traced to one of those, it is not a status claim.

---

## 8. Canonical file index

All paths are repo-relative.

**Ladder and scope**
- `docs/phase_f/L_LADDER_CANONICAL.md` — this file
- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` — scope, buckets,
  `harness_type`, sampling parameters, per-process channels
- `docs/phase_f/L2_2_STOCHASTIC_AUDIT.md` — original bucket classification

**Gate designs**
- `docs/phase_f/L1B_WIRING_CONFORMANT_GATE.md` — L1b
- `docs/phase_f/L2_0A_ALLOCATOR_INPUT_GATE.md` — L2.0a
- `docs/phase_f/L2_4_CHASSIS_CONSERVATION_GATE.md` — L2.4
- `docs/phase_f/l2_2_design_a/L2_2_DESIGN_A_SPEC.md` — L2.2 Design-A
- `docs/phase_f/L2_EVENT_GATE_SPEC_v4.md` — L2.event
- `docs/phase_f/L2_5_HARNESS_DESIGN.md`, `docs/phase_f/L2_5_PLAN.md`,
  `docs/phase_f/L2_5_ACCEPTANCE_RUBRIC.md`,
  `docs/phase_f/L2_5_PAIR_MATRIX.md` — L2.5
- `docs/phase_f/L2_2_METRIC_BY_PROCESS_CHARACTER_DESIGN.md` — metric families
- `docs/phase_f/L2_2_METABOLISM_LP_DEGENERATE_DESIGN_V4.md` — Metabolism MF4

**Evidence authority**
- `docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md` — evidence schema,
  re-derivation, staleness, portable bundle, sentinels
- `docs/phase_f/l2_2_design_a/LAUNDERING_VS_CONVERGENCE.md` — laundering vs
  genuine deterministic convergence
- `docs/phase_f/L2_5_HONEST_MODE_HINT_LEAKAGE_FINDING.md` — what trace-hint
  short-circuits hid
- `docs/phase_f/l2_2_design_a/h12/H12_REPORT.md` — H12 closed-form-dominance
  evidence
- `.github/copilot-instructions.md` — primary-source discipline, RNG
  discipline, provenance logging

**Profiles and proposals (non-gating until enacted)**
- `docs/phase_f/l2_2_design_a/h12/CONDITION_GATED_TAXONOMY_PROPOSAL.md`
- `docs/phase_f/l2_2_design_a/stress/DNADAMAGE_STRESS_PROFILE_PROPOSAL.md`
- `docs/phase_f/l2_windowed/FTSZ_WINDOWED_PROFILE_SPEC.md` and
  `docs/phase_f/l2_windowed/proposed_patches/`
- `docs/phase_f/l2_event/proposed_patches/`

**Executable gates and harnesses**
- `scripts/l1b_method_completeness.py`, `scripts/l1b_verify_wiring.py`
- `scripts/probe_l2_0_schema_audit.py`,
  `scripts/probe_l2_0a_allocator_input.py`
- `tests/vivarium/test_l2_1_strict_rubric.py`,
  `tests/vivarium/l2_replay_common.py`
- `tests/vivarium/l2_2_design_a_runner.py`, `scripts/l22_evidence/`
- `scripts/l2_4_verify_conservation.py`
- `tests/vivarium/l2_2_replay_common_v2.py` (L2.5 composition harness)
- `scripts/l2_event/registry.py`
- `opencell/vivarium/karr_composite.py`,
  `opencell/vivarium/karr_allocation_step.py`
