# ProteinDecay Canonical Projection (4820 <-> 482)

## 1. Problem statement

`ProteinDecay` is blocked in L2.1 replay because the harness and process are operating on different state surfaces.
The MATLAB process evolves protein monomer state on an expanded form-aware representation (`4820` monomer-form entries, with an explicit compartment axis in trace snapshots), while the current Python replay path overlays only a `482`-entry mature-monomer surface.
Because the substrate update in `ProteinDecay` depends on monomer-form decay channels (not just aggregate mature counts), the mismatch prevents bit-identical replay.

The current harness workaround is a literal head-slice projection (`np.arange(482)`), which is non-canonical and loses biological state meaning.
Beat-4 (`7ec8344`) correctly refused to "patch in" substrate deltas from trace hints because that would hide, not solve, the representation gap.
To get to GREEN honestly, we need a declared projection operator from the full monomer state to the `482` replay surface, plus a right-inverse scatter for replay initialization.

## 2. The 4820 space, explicitly

### 2.1 Evidence anchors

Primary anchors used for this design:

1. MATLAB source:
   `E:/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinDecay.m`
2. MATLAB state source:
   `E:/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/ProteinMonomer.m`
3. v2 trace artifact:
   `E:/opencell/data/m1_sources/karr_native/per_process_traces_v2/ProteinDecay_100ticks.mat`
4. Python process:
   `opencell/vivarium/karr_protein_decay_light.py`
5. Existing TOA schema/projection pattern:
   `data/schemas/per_process/terminal_organelle_assembly.toml`
   and
   `opencell/vivarium/karr_terminal_organelle_assembly.py`

### 2.2 Compartments

Global Karr compartment count is `6` (`this.compartment.count` in MATLAB process/state code paths).
In `ProteinDecay` trace snapshots, `monomers` is a matrix of shape `(6, 4820)` per tick.

`ProteinDecay` docstring and state data both indicate protein monomers are active in `5` compartments for this process.
The missing sixth slot is the DNA compartment (present globally, zero for protein monomer counts in this process snapshot).

Operational conclusion for projection:

- Global compartment axis exists and has cardinality `6`.
- Active nonzero monomer compartments in this process snapshot are `5`.
- Projection must be robust to both facts (never assume exactly 5 or exactly 6 nonzero rows).

### 2.3 Modification / form states

`ProteinMonomer.m` defines ten disjoint index sets, each length `482`:

1. `nascentIndexs`
2. `processedIIndexs`
3. `processedIIIndexs`
4. `signalSequenceIndexs`
5. `foldedIndexs`
6. `matureIndexs`
7. `inactivatedIndexs`
8. `boundIndexs`
9. `misfoldedIndexs`
10. `damagedIndexs`

`wholeCellModelIDs` is repeated 10x in that class, so each base protein WID appears in ten form slots.

Therefore:

- Base protein IDs (`P`) = `482`
- Form states (`F`) = `10`
- Monomer-form axis size = `P * F = 482 * 10 = 4820`

### 2.4 Arithmetic check and storage views

The exact arithmetic is:

- `4820 = 482 * 10` (protein IDs x form states)
- Raw trace monomer matrix per tick is `(6, 4820)`
- Flattened raw scalar count per tick is `6 * 4820 = 28920 = 482 * 10 * 6`

This yields two valid state views:

1. **Form-major matrix view:** `M_full in R^(C x 4820)` where `C=6`
2. **Compartment-collapsed form view:** `M_form in R^4820` where `M_form = sum_c M_full[c, :]`

The user-requested projection `pi: R^4820 -> R^482` is defined on view (2).
For raw trace ingestion on view (1), apply a compartment-collapse pre-step before `pi`.

### 2.5 Current mismatch walkthrough (why RED persists)

Current replay path behavior, simplified:

1. Harness reads `states_before/monomers[tick]` as `(6, 4820)`.
2. Harness utility flattens to `28920` scalars without preserving matrix semantics.
3. Process test applies literal `np.arange(482)` projection.
4. Process receives only a head slice, not a sum-over-form/compartment projection.

Why this is structurally wrong:

1. Head slicing depends on flatten order, not biology.
2. It is not invariant to trace orientation `(6, 4820)` vs `(4820, 6)`.
3. It drops non-head form/compartment mass that still contributes to decay kernels.
4. It cannot be interpreted as any documented MATLAB state transform.

Result:

- Substrate and monomer deltas that depend on non-head form slots
  (for example signal-sequence decay channels)
  cannot be represented faithfully at the current replay input surface.

### 2.6 Terminology used in this design

To avoid ambiguity, this doc uses:

1. **Base surface (`482`)**
   one value per base protein WID.

2. **Form surface (`4820`)**
   ten form slots per base WID, compartment-collapsed.

3. **Full trace surface (`6 x 4820`)**
   explicit compartment axis over form slots.

4. **Canonical projection**
   `Pi_full: R^(6x4820) -> R^482` via
   compartment sum then form sum.

## 3. Projection pi definition (formal)

### 3.1 Inputs and outputs

Let:

- `P = 482` (base protein WIDs)
- `F = 10` (form states)
- `C = 6` (global compartments)
- `M_form in R^(P*F)` be the compartment-collapsed monomer-form vector

Define a deterministic block index map:

- `B(p) = {p + k*P | k in [0, F-1]}` in 0-based indexing

Then:

- `pi: R^(P*F) -> R^P`
- `pi(M_form)[p] = sum_{j in B(p)} M_form[j]`

Equivalent raw-trace operator:

- `Pi_full(M_full) = pi(sum_c M_full[c, :])`

### 3.2 Mathematical statement

For each protein `p`:

`pi(M_form)[p] = sum_{f=1..F} M_form[p, f]`

For raw trace:

`Pi_full(M_full)[p] = sum_{c=1..C} sum_{f=1..F} M_full[c, p, f]`

This is the requested natural sum-over-compartments-and-modifications projection.

### 3.3 Implementation sketch (Python pseudocode)

```python
def project_monomer_4820_to_482(m_form: np.ndarray, n_proteins: int = 482) -> np.ndarray:
    # m_form: shape (4820,)
    if m_form.ndim != 1 or m_form.size % n_proteins != 0:
        raise ValueError("expected flat 4820-like vector")
    n_forms = m_form.size // n_proteins
    reshaped = m_form.reshape(n_forms, n_proteins)  # block order from ProteinMonomer index sets
    return reshaped.sum(axis=0, dtype=np.float64)


def project_trace_matrix_to_482(m_full: np.ndarray) -> np.ndarray:
    # m_full: shape (C, 4820) from v2 trace
    if m_full.ndim != 2:
        raise ValueError("expected matrix trace snapshot")
    m_form = m_full.sum(axis=0, dtype=np.float64)
    return project_monomer_4820_to_482(m_form)
```

### 3.4 Properties

1. **Linearity**
   `pi(a*x + b*y) = a*pi(x) + b*pi(y)`.

2. **Surjectivity**
   For any `v in R^482`, choose `sigma(v)` as defined in Section 4.
   Then `pi(sigma(v)) = v`.

3. **Kernel**
   `ker(pi) = {x in R^4820 | forall p, sum_{j in B(p)} x[j] = 0}`.

4. **Idempotence relation with scatter**
   `pi o sigma o pi = pi`.

5. **Trace-operator compatibility**
   `Pi_full = pi o collapse_compartment`, where `collapse_compartment(M) = sum_c M[c, :]`.

## 4. Scatter sigma definition (formal)

### 4.1 Inputs and outputs

Define:

- `sigma: R^482 -> R^4820`
- Right-inverse used for replay initialization only

Let `I_mature[p]` be the mature-form slot index for protein `p`.
This is sourced from MATLAB `ProteinMonomer.m` (`matureIndexs`, converted to 0-based).

Then:

- `sigma(v)[I_mature[p]] = v[p]`
- `sigma(v)[j] = 0` for all other slots

If using the raw `(6, 4820)` trace-shaped intermediate:

- place values at `(cytosol_row, I_mature[p])`
- zero all other rows/slots

### 4.2 Why cytoplasm + mature (ground state)

`ProteinDecay` and `ProteinMonomer` semantics make mature cytosol the least-assumptive replay seed:

1. MATLAB initialization seeds proteins to mature/bound/inactivated families from mature references.
2. Mature indices are explicitly first-class in process resource and decay accounting.
3. Cytosol is the default enzymatic arena for Lon/peptidase-driven monomer decay logic.
4. Replay `482` input has no compartment/form labels; mature-cytosol is the canonical deterministic anchor.

### 4.3 Properties

1. **Right inverse**
   `pi(sigma(v)) = v` for all `v in R^482`.

2. **Non-uniqueness acknowledged**
   Many right inverses exist.
   This design fixes one canonical choice to avoid hidden test-time drift.

3. **Replay-safe**
   `sigma` is only for initialization/scatter into full-state intermediate.
   It is not a biological dynamics rule.

## 5. L2.1 replay harness integration

### 5.1 Where pi is applied

Apply projection on the harness side, not process side:

1. Read raw trace snapshot for `monomers` as matrix `(6, 4820)` from `states_before`/`states_after`.
2. Apply `Pi_full` to obtain canonical `482` comparison vector.
3. Overlay/project that `482` vector into process state and assertions.

Current non-canonical literal head-slice in:

- `tests/vivarium/test_karr_protein_decay_l2_replay.py`
  (`_INDEX_PROJECTION_LITERAL = {'monomers': np.arange(482)}`)

must be replaced by schema-driven projection.

### 5.2 Harness-side flow (proposed)

1. Add matrix-aware loader in replay harness utilities (do not flatten monomers before projection).
2. For `ProteinDecay.monomers`, run:
   `karr_482 = Pi_full(raw_6x4820_snapshot)`.
3. Keep existing L2.1 delta-integrality and mismatch checks unchanged.
4. Do not introduce trace_hint compensation for monomers/substrates in this fix.

### 5.3 Proposed schema TOML entry

Create:
`data/schemas/per_process/protein_decay.toml`

```toml
# AUTOGENERATED-style schema, extended with projection metadata

[process]
name = "ProteinDecay"
class = "ProteinDecay"
matlab_source = "data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinDecay.m"
trace_file = "data/m1_sources/karr_native/per_process_traces_v2/ProteinDecay_100ticks.mat"

[monomers]
base_wid_count = 482
form_wid_count = 4820
trace_shape = [6, 4820]
base_wids_source = "states.Polypeptide.monomerWholeCellModelIDs"
form_index_source = "states.ProteinMonomer.{nascent,processedI,processedII,signalSequence,folded,mature,inactivated,bound,misfolded,damaged}Indexs"
projection = "sum_over_compartments_and_forms"
compartment_axis = 0
form_axis = 1

[monomers.compartments]
global_count = 6
active_count = 5
global_wids = ["c", "d", "e", "m", "tc", "tm"]
cytosol_index_1based = 1

[monomers.forms]
count = 10
order = ["nascent", "processedI", "processedII", "signalSequence", "folded", "mature", "inactivated", "bound", "misfolded", "damaged"]
mature_attr = "matureIndexs"

[projection]
pi = "R^4820 -> R^482, block-sum over 10 forms"
pi_full = "R^(6x4820) -> R^482, sum compartments then forms"
sigma = "R^482 -> R^4820, scatter to mature slot"
sigma_full = "R^482 -> R^(6x4820), scatter to cytosol+mature slot"
```

Design intent:

- Keep TOA-style schema ownership of axis metadata.
- Remove hard-coded shape assumptions from test code.
- Make projection behavior auditable and reusable across harness/process layers.

## 6. L2.1 process source integration

### 6.1 Can process stay purely in 482-space?

Not safely for this case if we require biological fidelity in substrate deltas.
`ProteinDecay` catalytic kernels are form-aware and compartment-gated.
The tick-3 residue itself was traced to a specific signal-sequence monomer decay column.

A pure 482-space implementation can only match if effective rates are pre-aggregated with no gating loss.
That is unlikely to be bit-identical under stochastic and resource-limited kinetics.

### 6.2 Recommended process architecture

Use a small internal helper class (analogous in role to TOA's projection schema object):

- Name suggestion: `_StateProjection`
- Lives in `opencell/vivarium/karr_protein_decay_light.py` (or future full process module)

Responsibilities:

1. Load/validate `matureIndexs` and form block metadata.
2. Provide `pi` / `sigma` / `Pi_full` methods.
3. Convert replay `482` surface to a 4820-form intermediate when kernels need it.
4. Convert full intermediate back to `482` deltas for process output.
5. Enforce explicit axis ordering and index sanity checks.

### 6.3 4820 intermediate scope

If needed, keep the 4820 (or 6x4820) intermediate:

- Ephemeral within `next_update`
- Reconstructed from replay surface via `sigma` only in replay path
- Never written as a public Vivarium store in L2.1

This preserves current chassis interfaces while unblocking biologically coherent kernel execution.

## 7. Implementation plan (estimated effort per stage)

### Stage 1: schema TOML

Scope:

1. Add `data/schemas/per_process/protein_decay.toml`.
2. Encode monomer axes, form order, mature index source, compartment metadata.
3. Add parser validation hooks (shape, axis, cardinality).

Estimate:

- 1.5 to 2.5 hours

Deliverable gate:

- Schema parses.
- Projection metadata round-trips in unit test.

### Stage 2: harness-side pi integration

Scope:

1. Add matrix-preserving reader path for `ProteinDecay.monomers`.
2. Replace literal head-slice in L2 test with schema-driven `Pi_full`.
3. Keep existing L2 assertions unchanged.

Estimate:

- 3.0 to 4.5 hours

Deliverable gate:

- No hard-coded `np.arange(482)` projection remains for ProteinDecay monomers.
- L2 test fails only on real biology deltas, not dimensional mismatch artifacts.

### Stage 3: process source refactor

Scope:

1. Add `_StateProjection` helper.
2. Wire optional 4820-form intermediate path for monomer decay kernels.
3. Keep no-oracle contract and allocator behavior intact.

Estimate:

- 4.5 to 6.5 hours

Deliverable gate:

- Process computes deltas from state-only inputs.
- No trace-hint backfilling for monomer/substrate parity.

### Stage 4: validation gate

Scope:

1. Re-run ProteinDecay L2.1 replay.
2. Run oracle-leak scan and selected regression trio.
3. Verify no cross-process replay regressions for projection utilities.

Estimate:

- 1.5 to 2.5 hours

Deliverable gate:

- L2.1 residue moved/cleared with canonical projection path.
- All guardrail tests pass.

### Total estimated effort to GREEN

- 10.5 to 16.0 hours

## 8. Open questions for human review

1. **Scatter compartment policy**
   Should `sigma_full` always seed cytosol+mature for all proteins, or preserve each protein's native mature compartment (`ProteinMonomer.compartments(matureIndexs)`)?

2. **Projection scope for assertion**
   For L2.1 comparison, do we want full `sum over all 6 compartments`, or `sum over active 5 only` with explicit exclusion of DNA row?

3. **Form order source of truth**
   Is `ProteinMonomer.m` index order sufficient canonical authority, or do we also require emitted metadata in replay fixtures to prevent future silent reorder?

4. **Complex projection coupling**
   Should this task include canonical projection for `complexs` (current `147` subset head-slice) in the same pass, or keep scope strictly monomer `4820 -> 482`?

5. **Harness API surface**
   Should projection operators live in generic replay utilities (`tests/vivarium/l2_replay_common.py`) or process-local test helpers to avoid over-generalizing early?

6. **Full-process roadmap**
   Does this projection design target only `ProteinDecay-light` replay parity, or should it be treated as required infrastructure for future full `ProteinDecay` process implementation?

## 9. Anti-design (what to reject)

Reject the following approaches:

1. **Hard-coding 4820 zeros in process source**
   This hides missing mapping semantics and violates chassis-state ownership.

2. **Relaxing harness length comparison**
   This makes L2.1 easier to pass without solving biological/state correctness.

3. **Reimplementing MATLAB stochastic monomer decay from trace outputs**
   This creates an RNG-parity wall and risks oracle-driven behavior.

4. **Keeping literal head-slice projection (`np.arange(482)`)**
   This is index-position coincidence, not a biological or schema-backed mapping.

5. **Using trace_hint to inject missing monomer/substrate deltas**
   This converts a representation bug into an oracle-coupling bug.

## 10. Decisions (2026-06-01) — resolutions to Section 8 open questions

Rubber-duck reviewed in session 5c51d44b-5a9f-4b23-85ff-0fddaadf2212 on
2026-06-01. Each open question now has a binding decision. Section 8 is
preserved as historical context; this section is the source of truth for
implementation.

### Q1 (scatter compartment policy) — DECISION: always cytosol+mature
- `sigma` always seeds cytosol+mature for all proteins.
- Justified in Section 4.2; no per-protein lookup needed.
- **Guardrail**: `sigma` docstring must state "harness-internal only, never
  fed as input to a process source". The biologically-wrong-looking
  compartment dimension is fine for L2.1 comparison (pi sums all 6) but
  must not leak into runtime process code paths.

### Q2 (projection scope for assertion) — DECISION: empirical, default sum-all-6
- This is not a design choice; it is a measurable fact about the recorded
  482 vector.
- **Stage-1 acceptance gate**: implement `pi = sum_all_6` as default; the
  first stage of the implementation MUST validate `pi(M_full_tick0) ==
  recorded_482_tick0` byte-equal on the actual protein_decay v2 trace.
- If the byte-equal check passes: lock `pi = sum_all_6`, document.
- If it fails: try `pi = sum_active_5` (exclude DNA-bound compartment),
  re-verify. Whichever matches the recorded vector wins.
- Hard rule: do not flip the comparison surface (i.e., do not change the
  recorded vector). The MATLAB-emitted 482 is ground truth.

### Q3 (form-order source of truth) — DECISION: emit explicit metadata
- Replay fixtures for protein_decay (and any future process with form-
  state-flattened state) MUST carry a `form_order` field: a length-F list
  of canonical form-state names in MATLAB's `ProteinMonomer.m` index
  order (e.g., `["nascent", "processedI", "processedII", "signalSequence",
  "folded", "mature", "inactivated", "bound", "misfolded", "damaged"]`).
- Format precedent: this is the first fixture to carry semantic-metadata
  blocks. Others will follow as needed.
- Rationale: positional encoding via "MATLAB source is canonical" failed
  to surface the 4820-vs-482 mismatch for 3+ days during initial
  protein_decay attacks. The 10-string list is the smallest artifact
  that would have surfaced the problem instantly.

### Q4 (complex projection coupling) — DECISION: strictly monomers
- Scope: monomer 4820 -> 482 only.
- `complexs` is OUT of scope for this implementation pass.
- **Verification step before any future bundling**: run a one-liner check
  on actual `complexs` 147-head-slice residue magnitude. If near-zero,
  YAGNI confirmed; if non-trivial, complexs gets its own design doc.
- Do NOT speculatively add complexs projection to this pass.

### Q5 (harness API surface) — DECISION: common module from day one
- Projection operators land in `tests/vivarium/l2_replay_common.py`.
- NOT process-local.
- Rationale: the functions are pure, numeric, with fully-fixed shapes
  `(4820,) -> (482,)` and `(482,) -> (4820,)`. There is no API
  uncertainty to defer. Process-local was a reflex; common-module is
  the right call.
- Functions to export:
  - `project_monomer_4820_to_482(m_form: np.ndarray) -> np.ndarray`
  - `project_trace_matrix_to_482(m_full: np.ndarray) -> np.ndarray`
  - `scatter_monomer_482_to_4820(v_482: np.ndarray, form_order: tuple[str, ...]) -> np.ndarray`
  - (form_order is required arg; comes from fixture metadata per Q3)

### Q6 (full-process roadmap) — DECISION: design for both pi and sigma
- Both `pi` (projection) and `sigma` (scatter) ship in this
  implementation pass.
- `pi` is exercised by the L2.1-light protein_decay test.
- `sigma` is exercised by **at least one property test**:
  `pi(sigma(v)) == v` for a set of representative `v in R^482`
  (e.g., zeros, ones, recorded tick-0 vector, random non-negative
  integer vectors).
- No untested sigma in main. The right-inverse property is testable
  without any process consumer.

## 11. Implementation sequencing (post-decisions)

Stage order:
1. **Empirical Q2 check** (prerequisite, sequential): run
   `pi=sum_all_6` against the recorded 482-vector on protein_decay v2
   trace tick 0. Lock Q2 answer before Stage 2 fires.
2. **Stage 2A (parallelizable)**: implement `pi` and `sigma` in
   `tests/vivarium/l2_replay_common.py` with property test
   (`pi(sigma(v)) == v`) and unit tests (shape, linearity, kernel).
3. **Stage 2B (parallelizable, independent of 2A)**: extract canonical
   `form_order` from `lib/karr_native/src/+edu/+stanford/+covert/+cell/+sim/+state/ProteinMonomer.m`
   (or wherever the form-index sets are defined) and add `form_order`
   to the protein_decay v2 fixture emission path.
3. **Stage 3 (sequential, after 2A+2B)**: wire `project_trace_matrix_to_482`
   into `test_karr_protein_decay_l2_replay.py` for the 482-comparison.
4. **Stage 4**: full L2.1 strict re-run; expect protein_decay GREEN if
   the projection is correct and there are no other residues (refire
   single-source-file attack on any remaining residue with
   trace-hint patterns).

### 11.1 Empirical update (2026-06-02): Path-A lift reproduces +144; blocker is missing trace surface

Investigation in worktree `pdecay-4820-lift` produced three key facts:

1. **Current baseline (without forcing 4820 latent monomer path):**
   `pytest tests/vivarium/test_karr_protein_decay_l2_replay.py -v --tb=short`
   fails at `tick=3, substrates[0], diff=-6` (`oc=0, karr=6`).
2. **Path-A diagnostic (force-feed full 4820 monomer matrix into latent decay path):**
   first mismatch becomes the historical fingerprint
   `tick=1, substrates[0], diff=+144` (`oc=144, karr=0`).
3. **Trace-surface evidence of missing context:**
   - `states_before/monomers` is `(6, 4820)` and `metadata/snapshot_properties`
     are only `boundEnzymes, complexs, enzymes, monomers, substrates`.
   - Mismatch ticks include substrate-energy events with no `complexs` change;
     at least one such tick (`tick=6`) has no monomer delta either, which is
     consistent with ProteinDecay substeps not represented by the 5-observable
     trace surface (notably `evolveState_DegradeAbortedPolypeptides`, and
     potentially refolding/misfolding side effects).

Decision update:

- **Choose Path B** (extend extraction surface), not Path A.
- Path A is not safely closable here: a 482-only light process cannot be lifted
  to faithful 4820 replay without additional per-tick substep observables.
- Minimal required extraction change is a new ProteinDecay trace schema that
  includes substep-relevant state beyond the current 5 fields (at minimum,
  proteolysis-tagged polypeptide context), followed by MATLAB re-extraction.
