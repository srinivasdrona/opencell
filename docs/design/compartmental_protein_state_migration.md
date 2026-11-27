# COMPARTMENTAL_PROTEIN_STATE_MIGRATION_DESIGN

Status: planner deliverable (Opus role) for branch
`fix/compartmental-protein-state-20260923`, worktree
`E:\opencell-worktrees\fix-compartmental-protein-state`.
Downstream roles: Gemini test writer (freezes adversarial tests) -> Sonnet doer
(implements) -> GPT reviewer. **No production or test code is changed by this
document.**

Template: `docs/prompts/DESIGN_TEMPLATE.md` (full form; this is a genuine
cross-surface architectural fork, not a revision).
Composition: `docs/prompts/COMPOSITION_MANDATE_v2.md` slot-2.

---

## 0) Spec-authority quotations (read these before any decision below)

### 0.1 Pre-L2.5 honesty baseline entry (authoritative scope spec)

Quoted verbatim from `docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml`
lines 456-504 (entry begins at line 456; next entry `Transcription` begins at
line 506):

```yaml
  - name: TerminalOrganelleAssembly
    behavior_gate: L2.1
    behavior_verdict: GENUINE
    eligibility: BLOCKED_CODE_DEVIATION
    findings:
      - id: TOA-REDUCED-STATE
        kind: CODE_DEVIATION
        disposition: OPEN
        summary: >-
          OpenCell uses protein-activity gates and assembled counters instead
          of Karr's full unincorporated/incorporated substrate matrices and
          fixed-point full-count transfer.
        evidence:
          - path: opencell/vivarium/karr_terminal_organelle_assembly.py
            lines: "307-350"
          - path: opencell/vivarium/karr_terminal_organelle_assembly.py
            lines: "403-455"
      - id: TOA-PRODUCTION-TOPOLOGY
        kind: CODE_DEVIATION
        disposition: OPEN
        summary: >-
          The production topology connects only protein and cell; no substrate
          compartment state is available for the MATLAB transfer.
        evidence:
          - path: opencell/vivarium/karr_composite.py
            lines: "2195-2198"
      - id: TOA-TRACE-HINT
        kind: CODE_DEVIATION
        disposition: OPEN
        summary: >-
          A replay-only states-after substrate outcome can override the
          biological transfer path.
        evidence:
          - path: opencell/vivarium/karr_terminal_organelle_assembly.py
            lines: "357-377"
          - path: opencell/vivarium/karr_terminal_organelle_assembly.py
            lines: "447-452"
      - id: TOA-COMPARTMENT-PROJECTION
        kind: CODE_DEVIATION
        disposition: OPEN
        summary: >-
          OpenCell projects terminal-organelle source/destination compartments
          to generic keys and does not preserve the biological compartment
          labels.
        evidence:
          - path: opencell/vivarium/karr_terminal_organelle_assembly.py
            lines: "190-211"
          - path: opencell/vivarium/karr_terminal_organelle_assembly.py
            lines: "378-401"
```

Baseline header context (same file, lines 1-20): `audit_base_commit:
6a038b1d084543ddd847528ff6e698a9dba37626`, `source_tree.sha256:
6dbf656c4dba53e44954ee82cd64e69285c8256712025f91433a849910a14308`,
`policy: "A lower-gate PASS is necessary but not sufficient for L2.5
eligibility."`

**Line-drift note (verified, not assumed).** The baseline's
`TOA-PRODUCTION-TOPOLOGY` anchor reads `karr_composite.py:2195-2198`; at this
worktree's HEAD (`5649000`) the same topology block is at
`karr_composite.py:2244-2247`. The block content is unchanged:

```python
        "karr_terminal_organelle_assembly": {
            "protein": ("protein",),
            "cell": ("cell",),
        },
```

All other TOA anchors resolve unchanged at HEAD (verified against
`opencell/vivarium/karr_terminal_organelle_assembly.py` method line map in
2.3). Implementers must re-resolve baseline line anchors against HEAD rather
than trusting the recorded numbers.

### 0.2 Karr MATLAB spec quotations (highest authority)

`+state/ProteinMonomer.m:95-104` (form-block layout, 10 blocks of
`numMonomers`):

```matlab
this.nascentIndexs        = (1:numMonomers)';
this.processedIIndexs     = (1:numMonomers)' + this.nascentIndexs(end);
this.processedIIIndexs    = (1:numMonomers)' + this.processedIIndexs(end);
this.signalSequenceIndexs = (1:numMonomers)' + this.processedIIIndexs(end);
this.foldedIndexs         = (1:numMonomers)' + this.signalSequenceIndexs(end);
this.matureIndexs         = (1:numMonomers)' + this.foldedIndexs(end);
this.inactivatedIndexs    = (1:numMonomers)' + this.matureIndexs(end);
this.boundIndexs          = (1:numMonomers)' + this.inactivatedIndexs(end);
this.misfoldedIndexs      = (1:numMonomers)' + this.boundIndexs(end);
this.damagedIndexs        = (1:numMonomers)' + this.misfoldedIndexs(end);
```

`+state/ProteinMonomer.m:27-40` — `stateNames = {'counts'}` is the **only**
state property of `ProteinMonomer`. There is no second protein count state in
Karr.

`+process/TerminalOrganelleAssembly.m:316-337` (`evolveState`, verbatim):

```matlab
function evolveState(this)
    % incorporate proteins into terminal organelle
    % cytoplasm -> terminal organelle cytoplasma
    % membrane  -> terminal organelle membrane
    while any(this.substrates(:, this.compartmentIndexs_unincorporated))
        activeReactions = ...
            this.localizationReactions(:, :, 1) * (this.substrates(:, 1) > 0) + ...
            this.localizationReactions(:, :, 2) * (this.substrates(:, 2) > 0) >= ...
            this.localizationThreshold;

        localizingProteins = logical(...
            this.substrates(:, this.compartmentIndexs_unincorporated) .* ...
            (this.localizationSubstrates' * activeReactions));
        if ~any(localizingProteins)
            break;
        end

        this.substrates(localizingProteins, this.compartmentIndexs_incorporated) = ...
            this.substrates(localizingProteins, this.compartmentIndexs_incorporated) + ...
            this.substrates(localizingProteins, this.compartmentIndexs_unincorporated);
        this.substrates(localizingProteins, this.compartmentIndexs_unincorporated) = 0;
    end
end
```

`+process/TerminalOrganelleAssembly.m:124-125`:

```matlab
compartmentIndexs_incorporated   = 1; %index of terminal organelle cytosol and membrane compartments of substrates
compartmentIndexs_unincorporated = 2; %index of cytosol and membrane compartments of substrates
```

`Process.m:818-820` (the substrate matrix is a **view of
`monomer.counts`**, written straight back — this is the single-authority
proof):

```matlab
if ~isempty(this.substrateMonomerGlobalCompartmentIndexs)
    this.monomer.counts(this.substrateMonomerGlobalCompartmentIndexs) = ...
        this.substrates(this.substrateMonomerLocalIndexs, :);
end
```

`Process.m:569-571` is the symmetric read (`substrates(...) =
monomerCounts(this.substrateMonomerGlobalCompartmentIndexs)`).

`+process/ProteinTranslocation.m:198-201, 210, 217, 350-353`:

```matlab
this.monomerCompartments = double(knowledgeBase.proteinMonomerCompartments);
this.monomerCompartments(this.monomerCompartments == this.compartment.terminalOrganelleCytosolIndexs)  = this.compartment.cytosolIndexs;
this.monomerCompartments(this.monomerCompartments == this.compartment.terminalOrganelleMembraneIndexs) = this.compartment.membraneIndexs;
this.monomerIndexs_translocating = find(this.monomerCompartments ~= this.compartment.cytosolIndexs);
...
this.monomers = this.monomer.counts(this.monomer.processedIIndexs, :, :);   % copyFromState
this.monomer.counts(this.monomer.processedIIndexs, :, :) = this.monomers;    % copyToState
...
this.monomers(idx_monomer, this.monomerCompartments(idx_monomer)) = ...
    this.monomers(idx_monomer, this.monomerCompartments(idx_monomer)) + 1;
this.monomers(idx_monomer, this.compartment.cytosolIndexs) = ...
    this.monomers(idx_monomer, this.compartment.cytosolIndexs) - 1;
```

---

## DAP Intent (slot-1 carryover)

**INTENT**

1. **What I am doing.** Designing (not implementing) the smallest
   source-faithful migration that gives OpenCell one authoritative,
   compartment-resolved `ProteinMonomer` count state, puts
   `TerminalOrganelleAssembly` and `ProteinTranslocation` on it, and turns the
   legacy flat `protein.counts` into an exact, non-writable derived view.

2. **Contract (Beat 1).** Karr keeps exactly one protein count state:
   `ProteinMonomer.counts`, a `4820 x 6` integer matrix
   (`ProteinMonomer.m:27-40, 95-104`). Every protein process reads a
   *view* of it and writes back through `Process.m:569-571 / 818-820`. Done =
   the OpenCell chassis has the same property: exactly one writable
   `(form, WID, compartment)` cell per molecule, TOA executes
   `TerminalOrganelleAssembly.m:316-337` verbatim on that store, and the flat
   aggregate equals the compartment sum at every point a reader can observe.

3. **Expected observable (Beat 3, condensed).** After Stage 1, for every
   migrated WID, `protein.counts[wid] == sum over {c,d,e,m,tc,tm} of
   protein.compartment_counts.mature[wid][k]` holds after every writer, and a
   pure TOA transfer tick changes the compartment distribution while leaving
   the aggregate **exactly unchanged**. A dual-store implementation that also
   accumulates into `protein.counts` necessarily breaks the second claim. A
   multi-copy synthetic state (`uninc = 5`) transfers all 5 in one tick, and a
   3-deep hierarchy (`HMW1(inc)=1`, `HMW3(uninc)=2`, `P32(uninc)=4`,
   `P65(uninc)=3`) resolves fully in one `next_update`; a per-tick `+1`
   implementation fails both.

4. **Inversion (Beat 4).** The most embarrassing outcome: the design *looks*
   single-authority, but one un-inventoried module keeps `accumulate`-writing
   `protein.counts` for a migrated WID. Nothing fails on tick 0 because the
   projection Step immediately overwrites it; the divergence surfaces only as
   silent mass creation in the compartment store versus the flat view many
   ticks later, and only in a full-chassis run nobody executes in the fix PR.
   Second-worst: the 8x2 matrix is rebuilt with the right *shape* but the
   `localizationReactions` third axis is read with the planes swapped, so the
   "incorporated" requirement is evaluated against the unincorporated column.
   **This is not hypothetical: it is the current state of
   `karr_terminal_organelle_assembly.py:165-171`** (see finding
   `TOA-PLANE-SWAP` in 4.4), and it is invisible in the 100-tick oracle.

5. **PM sanity-check.** *I am assuming the existing L2.1 replay harness for
   TOA may be rewritten by the Gemini test-writer role to overlay
   `states_before/substrates` into the new authoritative store (rather than
   into a process-local `substrates` port), and that dropping TOA's unused
   `enzymes` / `boundEnzymes` ports is acceptable because
   `evolveState` never reads them. If the operator instead requires the
   existing L2.1 harness to keep working byte-for-byte unchanged, then
   Decision D4 (drop the `substrates`/`enzymes` ports) is wrong and must be
   replaced by a read-only derived `substrates` view.*

Beat-2 (surface) is 2) and 3) below. Beat-5 (verification) is the Gemini test
set in 6) plus the doer's own run; this document performs no code change and
therefore has no Beat-5 measurement of its own beyond the probes recorded in
4).

---

## 1) Design contract

```
Contract:
- Required behavior:
    R1. Exactly one writable authority exists for every protein-monomer
        molecule count, keyed (form, WID, compartment) with form in Karr's 10
        form blocks and compartment in Karr's 6 KB compartments.
    R2. TerminalOrganelleAssembly reads its 8x2 (substrate x
        incorporated/unincorporated) matrix from that authority, executes
        TerminalOrganelleAssembly.m:316-337 exactly (fixed-point loop,
        full-count transfer, >= threshold, break-on-no-progress), and writes
        the result back to that authority and nowhere else.
    R3. ProteinTranslocation moves copies between compartments of that same
        authority (processedI form: cytosol -> monomerCompartments[wid]), not
        between a queue branch and a species-level string label.
    R4. Legacy readers of flat `protein.counts[wid]` observe, at every point
        at which they can read, a value exactly equal to the sum over the 6
        compartments of that WID's authoritative mature row, and no production
        code path can write that leaf.

- Why this matters:
    TOA is BLOCKED_CODE_DEVIATION on four findings that all reduce to one
    root cause: OpenCell has no compartment-resolved protein state, so the
    process was implemented against a substitute representation (activity
    gates + assembled counters + generic compartment_N keys) and needs a
    trace_hint escape hatch to reproduce the oracle. Karr needs no such thing
    because TOA has NO private state at all -- its `substrates` property is a
    view of ProteinMonomer.counts (Process.m:569-571, 818-820). Reproducing
    the representation removes all four findings at once, and it is a
    precondition for ProteinDecay, ProteinTranslocation, ChromosomeCondensation
    and every other process carrying a *-COMPARTMENT-PROJECTION finding.

- Done = (property statement, not command success):
    For any reachable chassis state S and any tick t, let A(S) be the
    authoritative compartment tensor and F(S) the flat protein.counts map.
    Then (a) F = Pi(A) where Pi is the fixed mature-row compartment sum,
    (b) no production update dict mutates F except the projection Step,
    (c) TOA(A) equals MATLAB evolveState applied to the 8x2 view of A, for
    every A including A with unincorporated counts > 1 and chained
    dependencies, and (d) sum over all compartments of A is conserved by TOA.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode:
    The projection Step makes F correct at every observation point, which
    masks a surviving accumulate-writer on F. Tests that only assert
    "F == Pi(A)" pass forever while the surviving writer silently doubles or
    loses mass in A, because F is recomputed from A and never compared to its
    own history. The guard is a *write-rejection* test plus a static lint over
    production update dicts, NOT a consistency test.
- What would falsify this contract statement:
    Evidence that some legacy consumer semantically needs `protein.counts` to
    mean something other than the mature-row compartment sum (e.g. a reader
    that means "cytosolic free pool"). 2.4 records the one real instance
    (ProteinActivation's compartment-0-active semantics) and 5)/D6 resolves it.
```

---

## 2) Inventory of existing artifacts

Machine-checkable manifest. `path` is repo-relative unless rooted at
`E:\opencell\` (primary MATLAB sources live in the main checkout, not the
worktree). `verified=` records the content check actually run, per
DESIGN_TEMPLATE rule 5.

### 2.1 Primary MATLAB sources and canonical fixtures

- [A01] path=`E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+state\ProteinMonomer.m` | kind=code (primary spec) | role=defines the ONLY protein count state (`stateNames={'counts'}`, L27-40), the 10 form blocks (L95-104), and the per-WID KB compartment vector (L129-130) | verified=read in full (188 lines)
- [A02] path=`E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\TerminalOrganelleAssembly.m` | kind=code (primary spec) | role=`evolveState` fixed-point full-count transfer (L316-337); `compartmentIndexs_incorporated=1`/`_unincorporated=2` (L124-125); `localizationThreshold = sum(sum(localizationReactions,3),2)` (L279) | verified=read L1-337
- [A03] path=`E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\ProteinTranslocation.m` | kind=code (primary spec) | role=operates on `monomer.counts(processedIIndexs,:,:)` (L210/217); tc->c, tm->m destination remap (L198-200); per-copy randperm loop with `+1` at destination / `-1` at cytosol (L325, L350-353) | verified=read L100-360
- [A04] path=`E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\Process.m` | kind=code (primary spec) | role=`copySubstratesFromState`/`copyToState` prove every process substrate matrix is a *view* of the global state (L569-571 read, L818-820 write) | verified=grepped with context at those anchors
- [A05] path=`E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+constant\Compartment.m` | kind=code (primary spec) | role=names the 6 compartment index properties (cytosol/chromosome/membrane/terminalOrganelleCytosol/terminalOrganelleMembrane/extracellular); the numeric values come from the KB, not this file | verified=read in full (41 lines)
- [A06] path=`data/karr_fixtures/per_process/ProteinMonomer_flat.mat` | kind=fixture | role=canonical initial `counts` (4820 x 6, sum 20929), form index blocks, per-WID KB compartments | verified=loaded via `bin\oc-py.cmd`; shapes, block boundaries, and per-compartment totals printed (4.1)
- [A07] path=`data/karr_fixtures/per_process/TerminalOrganelleAssembly_flat.mat` | kind=fixture | role=`substrates` 8x2 uint8, `localizationReactions` 10x8x2, `localizationSubstrates` 10x8, `localizationThreshold` 10, `substrateMonomerCompartmentIndexs` 8x2, `substrateMonomerGlobalCompartmentIndexs` 8x2 | verified=loaded; every matrix printed and cross-checked against A06 (4.2, 4.3)
- [A08] path=`data/m1_sources/karr_native/per_process_traces_v2/TerminalOrganelleAssembly_100ticks.mat` | kind=trace (oracle) | role=L2.1 oracle; `states_before/after` for substrates/enzymes/boundEnzymes | verified=opened with h5py; mutated ticks enumerated = **[6, 46, 68]**, each a single-copy MG_312 transfer (4.5). **This is why the current implementation passes L2.1 despite not doing full-count transfer.**
- [A09] path=`data/karr_fixtures/per_process/ProteinTranslocation_flat.mat` | kind=fixture | role=monomer lengths, SRP pathway flags, `monomerCompartments` codes consumed by the OC port | verified=not loaded directly in this pass; its derived values were read out of the OC module's parsed attributes (A13 probe). **Content not independently verified** -- flagged in 2.5.

### 2.2 OpenCell production surfaces (the migration target)

- [A10] path=`opencell/vivarium/karr_terminal_organelle_assembly.py` | kind=code | role=SUT; carries all four baseline findings plus the previously unrecorded plane swap (4.4). Method map: `_load_fixture` L111, rule parse L165-171, `_load_substrate_projection_schema` L182, `ports_schema` L271, `_requirement_uninc_met` L307, `_reaction_is_eligible` L321, `_substrate_deltas_from_trace_hint` L357, `_substrate_deltas_from_compartment_transfer` L378, `next_update` L403 | verified=read in full (455 lines)
- [A11] path=`opencell/vivarium/karr_protein_translocation.py` | kind=code | role=second migration target; `_TERMINAL_ORGANELLE_EXCLUSIONS` L25; `ports_schema` L251-300; `next_update` L307-455; writes `protein.location` (string) + `protein.unprocessed_counts` (negative) and never increments a destination | verified=read L180-470
- [A12] path=`opencell/vivarium/karr_protein_activation.py` | kind=code | role=**precedent and hazard**: already stores 6 proteins x 6 compartments, but splits them across `protein.counts` (= active, compartment 0), `protein.activation_active_noncytosol_counts` (compartments 1-5), `protein.activation_inactive_counts` (compartments 0-5). Constants at L23-24; branch schema L497-548; canonical state L588-628 | verified=read L140-260 and L490-640
- [A13] path=`opencell/vivarium/karr_composite.py` | kind=code | role=topology + flow; TOA topology L2244-2247 (protein, cell only); ProteinTranslocation topology L2162-2168; ProteinActivation topology L2169-2174; v6 `flow=` block L2425-2450 (only request calculators, allocation step, segregation evolution, coordinator are Steps) | verified=grepped with context; flow block read in full
- [A14] path=`opencell/vivarium/karr_observability_step.py` | kind=code | role=Step that **reads** `protein.counts` for all 482 WIDs to compute protein mass (L183, `_mass_from_counts`); must run *after* the projection Step | verified=read L176-202 + ports at L114
- [A15] path=`data/schemas/per_process/terminal_organelle_assembly.toml` | kind=schema | role=autogenerated v2.1 schema; `observables.substrates.shape = [2, 8]`; `activity_profile.substrates_mutated_ticks = 3`; `pass_through = ["boundEnzymes", "enzymes"]`; `trace_hint_keys = []` | verified=read in full
- [A16] path=`tests/vivarium/test_karr_terminal_organelle_assembly_l2_replay.py` | kind=test | role=current L2.1 GENUINE harness; observables `('substrates','enzymes','boundEnzymes')`; `_OBSERVABLE_TO_WIDS_ATTR` maps `substrates -> substrate_wids` | verified=read L1-105
- [A17] path=`tests/vivarium/test_karr_terminal_organelle_assembly.py` | kind=test | role=7 unit tests asserting the *reduced* semantics that this migration deletes (`test_activity_gate_blocks_all_assembly_when_off`, `test_100_tick_progression_reaches_and_holds_target_two`, ...). **These are prior-art tests that encode the deviation and must be replaced, not preserved.** | verified=test function names enumerated
- [A18] path=`tests/vivarium/l2_replay_common.py` | kind=test-helper | role=`cell_vector` oracle reader (L136-153), `build_state_template` (L347), `overlay_observable_into_state`, and the `trace_hint` helper (L600-618) whose contract says process source MUST NOT call it -- TOA currently reads the dict it populates | verified=grepped with context
- [A19] path=`docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml` | kind=status/spec | role=authoritative eligibility ledger; TOA entry L456-504 (quoted in 0.1); ChromosomeCondensation `CC-COMPARTMENT-PROJECTION` L50-56 is the same root cause in another process | verified=read L1-70 and L440-530
- [A20] path=`docs/phase_f/PROTEIN_DECAY_PROJECTION.md` | kind=doc (prior failed attempt) | role=**prior art on exactly this problem**: documents that ProteinDecay is L2.1-blocked because "the harness and process are operating on different state surfaces" (4820 form entries with a compartment axis vs a 482 mature surface), and that the 6th (DNA) compartment is globally present but zero for monomers. Its proposed remedy was a *projection* (collapse), i.e. the lossy direction this design reverses | verified=read L1-120
- [A21] path=`plan.md` | kind=status | role=operational handoff block L60-100 fixes the role split, the "no private TOA matrix" constraint, and the ban list | verified=read L1-140
- [A22] path=`opencell/vivarium/karr_protein_processing_ii.py` | kind=code | role=**undeclared writer**: `ports_schema` L125-160 declares `processed_counts/unfolded_counts/signal_sequence_counts/enzyme_counts` but `_build_update` L337-345 writes `protein_update["counts"]` for all 482 `unprocessed_monomer_wids`. It writes a leaf it never declared, relying on a sibling process having declared it | verified=read L300-348 + AST port inventory

### 2.3 Inventory Beat-4 inversion

```
- What critical artifact could still be missing from this list?
    (a) A non-Vivarium consumer of protein counts (analysis scripts,
        persistence, division/divider logic). Mitigated: the AST port scan was
        run over `opencell/` (only `opencell/vivarium/*` declares a protein
        port) and `scripts/` (only `scripts/run_chassis_v6_32400t.py`
        surfaces one). NOT fully mitigated for `opencell/vivarium/persist.py`
        and any `_divider` on protein leaves -- QO4.
    (b) A MATLAB protein process not read here (ProteinProcessingI/II,
        ProteinFolding, ProteinModification, ProteinDecay `.m`). Deliberate:
        the slot-3 directive scopes MATLAB reading to PM/TOA/PT unless the
        consumer inventory proves otherwise. The inventory DOES prove folding,
        processing and decay are Stage-1 consumers (2.4), so their `.m`
        sources become mandatory reading for the Stage-1 doer -- recorded as
        an explicit Stage-1 prerequisite in 9.2, not silently skipped.
- What check did you run to reduce that risk?
    `_tmp_port_inventory.py` (AST walk of every class in a tree, reporting
    every dict literal with a "protein" key inside ports_schema vs elsewhere,
    plus every ["protein"] subscript and .get("protein") call). Run over
    `opencell/vivarium` (25 modules matched), `opencell` (no additional), and
    `scripts` (1 module). Plus `_tmp_probe15.py`, which CONSTRUCTS 19
    production process classes and reports, per protein branch, the leaf count
    and the intersection with the 8 TOA WIDs.
- What could be WRONG in the artifacts we listed?
    * A08 (oracle trace) is real but *weak*: only 3 of 100 ticks mutate
      substrates and all 3 move exactly one copy. It cannot distinguish
      full-count transfer from per-tick +1. Verified by direct extraction
      (4.5). Any test plan that relies on A08 alone to prove R2 is hollow.
    * A09 content was NOT independently verified this pass (derived values
      were read through the OC module). Flagged; Stage-2 prerequisite.
    * A07's `localizationReactions` is `uint8` with a singleton third axis
      ordering that is trivially mis-indexed; its correctness was established
      by cross-checking `sum(sum(lr,3),2) == localizationThreshold` (True) and
      by decoding all 10 reactions into named dependencies (4.3).
    * A15 `compartment_wids` is ABSENT from the v2.1 schema; the OC module
      manufactures `compartment_0/compartment_1` (A10 L212-219). Those labels
      carry no biology and are the literal content of TOA-COMPARTMENT-PROJECTION.
```

### 2.4 Protein-port manifest (machine-checkable; regenerate with the probe in 6.9)

Columns: `module` | `branch` | `leaves` | `TOA-8 hits` | `class`.
`class` in {`AUTH-W` = writes counts that must become authoritative,
`DERIVED-R` = read-only consumer of the flat view, `MIGRATABLE-W` = writer of
a non-`counts` protein branch that is really a form row, `UNRELATED` = not
protein-monomer count state, `UNDECLARED-W` = writes a leaf it did not
declare}. Verdicts derive from the AST scan (writer = module builds a
`{"protein": ...}` update or `update["protein"][...] = ...`).

| # | module | branch | leaves | TOA-8 | class | evidence |
|---|---|---|---|---|---|---|
| M01 | karr_translation_v3 | unprocessed_counts | 482 | 8 | MIGRATABLE-W (nascent row, compartment c) | ports L202-210; write L767-771 |
| M02 | karr_protein_processing_i | unprocessed_counts | 482 | 8 | MIGRATABLE-W (nascent) | ports L135-162; write L299-302 |
| M03 | karr_protein_processing_i | processed_counts | 482 | 8 | MIGRATABLE-W (processedI) | write L299-302 |
| M04 | karr_protein_processing_i | counts | 1 | 0 | AUTH-W (compat mirror, `use_protein_counts_compat`) | write L303-308 |
| M05 | karr_protein_processing_ii | processed_counts | 482 | 8 | MIGRATABLE-W (processedI) | ports L125-160; write L338-339 |
| M06 | karr_protein_processing_ii | unfolded_counts | 482 | 8 | MIGRATABLE-W (processedII) | write path via `_build_update` |
| M07 | karr_protein_processing_ii | signal_sequence_counts | 482 | 8 | MIGRATABLE-W (signalSequence row) | write L342-343 |
| M08 | karr_protein_processing_ii | **counts** | (undeclared) | 8 | **UNDECLARED-W** | write L340-341 |
| M09 | karr_protein_folding | unfolded_counts | 482 | 8 | MIGRATABLE-W (folded row source) | ports L186-215; write L312-316 |
| M10 | karr_protein_folding | counts | 482 | 8 | AUTH-W (mature pool) | write L312-316 |
| M11 | karr_protein_modification | unmodified_counts | 20 | 2 (MG_217, MG_317) | MIGRATABLE-W | ports L141-170; write L290-294 |
| M12 | karr_protein_modification | modified_counts | 20 | 2 | MIGRATABLE-W | write L290-294 |
| M13 | karr_protein_modification | counts | 2 | 0 | DERIVED-R (enzymes) | ports L162-166 |
| M14 | karr_protein_translocation | unprocessed_counts | 117 | 1 (MG_318) | MIGRATABLE-W (processedI cytosol source) | ports L268-275; write L432-437 |
| M15 | karr_protein_translocation | location | 117 | 1 | **UNRELATED/DELETE** (species-level string label; no Karr analogue) | ports L276-279; write L429-436 |
| M16 | karr_protein_translocation | counts | 118 | 1 | DERIVED-R (enzyme pool) | ports L264-267; read L308, L354-360 |
| M17 | karr_protein_decay_light | counts | 482 | 8 | AUTH-W | ports L332; write L1061-1063 |
| M18 | karr_protein_activation | counts | 3 | 0 | AUTH-W with **conflicting semantics** (active, compartment 0 only) | L497-527, L588-612 |
| M19 | karr_protein_activation | activation_active_noncytosol_counts | 3 | 0 | AUTH-W (compartments 1-5, active) -> third authority | L518-531 |
| M20 | karr_protein_activation | activation_inactive_counts | 3 | 0 | AUTH-W (compartments 0-5, inactive = inactivated row) | L533-546 |
| M21 | karr_protein_activation | activity | 6 | 0 | DERIVED-R (already documented as a projection) | L552-560 |
| M22 | karr_terminal_organelle_assembly | activity | 8 | 8 | DERIVED-R (the substitute representation being deleted) | L280-285, read L412 |
| M23 | karr_ribosome_assembly | counts | 58 | 0 | AUTH-W | ports L150; write L327-329 |
| M24 | karr_chromosome_segregation(+_evolution) | counts | 3 | 0 | AUTH-W | ports L296/L326; writes via evolution step |
| M25 | karr_replication_initiation | counts | 1 | 0 | AUTH-W | ports L636; write L856-865 |
| M26 | karr_dna_supercoiling | counts | (dynamic) | **must verify** | AUTH-W (side effects) | write L1395-1402; no literal ports dict -- see QO2 |
| M27 | karr_dna_repair | counts | 9 | 0 | DERIVED-R | ports L353; read L1316 |
| M28 | karr_host_interaction | counts | 14 | 8 | DERIVED-R (adhesin gate; returns only `cell`) | ports L300/L326-330; L446-449 |
| M29 | karr_observability_step | counts | 482 | 8 | DERIVED-R (**Step**; protein mass) | ports L114; read L183 |
| M30 | karr_transcriptional_regulation | counts | 3 | 0 | DERIVED-R (TF counts) | ports L783; read L861 |
| M31 | karr_rna_processing / rna_modification / trna_aminoacylation | counts | 1 / 5 / 7 | 0 | DERIVED-R (enzyme pools) | ports L183 / L135 / L144 |
| M32 | karr_request_calculators: RequestCalculatorProteinPathway | counts, unprocessed_counts, processed_counts, unfolded_counts, unmodified_counts, location | mixed | 8 | DERIVED-R (**Step**) | ports L404-460; read L471 |
| M33 | karr_request_calculators: RequestCalculatorPTransloc | counts, unprocessed_counts, location | mixed | 1 | DERIVED-R (**Step**) | ports L679-700; read L712 |
| M34 | karr_request_calculators: RequestCalculatorRibAsm | counts | n/a | 0 | DERIVED-R (**Step**) | ports L177 |
| M35 | karr_translation / karr_translation_v2 | counts | 482 | 8 | LEGACY (non-runtime; v3 is the canonical runtime class) | ports L205 / L65 |
| M36 | scripts/run_chassis_v6_32400t.py | protein port ref | n/a | n/a | DERIVED-R (analysis) | AST scan hit |

**Manifest facts that decide the design:**

- Exactly **8 modules** currently hold a writable path to a `protein.counts`
  leaf for at least one of the 8 TOA WIDs: M08 (undeclared), M10, M17, plus
  M26 (unverified) -- and via non-`counts` protein branches M01, M02/M03,
  M05/M06/M07, M09, M11/M12, M14. Readers of those WIDs: M16, M28, M29, M32,
  M33.
- `protein.counts` is **not** a single-semantic leaf today: M10/M17 treat it
  as "mature pool", M08 pushes *unprocessed* deltas into it, M18 defines it as
  "active count in compartment 0". That three-way collision is the real
  pre-existing defect; the migration must resolve it explicitly (D6), not
  paper over it.
- `protein.location` (M15) has no Karr analogue at all. A per-species string
  cannot represent "31 copies in m and 4 in c", which is exactly what
  `ProteinTranslocation.m:350-353` produces. It is deleted, not migrated.

### 2.5 Content-verification statement

Verified by loading and printing: A06, A07, A08, A10-A18 (source read), A15,
A19, A20, A21. **Not content-verified this pass:** A09
(`ProteinTranslocation_flat.mat`) -- all ProteinTranslocation numbers quoted
in this document come from the MATLAB source (A03) or from the OC module's
parsed attributes (A11), never from an unverified fixture claim. M26
(`karr_dna_supercoiling` protein side-effect WID set) is declared **unknown**
and is a blocking Stage-1 prerequisite (QO2), not an assumption.

---

## 3) Interaction-surface map

| ID | Producer | Consumer | Contract unit | Failure if mismatched | Evidence anchor |
|---|---|---|---|---|---|
| S1 | authoritative store `protein.compartment_counts[form][wid][compartment]` | every protein process | `(form, WID, compartment)` cell; compartment in frozen tuple `("c","d","e","m","tc","tm")` <-> MATLAB 1..6 | wrong compartment column = silent mislocalization; a WID/compartment transposition passes any shape assertion | 4.1 C1-C4; `ProteinMonomer.m:129-130` |
| S2 | authority subtree | projection Step `protein_flat_projection` | `Pi: flat[wid] = sum_k mature[wid][k]` | stale or partial projection = legacy readers see pre-transfer counts | `Engine._send_updates -> run_steps` (vivarium/core/engine.py); 4.6 |
| S3 | projection Step | `protein.counts` leaves with rejecting updater | only the Step's sentinel-tagged update is accepted | any other writer reintroduces dual authority | `store.py:733-750` `_get_updater`; 4.7 |
| S4 | Vivarium Step graph (`flow=`) | scheduler phase ordering | authority-writing Steps -> projection Step -> flat-reading Steps (M29 observability, M32/M33 request calculators) | observability computes protein mass from a stale flat view; request calculators request against stale counts | `karr_composite.py:2425-2450`; 4.6 |
| S5 | TOA fixture `substrateMonomerCompartmentIndexs` (8x2) | TOA compartment resolution | col 1 = incorporated (tc/tm), col 2 = unincorporated (c/m); `compartmentIndexs_incorporated = 1` | swapping the columns reverses the transfer direction and still conserves mass, so conservation tests pass | `TerminalOrganelleAssembly.m:124-125`; 4.2 |
| S6 | TOA fixture `localizationReactions` (10x8x2) | TOA reaction gating | plane index 1 (MATLAB) / 0 (numpy) = **incorporated** requirement; plane 2/1 = **unincorporated** | current code has these swapped (`TOA-PLANE-SWAP`, 4.4) and the oracle cannot detect it | `TerminalOrganelleAssembly.m:321-325`; 4.3, 4.4 |
| S7 | `ProteinTranslocation.monomerCompartments` | destination compartment per WID | tc->c and tm->m remap happens BEFORE `monomerIndexs_translocating` is computed | tc-targeted proteins (MG_217/218/312/317/386) become non-translocating; treating them as translocating double-moves them | `ProteinTranslocation.m:198-201` |
| S8 | L2.1 oracle `states_before/after/substrates` | replay harness | 8x2 matrix in (incorporated-row, unincorporated-row) order, C-flattened to 16 | harness overlay into the wrong compartment keys yields a green replay against a wrong state | A08; 4.5 |
| S9 | ProteinActivation branches M18/M19/M20 | the same `protein` root | active(compartment k) = mature row cell; inactive(compartment k) = inactivated row cell | leaving them separate creates a **third** authority over the same molecules | A12; D6 |
| S10 | Vivarium Process execution model | all Processes in a tick | every Process reads the SAME pre-tick snapshot; updates are applied after all `next_update` calls | expecting Karr's sequential `evalOrder` visibility inside one tick is a category error and will produce fake "same-tick" tests | `engine.run_for`/`_send_updates`; 4.6 |
| S11 | `data/schemas/per_process/terminal_organelle_assembly.toml` | TOA constructor | `observables.substrates.shape = [2,8]` and absence of `compartment_wids` | the module currently manufactures `compartment_0/1` from this absence | A15; A10 L182-269 |
| S12 | `_updater` key inside an update dict | any store leaf | per-update updater override defeats the rejecting updater at S3 | a single `{"_updater": "accumulate"}` in production reopens dual authority | `store.py:745-746`, `store.py:1647` |

### Beat-4 inversion (interaction surfaces)

```
- Which cross-surface assumption is most likely false?
    S4. The claim "Steps run after Processes, so a projection Step keeps the
    flat view exact" is only true if the projection Step is in the LAST step
    layer that touches protein state AND no Step that reads protein.counts
    runs in an earlier-or-equal layer. M29 (observability) and M32/M33
    (request calculators) are Steps that read protein.counts. The v6 flow
    block currently gives the request calculators an EMPTY dependency list
    (`karr_composite.py:2426-2435`), i.e. they are in layer 0 -- before any
    projection Step could run in the same run_steps() pass.
- What observation would expose that quickly?
    Add the projection Step with `flow[projection] = []` (layer 0) and assert
    that a request calculator sees the post-TOA aggregate: it will see the
    pre-TOA value instead, because both sit in layer 0 and deferred updates
    within a layer are applied only after the whole layer has computed
    (engine.run_steps: `deferred_updates` are applied after the inner loop).
    The design therefore REQUIRES the projection Step to be a dependency of
    every flat-reading Step (D3/D5), which is mechanically checkable by a
    topological assertion over `engine.flow`, not by a runtime value test.
```

---

## 4) Baseline facts and constraints

All facts below were produced in this session with `bin\oc-py.cmd` against the
canonical fixtures/sources. Probe scripts are listed in `STATUS_protein_state_plan.md`.

### 4.1 ProteinMonomer state shape (PROVEN)

- `counts` shape = **(4820, 6)**, dtype uint16, total = **20929** copies.
- 4820 = 10 forms x 482 monomers. Form blocks (1-based, contiguous, verified):
  `nascent 1-482`, `processedI 483-964`, `processedII 965-1446`,
  `signalSequence 1447-1928`, `folded 1929-2410`, `mature 2411-2892`,
  `inactivated 2893-3374`, `bound 3375-3856`, `misfolded 3857-4338`,
  `damaged 4339-4820`. Matches `ProteinMonomer.m:95-104` exactly.
- Nonzero cells at t0 (form, compartment-index, total, nonzero-WIDs):
  `mature (1, 16177, 296) (3, 433, 18) (4, 3770, 90) (5, 106, 5) (6, 86, 3)`;
  `inactivated (1, 288, 2)`; `bound (1, 69, 2)`. All other forms are entirely
  zero at t0.
- Per-WID KB compartment vector `compartments` takes values `{1,3,4,5,6}`;
  **2 never occurs** for protein monomers. Mature-row histogram:
  `1:358, 3:20, 4:96, 5:5, 6:3` (sums to 482).
- `compartments[signalSequenceIndexs]` is uniformly `1`, which is
  `ProteinMonomer.m:130` (`= this.compartment.cytosolIndexs`). **This pins
  cytosol = index 1 from data, not from assumption.**

Compartment axis identity (C1-C4):

| MATLAB idx | KB id | name | how proven |
|---|---|---|---|
| 1 | `c` | Cytosol | `compartments[signalSequenceIndexs] == 1` vs `ProteinMonomer.m:130` |
| 2 | `d` | DNA / chromosome | never used by monomers (probe); `docs/phase_f/PROTEIN_DECAY_PROJECTION.md:37-38` independently states the missing sixth monomer slot is the DNA compartment |
| 3 | `e` | Extracellular | `karr_protein_translocation.py:203-207` maps code 3 to extracellular; 18 mature WIDs sit there |
| 4 | `m` | Membrane | TOA `substrateMonomerCompartmentIndexs[:,2]` = 4 for the three `tm` proteins, i.e. the unincorporated partner of `tm` |
| 5 | `tc` | Terminal Organelle Cytosol | TOA `substrateMonomerCompartmentIndexs[:,1]` = 5 for MG_217/218/312/317/386 |
| 6 | `tm` | Terminal Organelle Membrane | = 6 for MG_191/192/318 |

Row 2 (`d`) is the one **inferred** entry (by elimination + alphabetical
consistency of the id set `{c,d,e,m,tc,tm}` with the observed 1,3,4,5,6
assignments). Falsifier: any fixture that shows a monomer or complex in
compartment 2 that is not chromosomal. Consequence if wrong: only the *label*
`d` is wrong; no arithmetic in this design depends on index 2 (it is always
zero for monomers), so the blast radius is cosmetic. Recorded as QO1.

### 4.2 TOA substrate matrix is a VIEW of ProteinMonomer.counts (PROVEN)

`TerminalOrganelleAssembly_flat.mat` `substrates` (8x2 uint8):

```
row  WID              inc(col1)  uninc(col2)   inc_comp  uninc_comp
 1   MG_191_MONOMER      31          0            6 (tm)    4 (m)
 2   MG_192_MONOMER      31          0            6 (tm)    4 (m)
 3   MG_217_MONOMER      17          0            5 (tc)    1 (c)
 4   MG_218_MONOMER      33          0            5 (tc)    1 (c)
 5   MG_312_MONOMER      26          0            5 (tc)    1 (c)
 6   MG_317_MONOMER      19          0            5 (tc)    1 (c)
 7   MG_318_MONOMER      24          0            6 (tm)    4 (m)
 8   MG_386_MONOMER      11          0            5 (tc)    1 (c)
```

Cross-check against `ProteinMonomer_flat.mat` mature rows (probe output):

```
MG_191_MONOMER mature_row=2604 counts=[0,0,0,0,0,31]   -> counts[2604, tm] = 31
MG_192_MONOMER mature_row=2605 counts=[0,0,0,0,0,31]
MG_217_MONOMER mature_row=2632 counts=[0,0,0,0,17,0]   -> counts[2632, tc] = 17
MG_218_MONOMER mature_row=2633 counts=[0,0,0,0,33,0]
MG_312_MONOMER mature_row=2731 counts=[0,0,0,0,26,0]
MG_317_MONOMER mature_row=2736 counts=[0,0,0,0,19,0]
MG_318_MONOMER mature_row=2737 counts=[0,0,0,0,0,24]
MG_386_MONOMER mature_row=2811 counts=[0,0,0,0,11,0]
```

Identical, cell for cell. And `substrateMonomerGlobalCompartmentIndexs`
decodes exactly as `sub2ind([4820 6], matureIndexs(g), compartment)`:
e.g. MG_191 -> `2604 + (6-1)*4820 = 26704` (fixture value `26704`), and
unincorporated `2604 + (4-1)*4820 = 17064` (fixture value `17064`).

**Conclusion (the load-bearing fact of this design): Karr's TOA has no private
state. `this.substrates` is a linear-index view of `ProteinMonomer.counts`,
refreshed each tick by `Process.m:569-571` and written back by
`Process.m:818-820`. Any OpenCell design with a TOA-owned matrix is
structurally wrong regardless of its numerics.**

### 4.3 TOA localization hierarchy, fully decoded (PROVEN)

`localizationSubstrates` (10x8) is one-hot per reaction (target protein).
`localizationReactions` (10x8x2): plane 1 = incorporated requirement, plane 2
= unincorporated requirement. `localizationThreshold = [1,0,1,1,1,1,1,1,1,1]`
and `sum(sum(lr,3),2) == threshold` returns True.

| # | reaction WID | target | requires |
|---|---|---|---|
| R1 | MG_191_TerminalOrganelleAssembly_01 | MgPa (MG_191) | HMW1 **incorporated** |
| R2 | MG_192_TerminalOrganelleAssembly_01 | P110 (MG_192) | **nothing** (threshold 0 -> always active) |
| R3 | MG_217_TerminalOrganelleAssembly_01 | P65 (MG_217) | P32 **incorporated** |
| R4 | MG_218_TerminalOrganelleAssembly_01 | HMW2 (MG_218) | HMW1 **unincorporated** |
| R5 | MG_218_TerminalOrganelleAssembly_02 | HMW2 (MG_218) | HMW1 **incorporated** |
| R6 | MG_312_TerminalOrganelleAssembly_01 | HMW1 (MG_312) | HMW2 **unincorporated** |
| R7 | MG_312_TerminalOrganelleAssembly_02 | HMW1 (MG_312) | HMW2 **incorporated** |
| R8 | MG_317_TerminalOrganelleAssembly_01 | HMW3 (MG_317) | HMW1 **incorporated** |
| R9 | MG_318_TerminalOrganelleAssembly_01 | P32 (MG_318) | HMW3 **incorporated** |
| R10 | MG_386_TerminalOrganelleAssembly_01 | P200 (MG_386) | HMW1 **incorporated** |

This reproduces the class docstring exactly ("two proteins HMW1 and HMW2
require the other either to already been incorporated ... or free in the
cytoplasm"). Dependency chain depth: `HMW1 -> HMW3 -> P32 -> P65` is **3
hops**, which is why `evolveState` needs a fixed-point loop and not a single
pass.

### 4.4 OpenCell deviations found, beyond the four baseline findings

- **`TOA-PLANE-SWAP` (new; not in the baseline).**
  `karr_terminal_organelle_assembly.py:165-171` assigns
  `required_uninc = flatnonzero(localization_reactions[ridx, :, 0] > 0)` and
  `required_inc = ...[ridx, :, 1]`. Numpy plane 0 is MATLAB plane 1, which is
  `compartmentIndexs_incorporated`. The two requirement classes are therefore
  **transposed** throughout `_reaction_is_eligible` (L321-349). The 100-tick
  oracle cannot see it (4.5). Any rewrite must re-derive the planes from
  `compartmentIndexs_incorporated`/`_unincorporated` in the fixture, not from
  a hard-coded 0/1.
- **`TOA-ACTIVITY-GATE`.** `_reaction_is_eligible` requires
  `self._is_active(activity_by_wid, target_wid)` before a protein may
  localize. Karr has no such precondition -- `evolveState` reads only
  `this.substrates`. The `protein.activity` port (M22) is a substitute for the
  missing unincorporated column.
- **`TOA-TARGET-CAP`.** `assembled[target_wid] >= target_count` caps assembly
  at `target_terminal_organelle_count` (default 1, "2 during duplication").
  Karr has no cap; it transfers every unincorporated copy.
- **`TOA-ONE-PER-TICK`.** `_substrate_deltas_from_compartment_transfer`
  (L378-401) moves exactly `+1/-1` per protein per tick, guarded by
  "only when no activity gate is on". `evolveState` moves the **entire**
  unincorporated count, and repeats until fixed point.
- **`PT-QUEUE-CONFLATION`.** `protein.unprocessed_counts` is written by
  translation (M01, nascent) and by processing-I (M02, nascent) and consumed
  by translocation (M14) as if it were the processedI cytosolic pool. Karr
  keeps `nascent` (rows 1-482) and `processedI` (rows 483-964) as distinct
  rows; translocation reads only `processedIIndexs`.
- **`PT-TO-EXCLUSION`.** `_TERMINAL_ORGANELLE_EXCLUSIONS = {"MG_191_MONOMER",
  "MG_192_MONOMER"}` (L25) removes two proteins from translocation. In Karr
  they ARE translocating (their KB compartment `tm` remaps to `m`, which is
  `~= cytosolIndexs`, so `ProteinTranslocation.m:201` includes them). MG_318
  is likewise `tm`->`m` and is NOT excluded, so the exclusion is not even
  internally consistent.
- **`PPII-UNDECLARED-WRITE`.** M08: `karr_protein_processing_ii` writes
  `protein.counts` without declaring it.

### 4.5 The L2.1 oracle cannot prove R2 (PROVEN, and this is decisive)

Direct extraction from A08 (`h5py`, `states_before`/`states_after`):

```
mutated ticks: [6, 46, 68]
tick 6 : before inc=[31,31,17,33,26,19,24,11] uninc=[0,0,0,0,1,0,0,0]
         after  inc=[31,31,17,33,27,19,24,11] uninc=[0,0,0,0,0,0,0,0]
tick 46: before inc=[...,27,...] uninc=[...,1,...]   after inc=[...,28,...] uninc=0
tick 68: before inc=[...,28,...] uninc=[...,1,...]   after inc=[...,29,...] uninc=0
```

Every mutation is **one copy of MG_312 (HMW1) moving c -> tc**, enabled by R7
(HMW2 incorporated = 33 > 0). In all three ticks the unincorporated count is
exactly 1, so "transfer the full count" and "transfer one copy" are
numerically indistinguishable. The 97 remaining ticks have
`uninc == 0` and are trivially identity.

**Constraint on the test plan:** R2 CANNOT be established by A08. It requires
constructed states (`uninc > 1`, and a >=2-iteration dependency chain) derived
from `TerminalOrganelleAssembly.m:316-337`, with the expected values computed
by hand from the MATLAB algorithm and written into the test as literals. That
is not oracle-seeding: the input is a synthetic state, and the expectation is
derived from the source algorithm, not from any Karr output artifact.

### 4.6 Vivarium execution semantics (PROVEN by reading the installed package)

`.venv-wsl/lib/python3.12/site-packages/vivarium/core/engine.py`:

- `Engine.__init__` calls `self.run_steps()` once, immediately after the store
  is built and before the first emit. **A projection Step therefore runs at
  t=0 and the flat view is correct before the first `next_update`.**
- `run_for` collects each Process's `next_update` into `self.front` and calls
  `_send_updates` once the layer completes; `_send_updates` applies all
  process updates and then calls `run_steps()`.
- `run_steps` executes `self._step_graph.get_execution_layers()` in order;
  **within a layer, all step updates are computed first and applied
  afterwards** (`deferred_updates` list). Two steps in the same layer cannot
  see each other's updates.
- Consequence A: **Processes have no same-tick visibility of each other.**
  Every Process in a tick reads the same pre-tick snapshot. Karr's sequential
  `evalOrder` mutation visibility is NOT reproduced by this chassis. This is a
  pre-existing chassis-level property, out of scope here, and any "cross-process
  same-tick visibility" test must be written as *consistency of the snapshot*
  (flat == Pi(compartment) for every reader in the tick), not as
  "process B sees process A's write".
- Consequence B: ordering that IS controllable is the Step graph. The
  projection Step must be a dependency of every flat-reading Step.

### 4.7 Updater mechanics (PROVEN)

- `updater_registry` provides `accumulate, nonnegative_accumulate, set, merge,
  dict_value, null`.
- `store.py:689-692`: `_updater` in a schema may be a registry name **or a
  callable** (`_check_schema_support_defaults` passes non-strings through).
- `store.py:733-750` `_get_updater`: a `_updater` key **inside an update dict**
  overrides the leaf's schema updater. So a rejecting updater is defeatable by
  a malicious/careless update. This cannot be closed in-framework; it must be
  closed by a static lint (6.4) plus overwrite-on-every-step repair.
- `store.py:1636-1660`: the updater is called as `updater(current_value,
  update)`; raising inside it produces a wrapped Exception naming the store
  path -- good enough for an assertable error.

### 4.8 Hard constraints inherited from project context

1. WSL is the execution environment; all probes/tests run via `bin\oc-py.cmd`
   / `bin\oc-pytest.cmd`. Expected skip count for a correct run is 5.
2. Bans in force for every downstream role: no `trace_hint`, no `states_after`
   as SUT input, no event-tick branches, no oracle reads in production, no
   test-only production mode, no independently writable aggregate mirror, no
   documentation-only waiver.
3. Tests are frozen by the Gemini role before the doer starts; the doer may
   not weaken or replace them.
4. No role pushes. `plan.md` is owned by the parent.

### Beat-4 inversion (baseline facts)

```
- Which baseline "fact" is inferred rather than proven?
    (a) Compartment index 2 == `d` (DNA). Inferred by elimination; see 4.1.
        No arithmetic depends on it.
    (b) "`protein.counts` means the mature-row compartment sum" is an
        INTERPRETATION of current OC readers, not a Karr fact -- Karr has no
        flat protein count at all. 2.4 shows three conflicting in-repo
        semantics. D6 decides it explicitly.
    (c) The claim that `karr_dna_supercoiling` (M26) does not touch the 8 TOA
        WIDs is NOT established. Declared unknown; Stage-1 prerequisite.
- What would invalidate it?
    (a) a monomer/complex fixture row in compartment 2;
    (b) a reader whose arithmetic breaks when `protein.counts` becomes the
        6-compartment mature sum (the Stage-1 test suite must include the
        adhesin gate in M28 and the mass calculation in M29 precisely because
        they are the two readers whose numbers are externally checkable);
    (c) the one-line probe in 6.9 over `karr_dna_supercoiling`'s side-effect
        WID set.
```

---

## 5) Decision ledger

### Decision D1 -- What is the authority's granularity?

```
Question: Is the authoritative unit (WID) or (form, WID, compartment)?

Options considered:
 1) (WID) only, with compartment as an attribute -- i.e. keep one count per
    protein and store a "where is it" label. This is what
    `protein.location` (M15) does today.
 2) (form, WID) -- keep the existing per-form branches
    (unprocessed/processed/unfolded/...) and add nothing.
 3) (form, WID, compartment) -- a direct Python-side transcription of
    `ProteinMonomer.counts[4820, 6]`.

Chosen option: 3.

Rationale: Karr's state IS (form, WID, compartment); `stateNames={'counts'}`
and nothing else (ProteinMonomer.m:27-40). Option 1 is provably insufficient:
`ProteinTranslocation.m:350-353` produces split populations (n copies in m,
k in c) that a per-species label cannot represent, and TOA's
`substrates(:,1)` vs `(:,2)` requires both columns of the SAME species
simultaneously (4.2). Option 2 is what exists and is exactly what the
baseline calls TOA-REDUCED-STATE / *-COMPARTMENT-PROJECTION.

Tradeoffs accepted: 28,920 leaves at full migration (482 x 10 x 6). Mitigated
by staged rollout (D7): Stage 1 materializes 480 leaves. Emission cost is
controlled by `_emit: False` on the authority and `_emit: True` only on the
derived flat view (which is what the existing emitters already consume).

Beat-4 inversion: the tensor may be materialized with the right cardinality
but a transposed axis -- 8x2 vs 2x8, or WID-major vs compartment-major --
which passes every shape assertion. Guard: the authority is keyed by *string*
WIDs and *string* compartment ids at every level, never by integer position,
so a transposition is a KeyError rather than a silent reindex. That is a
primary reason for rejecting the ndarray option in D2.

Falsifier: evidence that any Karr protein process reads or writes a protein
count through a key other than (form-row, compartment-column) of
ProteinMonomer.counts.

Operator escalation needed? no
```

### Decision D2 -- Physical state layout in the Vivarium store

```
Question: How is the (form, WID, compartment) tensor laid out as Store nodes?

Options considered:
 1) FORM-MAJOR NESTED DICT:
      protein.compartment_counts[form][wid][compartment] -> float leaf
    e.g. protein.compartment_counts.mature["MG_312_MONOMER"]["tc"]
 2) COMPOSITE-KEY FLAT:
      protein.compartment_counts["mature|MG_312_MONOMER|tc"] -> float leaf
 3) SINGLE NDARRAY LEAF:
      protein.count_matrix -> np.ndarray shape (4820, 6), `accumulate`
 4) COMPARTMENT-MAJOR NESTED DICT:
      protein.compartment_counts[form][compartment][wid] -> float leaf

Chosen option: 1 (form-major nested dict).

Rationale (evaluated against Vivarium topology/updater behavior, 4.6/4.7):
 - Topology projection. Vivarium maps a port to a path. Option 1 lets each
   process take exactly the subtree it owns: TOA -> ("protein",
   "compartment_counts", "mature"); ProteinTranslocation ->
   ("protein","compartment_counts","processed_i"); ProteinFolding gets two
   ports (folded, mature). Option 2 cannot do this at all -- every consumer
   would receive all 28,920 leaves and filter by string parsing, which also
   destroys the per-port `_emit` control.
 - Updater granularity. Options 1/2/4 give one leaf per molecule cell, so
   `accumulate` deltas from different processes merge naturally and an
   arithmetic conflict is impossible. Option 3 requires every writer to build
   a dense (4820,6) delta array per tick; a writer that builds the array with
   the wrong row offset silently corrupts another protein's row, which is
   exactly the class of bug D1's Beat-4 inversion warns about.
 - Serialization/emit. Option 3 emits a 28,920-element float array per tick
   through the emitter (serializer exists for ndarray, but the cost and the
   diff-ability are both bad). Options 1/2/4 can set `_emit: False`.
 - Divider. Cell division needs a `_divider` per molecule leaf (binomial).
   Options 1/4 allow a branch-level divider on `compartment_counts`; option 3
   would need a custom array divider.
 - Option 4 vs 1: compartment-major would make a single-compartment consumer
   cheaper (its port yields `{wid: value}` directly). But TOA needs BOTH
   columns of the same WID in the same read (4.2/4.3), ProteinTranslocation
   needs source+destination of the same WID, and the projection Pi is a
   per-WID row sum. Every hot consumer is WID-row-oriented, so WID-major
   under form wins. Also: form-major-then-WID keeps the "one subtree per
   molecule species" property that makes a per-WID divider and a per-WID
   authority audit trivial.

Tradeoffs accepted: three levels of nesting; slightly more verbose update
dicts (`{"protein": {"compartment_counts": {"mature": {wid: {"tc": +1.0}}}}}`).

Beat-4 inversion: a nested dict makes it easy to write a *partial* update that
silently creates a new key (e.g. compartment `"TC"` or `"tc "`), because
Vivarium's Store will happily establish a path. Guard: the authority module
exposes the only constructor for update dicts
(`opencell/vivarium/protein_state.py::compartment_delta(form, wid, compartment, n)`),
which validates `form in FORMS`, `wid in WIDS`, `compartment in COMPARTMENTS`
and raises otherwise; plus a Stage-1 test that asserts the set of leaf paths
after a 100-tick run is EXACTLY the set declared at construction.

Falsifier: a Vivarium limitation that prevents a Step from reading a whole
subtree (it does not: a Step port mapped to ("protein","compartment_counts")
receives the nested dict).

Operator escalation needed? no
```

### Decision D3 -- How does the flat compatibility view stay exact and unwritable?

```
Question: What mechanism produces `protein.counts[wid]` and prevents any
second writer?

Options considered:
 1) PROJECTION STEP + `set` updater: a Step recomputes flat from the
    authority and writes with "_updater": "set".
 2) PROJECTION STEP + REJECTING CALLABLE UPDATER: as (1), but the leaf's
    schema updater is a callable that raises unless the update carries a
    module-private sentinel; the Step is the only code that can produce it.
 3) `_reduce` UPDATE KEY: the Step emits {"_reduce": {"from": <authority
    path>, "initial": 0.0, "reducer": <sum fn>}} so the sum is performed by
    the Store itself over the authority subtree.
 4) DELETE `protein.counts` and force every reader onto a helper function.
 5) DERIVED-STORE / topology alias: point flat readers at the authority path.

Chosen option: 2, with the Step recomputing and OVERWRITING the full flat
map on every run (not just on change).

Rationale:
 - (1) alone makes the view exact but does nothing about a surviving
   accumulate-writer: the Step would silently repair it every tick, which is
   precisely the delayed-divergence inversion named in the INTENT block.
 - (2) closes the common path: any process that emits
   {"protein": {"counts": {wid: delta}}} raises
   `ProteinFlatProjectionWriteError` at `store.py:1636` with the offending
   store path in the message. Loud, immediate, attributable.
 - Overwrite-on-every-run is the second layer: even if a write sneaks through
   the `_updater`-override hole (4.7, S12), the flat map is restored to
   Pi(authority) before any reader runs, so the flat view cannot be a
   divergent second authority -- it can at worst be transiently wrong inside
   one step layer, which the static lint (6.4) forbids and the
   write-rejection test (6.1) detects.
 - (3) is elegant and was seriously considered: it makes exactness structural.
   Rejected because the reducer is a function object inside an update dict
   that the emitter may attempt to serialize, because `_reduce` assigns the
   reduction result to a single node (so it needs one update per WID anyway),
   and because it does not prevent a second writer -- it would still need (2).
   Complexity without closing the actual hole.
 - (4) violates the stated contract ("legacy flat protein.counts readers
   receive an exact derived compatibility view").
 - (5) is impossible: a topology alias can redirect a port to a path, but
   `protein.counts[wid]` must equal a SUM over six sibling leaves; Vivarium
   has no summing alias.

Proof that the view is exact *within* a tick (S2/S4):
  - Processes: all Processes in a tick read the same pre-tick snapshot
    (4.6 Consequence A). The projection Step ran at the end of the previous
    `_send_updates` (or at `Engine.__init__` for t=0), so the snapshot's flat
    map equals Pi(authority) of that same snapshot. Exact, by construction.
  - Steps: the Step graph is topologically ordered, and D5 requires
    flow[S] to contain the projection Step for every flat-reading Step S.
    Steps in the same layer cannot see each other (4.6), so "same layer" is
    not good enough -- it must be a strict dependency edge.
Proof that it cannot accept writes: the rejecting updater (2) + the static
lint (6.4) + the leaf-path invariant test (6.1). Documented residual: the
per-update `_updater` override (S12) is a framework escape the design cannot
remove; it is converted from "silent" to "lint failure".

Tradeoffs accepted: the projection Step writes |migrated WIDs| leaves every
tick even when nothing changed. At Stage 1 that is 8 writes/tick; at Stage 3,
482. Measured cost is a Stage-3 concern, recorded as R4.

Beat-4 inversion: the rejecting updater might be attached to the leaf but the
projection Step might be attached to a DIFFERENT path (e.g. the Step writes
("protein","counts") while readers read ("protein","counts") through a
different topology alias), so the leaf never actually receives the sentinel
and every tick raises -- or worse, the Step's port is misrouted to a fresh
subtree and the readers keep reading a stale default of 0.0 forever without
error. Guard: test 6.1c asserts the flat leaf's *identity* by mutating the
authority and reading the flat value through a READER process's port, not
through the Step's own port.

Falsifier: a demonstration that Vivarium applies process updates and step
updates in an interleaved order that lets a Process observe a mid-layer state.

Operator escalation needed? no
```

### Decision D4 -- TOA's port surface

```
Question: Which ports does the migrated TerminalOrganelleAssembly declare?

Options considered:
 1) Keep `substrates`/`enzymes`/`boundEnzymes`/`protein`/`cell` as today, and
    wire `substrates` through topology into the authority.
 2) Keep a read-only derived `substrates` 8x2 view (for the L2.1 harness) plus
    a writable `protein` port.
 3) Declare ONE port, `protein`, mapped to
    ("protein","compartment_counts","mature"); drop substrates, enzymes,
    boundEnzymes, cell, activity, and the target-count parameter; expose
    `substrate_wids` (16 labeled keys) and a pure function
    `project_substrates(states) -> np.ndarray(8,2)` for harnesses.

Chosen option: 3.

Rationale:
 - Karr's TOA `evolveState` reads ONLY `this.substrates` (4.0 quotation). It
   never reads `this.enzymes` or `this.boundEnzymes`; those exist because
   `ReactionProcess` populates them generically, and the schema TOML already
   marks them `pass_through` with 0 mutated ticks (A15). Declaring unused
   ports is the exact smell ChromosomeSegregation removed in `824cf00`
   (plan.md handoff, 2026-09-22 19:28).
 - Option 1 keeps a separate `substrates` store that would be writable -> a
   second authority. Option 2 needs a read-only mirror whose exactness must
   itself be proven and whose leaves are yet another surface to lint. Option 3
   has one surface.
 - `cell.terminal_organelle_count` and
   `cell.terminal_organelle_components_assembled` have no Karr analogue at
   all; `initializeState(~)` is empty and the only cell-level TOA concept in
   Karr is organelle duplication, which lives in Cytokinesis/replication, not
   here. They are deleted. (This removes the `target_terminal_organelle_count`
   cap, TOA-TARGET-CAP.)
 - The 16 substrate keys become biologically labeled:
   `MG_191_MONOMER@tm, ... , MG_386_MONOMER@tc` (incorporated block) then
   `MG_191_MONOMER@m, ..., MG_386_MONOMER@c` (unincorporated block), i.e. per
   the fixture's `substrateMonomerCompartmentIndexs`. This closes
   TOA-COMPARTMENT-PROJECTION.

Tradeoffs accepted: the existing L2.1 harness (A16) must be rewritten to
overlay `states_before/substrates` into the authority and to project
`states_after` back out of it. That rewrite is the Gemini role's job and is
listed in 6.6. The existing 7 unit tests (A17) that assert the reduced
semantics are deleted, not adapted.

Beat-4 inversion: the harness rewrite could "pass" by overlaying the oracle
into the authority and then projecting the SAME overlay straight back out
without the process having done anything (identity round-trip). Guard: 6.6
requires the harness to assert non-identity on ticks 6/46/68 specifically and
to fail if `next_update` returns `{}` on those ticks.

Falsifier: operator requirement that the existing L2.1 test file remain
byte-compatible (see PM sanity-check in the INTENT block).

Operator escalation needed? YES -- QO3.
```

### Decision D5 -- Scheduler placement of the projection

```
Question: Is the projection a Process, a Step, or an inline call, and where in
the flow graph does it sit?

Options considered:
 1) A Process. 2) A Step with `flow[projection] = []`.
 3) A Step that DEPENDS on every authority-writing Step, and on which every
    flat-reading Step depends.
 4) Inline at the top of every reader's `next_update`.

Chosen option: 3.

Rationale: (1) is wrong -- a Process would compute its update from the
pre-tick snapshot, so the flat view would lag one tick, which is precisely the
"stale same-tick counts" inversion. (2) is wrong for the reason derived in the
S4 inversion: the v6 flow currently puts the request calculators (M32/M33,
flat readers) in layer 0 with an empty dependency list
(`karr_composite.py:2426-2435`), and steps in the same layer cannot see each
other's updates (4.6). (4) is a dual-authority generator by construction --
each reader would compute its own view.

Concrete required edges in `build_karr_chassis_v6`'s `flow=` block:
   flow["protein_flat_projection"] = [
       ("karr_allocation_step",),                      # authority-adjacent step
       ("karr_chromosome_segregation_evolution",),     # writes protein.counts (M24)
   ]
   flow["request_calculator_protein_pathway"] += [("protein_flat_projection",)]
   flow["request_calculator_protein_translocation"] += [("protein_flat_projection",)]
   flow["request_calculator_ribasm"] += [("protein_flat_projection",)]
   flow["karr_observability_step"] += [("protein_flat_projection",)]   # v6-obs variant
Note the pre-existing tension: request calculators currently have to run
BEFORE `karr_allocation_step`. Since the projection must run after the
authority-writing steps and before the flat readers, and the flat readers are
the request calculators, the resulting graph is:
   layer 0: protein_flat_projection
   layer 1: request_calculator_*
   layer 2: karr_allocation_step
   layer 3: karr_chromosome_segregation_evolution
   layer 4: protein_flat_projection_post   <-- second instance
i.e. the projection must appear TWICE, once at the head of the step graph
(consuming the just-applied Process updates) and once after the
authority-writing Steps. Both instances are the same class with the same
sentinel; idempotence makes this safe (the Step is a pure function of the
authority). This is an explicit design output, not an implementation detail:
the doer must register `protein_flat_projection_pre` and
`protein_flat_projection_post`, and test 6.5 asserts both exist and that no
flat reader is in a layer <= a flat writer's layer without a projection
between them.

Tradeoffs accepted: two Step instances; one extra pass over |migrated WIDs|.

Beat-4 inversion: registering both instances but giving them the same store
path AND the same name, so Vivarium's step graph silently dedupes/overwrites
one; or registering the post-instance and forgetting the pre-instance so
tick-0 readers see defaults. Guard: 6.5 asserts on
`engine._step_graph.get_execution_layers()` directly -- a structural
assertion, not a value assertion.

Falsifier: a measurement showing `run_steps()` applies updates within a layer
incrementally (it does not; `deferred_updates` is applied after the layer).

Operator escalation needed? no
```

### Decision D6 -- Meaning of the flat view, and ProteinActivation's third authority

```
Question: What exactly does `protein.counts[wid]` mean after migration, given
three conflicting current meanings (2.4)?

Options considered:
 1) flat = sum over all 6 compartments of the MATURE row.
 2) flat = sum over all 6 compartments and all 10 forms (total protein).
 3) flat = mature[wid]["c"] only (cytosolic free pool).
 4) Keep ProteinActivation's meaning (active count in compartment 0) for its
    6 regulated WIDs and option 1 for everything else.

Chosen option: 1, with ProteinActivation folded into the authority (its
active matrix IS the mature row; its inactive matrix IS the inactivated row).

Rationale:
 - Every current reader of `protein.counts` asks "how many usable copies of
   this protein exist": enzyme pools (M13, M16, M27, M30, M31), the adhesin
   gate (M28), protein mass (M29), request calculators (M32-M34). In Karr all
   of those are mature-row quantities. Option 2 would add nascent/misfolded/
   damaged mass into enzyme availability -- wrong. Option 3 would break every
   membrane enzyme.
 - ProteinActivation (A12) already documents `protein.counts` as
   "the active-count authority for fixture compartment 0" and keeps
   compartments 1-5 in `activation_active_noncytosol_counts`. Under this
   design those two branches merge into `compartment_counts.mature`, and
   `activation_inactive_counts` becomes `compartment_counts.inactivated`.
   That is not a convenience: Karr's ProteinActivation moves counts between
   `matureIndexs` and `inactivatedIndexs` rows of the SAME matrix
   (ProteinMonomer.m header: "Activation inactivated->mature; Inactivation
   mature->inactivated"). Keeping them separate is what would make them a
   third authority -- the exact Beat-4 inversion named in the prompt.
 - Option 4 is rejected explicitly: a per-WID semantic exception in the flat
   view is a latent bug factory and would make the invariant
   "flat == Pi(authority)" untestable as a single property.

Consequence for ProteinActivation's own numbers: its active matrix currently
defaults from `canonical_active` cross-validated against ProteinMonomer
mature/inactivated indices (A12 L490-548), so the merge is a re-homing of the
same values, and 6.8 requires a byte-identical canonical-state assertion
before/after the merge.

Tradeoffs accepted: ProteinActivation is touched in Stage 4, after TOA and
ProteinTranslocation. Until then its 6 WIDs stay on their current branches and
are EXCLUDED from the migrated-WID set -- which is safe because no TOA WID and
no translocatable WID overlaps them (probe: `activation ... toa_hits=0` for
all three branches).

Beat-4 inversion: declaring the merge "done" while `activity` still derives
from the old branch, so the two disagree. Guard: 6.8 asserts
`protein.activity[wid] == int(any(mature[wid][k] != 0 for k in COMPARTMENTS))`
recomputed from the authority.

Falsifier: a reader proven to need the cytosol-only pool; it would force a
second derived view (`protein.cytosolic_counts`), not a second authority.

Operator escalation needed? YES -- QO5 (flat-view semantics is the single
most consequential operator-visible choice here).
```

### Decision D7 -- Migration unit: by WID set, not by form set

```
Question: What is the bounded first slice that leaves NO period with two
writable authorities?

Options considered:
 1) By FORM: migrate the mature row for all 482 WIDs first.
 2) By WID: migrate all 10 forms x 6 compartments for a small WID set first.
 3) By PROCESS: migrate TOA first, everything else later.
 4) Big bang.

Chosen option: 2, with slice 1 = the 8 terminal-organelle monomers.

Rationale:
 - The no-dual-authority invariant is per CELL (form, WID, compartment).
   Migrating by WID gives a closed cut: for a migrated WID, every form-to-form
   transition (translation -> nascent, processingI -> processedI,
   translocation c->m, processingII -> processedII + signalSequence, folding
   -> folded/mature, modification, TOA m->tm, decay) happens entirely inside
   the authority, so no boundary adapter is needed anywhere in the maturation
   chain.
 - Option 1 (by form) does NOT give a closed cut: migrating `mature` for all
   482 leaves folding's `folded -> mature` transition straddling the boundary,
   which forces a compartment-inventing adapter (where does a newly folded
   copy land?) -- i.e. a documented approximation, which the ban list forbids.
   It also immediately drags in M10, M17, M18, M23, M24, M25, M26 and M08:
   effectively a big bang.
 - Option 3 is a dual-authority generator: TOA would read the authority while
   folding/decay keep writing the flat leaf for the same molecules.
 - Slice size: 8 WIDs x 10 forms x 6 compartments = **480 leaves**. Modules
   touched: M01, M02/M03, M05/M06/M07/M08, M09/M10, M11/M12, M14, M17, M22
   (writers) + M16, M28, M29, M32, M33 (readers, no change beyond the flat
   view becoming derived). Every one of those is enumerated in 2.4 with a
   line anchor. That is a bounded, checkable slice -- not "migrate all
   consumers".
 - Why the 8 TOA WIDs specifically: they are the only WID set for which the
   compartment axis is behaviorally load-bearing TODAY (they are the only
   monomers in tc/tm, 4.1), they are TOA's entire substrate set, and MG_318
   is also a ProteinTranslocation target -- so the slice exercises both
   migration targets named in the contract.

Tradeoffs accepted: ProteinTranslocation is only partly migrated in Stage 1
(MG_318 plus, after removing PT-TO-EXCLUSION, MG_191/MG_192). The other 114
translocatable WIDs follow in Stage 2. The design says so plainly; Stage 1
alone does NOT close the ProteinTranslocation deviations, and 7) records that.

Beat-4 inversion: a "WID slice" that is enforced only by convention, so a
module keeps its 482-leaf dict and merely happens not to emit deltas for the
8. That is still dual authority (the leaves exist and are writable). Guard:
Stage 1 REMOVES the 8 WIDs from every legacy writable leaf dict, and 6.2
asserts `set(migrated_wids) & set(module.ports_schema()["protein"][branch])
== set()` for every legacy branch of every module in 2.4.

Falsifier: discovery of a writer for one of the 8 WIDs outside the enumerated
module set (M26 is the open candidate).

Operator escalation needed? no (but QO2 must be answered before Stage 1)
```

### Decision D8 -- Where does the authority live in the store tree?

```
Question: New top-level store `protein_state`, or a branch of the existing
`protein` root?

Options considered:
 1) New top-level store: ("protein_state", form, wid, compartment).
 2) Branch of the existing root: ("protein", "compartment_counts", form, wid,
    compartment).

Chosen option: 2.

Rationale: every process that will read the authority already has a `protein`
port mapped to ("protein",) in all three composite variants
(karr_composite.py L880-886, L1428-1440, L2162-2174, L2244-2247), so the
migration needs ZERO topology edits for existing processes -- they simply read
a new branch of a port they already have. A new top-level store would require
editing three topology dicts x ~15 processes, each edit an opportunity for the
"misrouted port reads defaults forever" failure. It also keeps the flat view
and its source under one root, which makes the divider story coherent.

Tradeoffs accepted: the `protein` root accumulates yet another branch name; the
legacy branch names remain until Stage 3.

Beat-4 inversion: because no topology edit is needed, a process can read the
authority by accident (it is inside a port it already holds) without declaring
those leaves in `ports_schema`, exactly as M08 does today for `counts`. Guard:
6.3 asserts that for every process, the protein leaves it WRITES are a subset
of the leaves it DECLARES (this test fails on M08 today -- it is expected to
be red until Stage 1 fixes M08, and that is a feature).

Falsifier: none identified.

Operator escalation needed? no
```

---

## 5b) Worked molecule trace (fixture -> writers -> aggregate reader)

Required by the directive ("trace at least one molecule"). Target: **one copy
of MG_312_MONOMER (HMW1) at oracle tick 6**, the real transfer in A08.

| step | actor | state touched | value |
|---|---|---|---|
| 0 | fixture `ProteinMonomer_flat.mat` | `counts[2731, tc]` (mature row of MG_312) | 26 |
| 0 | Stage-1 initial state | `protein.compartment_counts.mature["MG_312_MONOMER"]` | `{c:0, d:0, e:0, m:0, tc:26, tm:0}` |
| 0 | `protein_flat_projection_pre` at `Engine.__init__` | `protein.counts["MG_312_MONOMER"]` | `26.0` |
| 1 | maturation chain deposits one new copy in the cytosol. MG_312's KB compartment is `tc`; `ProteinTranslocation.m:199` remaps `tc -> c`, so `monomerCompartments == cytosolIndexs` and `ProteinTranslocation.m:201` classifies MG_312 as **non-translocating**. The copy therefore stays in `c` for its whole maturation. | `...mature["MG_312_MONOMER"]["c"]` | `0 -> 1` |
| 1 | projection | `protein.counts["MG_312_MONOMER"]` | `27.0` (26 in tc + 1 in c) |
| 2 (tick 6) | TOA `next_update` reads its 8x2 view from the authority via `substrateMonomerCompartmentIndexs`: `inc[HMW1] = mature[MG_312][tc] = 26`, `uninc[HMW1] = mature[MG_312][c] = 1` | -- | matches oracle `states_before` exactly |
| 3 | TOA iteration 1: `activeReactions` -- R7 requires HMW2 **incorporated**; `inc[HMW2] = mature[MG_218][tc] = 33 > 0`; threshold 1 -> `1 >= 1` active. (R6 requires HMW2 unincorporated = 0 -> inactive.) | -- | R2, R7 active |
| 4 | `localizingProteins = uninc .* (localizationSubstrates' * activeReactions)`; HMW1 has `uninc=1` and R7 targets it -> localizing. P110 (R2, always active) has `uninc=0` -> not localizing. | -- | `{HMW1}` |
| 5 | full-count transfer: `inc[HMW1] += uninc[HMW1]` (=27), `uninc[HMW1] = 0`. Loop re-tests `any(uninc)` -> all zero -> exit. | -- | 1 iteration |
| 6 | TOA emits | `{"protein": {"compartment_counts": {"mature": {"MG_312_MONOMER": {"tc": +1.0, "c": -1.0}}}}}` | -- |
| 7 | store applies (`accumulate`) | `...mature["MG_312_MONOMER"]` | `{c:0, tc:27, ...}` |
| 8 | `protein_flat_projection_post` recomputes | `protein.counts["MG_312_MONOMER"]` | `27.0` -- **unchanged from step 1** |
| 9 | flat readers (M28 adhesin gate, M29 protein mass, M32 request calculator) read `27.0`; compartment readers see the new distribution | -- | consistent |

**The falsifiable asymmetry**: steps 7 and 8 must show the compartment
distribution changing while the aggregate does NOT. An implementation that
keeps `protein.counts` writable and accumulates `+1` into it (the dual-store
failure) yields `28.0` at step 8 and fails. An implementation with a private
TOA matrix never reaches step 7 at all -- `protein.compartment_counts` is
unchanged and step 8 yields `27.0` for the wrong reason, which 6.1d catches by
asserting the compartment cells directly.

---

## 6) Expected outcomes and verification claims (the Gemini test specification)

These are the adversarial tests to be written and frozen **before** the doer
starts. Each names the file, the property, and the implementation class it
kills. Suggested file names are prescriptive; the doer may not weaken them.

### 6.1 `tests/vivarium/test_protein_state_authority.py`

```
Claim C1 (single-authority write rejection)
- If design is correct, we should observe:
    Applying {"protein": {"counts": {"MG_312_MONOMER": 1.0}}} to a built
    chassis Store raises an exception whose message contains
    "ProteinFlatProjectionWriteError" and the store path ("protein","counts",
    "MG_312_MONOMER").
- Measurement: build the v6 composite via build_karr_chassis_v6(); call
    engine.state.apply_update(...) directly with that update; pytest.raises.
- Exact value: exception raised; and after the raise, the leaf value is
    still exactly sum_k mature["MG_312_MONOMER"][k].
- Why this distinguishes: an "exact projection" implemented with a plain
    `set` updater (option D3.1) passes every consistency test and FAILS this
    one.

Claim C1b (no leaf-path drift)
- After a 100-tick v6 run, the set of store paths under
  ("protein","compartment_counts") equals exactly
  {(form,wid,comp) : form in FORMS, wid in MIGRATED_WIDS, comp in COMPARTMENTS},
  cardinality 480 at Stage 1.
- Kills: typo'd compartment keys silently creating new leaves (D2 Beat-4).

Claim C1c (flat identity through a reader's port, not the writer's)
- Mutate the authority directly (+7 copies of MG_318 in `m`); run one engine
  step; read protein.counts["MG_318_MONOMER"] through
  KarrHostInteractionProcess's port view, not through the projection Step.
- Expected: exactly old + 7.
- Kills: a misrouted projection Step writing a parallel subtree (D3 Beat-4).

Claim C1d (aggregate invariance across a TOA transfer)
- Seed mature MG_312 = {tc: 26, c: 1}; run one tick with TOA connected.
- Expected: mature MG_312 == {tc: 27, c: 0} AND
  protein.counts["MG_312_MONOMER"] == 27.0 both before and after.
- Kills: any implementation that also accumulates into the flat leaf.
```

### 6.2 `tests/vivarium/test_protein_state_no_dual_writer.py`

```
Claim C2 (legacy leaves no longer contain migrated WIDs)
- For every module in the 2.4 manifest, construct it and assert
  set(MIGRATED_WIDS) & set(schema["protein"][branch]) == set()
  for every legacy branch in
  {counts, unprocessed_counts, processed_counts, unfolded_counts,
   unmodified_counts, modified_counts, signal_sequence_counts, location}.
- Exact value: empty set for all (module, branch) pairs; the test enumerates
  the pairs from the manifest so a NEW module with a protein port fails the
  test until it is classified.
- Kills: D7's Beat-4 inversion (slice enforced by convention only).

Claim C2b (declared-writes-only)
- Static AST scan over opencell/vivarium/*.py: for each Process class, the set
  of protein leaf paths written in next_update/_build_update must be a subset
  of the leaf paths declared in ports_schema.
- Expected: PASS. NOTE: this test is RED on `karr_protein_processing_ii`
  today (M08 writes an undeclared `counts` branch). That is intended -- the
  test writer must assert the fixed state, and the doer must fix M08.
```

### 6.3 `tests/vivarium/test_toa_karr_transfer.py` (the core R2 tests)

```
Claim C3 (exact 8x2 fixture transfer, oracle ticks)
- Seed the authority from ProteinMonomer_flat mature rows; overlay the A08
  states_before 8x2 for ticks 6/46/68 into the authority via the documented
  compartment map; run TOA.next_update; project back to 8x2.
- Expected: exact equality with states_after; AND next_update returns a
  NON-EMPTY update on each of those three ticks; AND returns {} on a tick
  with uninc all-zero.
- Threshold: exact integer equality (no tolerance).

Claim C4 (full-count transfer, n > 1)   <-- A08 CANNOT prove this
- Constructed state: mature MG_312 = {c: 5, tc: 26}; mature MG_218 = {tc: 33}.
- Expected after ONE next_update: mature MG_312 == {c: 0, tc: 31}.
- Derivation: TerminalOrganelleAssembly.m:333-336 assigns
  inc += uninc; uninc = 0 (not inc += 1).
- Kills: TOA-ONE-PER-TICK (`_substrate_deltas_from_compartment_transfer`
  L378-401), which would yield {c: 4, tc: 27}.

Claim C5 (fixed-point hierarchy depth >= 3 in ONE tick)
- Constructed state (all other cells zero):
    mature MG_312 (HMW1) = {tc: 1}          # incorporated seed
    mature MG_317 (HMW3) = {c: 2}           # uninc; needs HMW1 incorporated (R8)
    mature MG_318 (P32)  = {m: 4}           # uninc; needs HMW3 incorporated (R9)
    mature MG_217 (P65)  = {c: 3}           # uninc; needs P32 incorporated (R3)
- Expected after ONE next_update:
    MG_317 -> {tc: 2}, MG_318 -> {tm: 4}, MG_217 -> {tc: 3}, MG_312 -> {tc: 1}
- Derivation: the `while` loop at L320 re-evaluates activeReactions after each
  full-count transfer; iteration 1 localizes HMW3, iteration 2 localizes P32,
  iteration 3 localizes P65, iteration 4 finds no uninc and exits.
- Kills: any single-pass implementation (would leave P32 and P65 unmoved).

Claim C6 (plane orientation / HMW1-HMW2 mutual rule)
- Constructed state A: mature MG_312 = {c: 2}, mature MG_218 = {c: 3},
  everything else zero. R4 (HMW2 needs HMW1 UNINCORPORATED) and R6 (HMW1 needs
  HMW2 UNINCORPORATED) are both active on the same snapshot.
  Expected: BOTH localize in iteration 1 -> MG_312 {tc: 2}, MG_218 {tc: 3}.
- Constructed state B: mature MG_317 (HMW3) = {c: 2}, mature MG_312 = {c: 1},
  everything else zero. R8 requires HMW1 **incorporated**; HMW1 is
  unincorporated, so HMW3 must NOT move in iteration 1. HMW1 itself cannot
  move either (R6/R7 need HMW2, which is absent).
  Expected: NOTHING moves; next_update returns {}.
- Kills: TOA-PLANE-SWAP (4.4). With the planes transposed, state B moves HMW3.

Claim C7 (threshold-0 reaction)
- Constructed state: mature MG_192 (P110) = {m: 7}, all else zero.
- Expected: MG_192 -> {tm: 7} in one tick (R2 threshold 0 -> always active).
- Kills: an implementation that treats "no requirements" as "never eligible".

Claim C8 (conservation)
- For every constructed state above and for a 100-tick chassis run:
  sum over (form, wid, compartment) of the authority is invariant across
  TOA's update, and no cell is ever negative or non-integral.

Claim C9 (no oracle input)
- Static: `grep -n "trace_hint\|states_after\|states_before" \
   opencell/vivarium/karr_terminal_organelle_assembly.py` returns nothing.
- Runtime: constructing the process with a state containing a `trace_hint`
  key changes nothing about the returned update.
- Kills: TOA-TRACE-HINT.
```

### 6.4 `tests/vivarium/test_protein_state_static_lint.py`

```
Claim C10 (no `_updater` escape)
- AST scan: no production module under opencell/ may emit a dict containing
  the key "_updater" anywhere inside a value routed to the "protein" port.
- Rationale: store.py:745-746 lets a per-update `_updater` override the
  rejecting updater (S12). This is the only way to defeat D3 and it must be a
  lint failure.

Claim C11 (compartment id discipline)
- Every compartment key string appearing in production source under a
  compartment_counts update literal is a member of
  ("c","d","e","m","tc","tm"). No `compartment_0`-style generic label survives
  in TOA.
- Kills: TOA-COMPARTMENT-PROJECTION.
```

### 6.5 `tests/vivarium/test_protein_projection_scheduling.py`

```
Claim C12 (step-graph ordering is structurally correct)
- Build the v6 engine; read engine._step_graph.get_execution_layers().
- Assert: a projection instance exists in the FIRST layer; a projection
  instance exists in a layer strictly greater than the layer of every Step
  classified AUTH-W in 2.4; and every Step classified DERIVED-R sits in a
  layer strictly greater than some projection instance.
- Kills: the S4 inversion (projection in the same layer as its readers) and
  the "projection is a Process" mistake (a Process would not appear here).

Claim C13 (t=0 correctness)
- Immediately after build_karr_chassis_v6() and BEFORE any update(), assert
  protein.counts[wid] == sum_k mature[wid][k] for all migrated WIDs.
- Justification: Engine.__init__ calls run_steps() (4.6).
```

### 6.6 `tests/vivarium/test_karr_terminal_organelle_assembly_l2_replay.py` (rewritten)

```
Claim C14 (L2.1 replay through the authority)
- Overlay A08 states_before/substrates into
  protein.compartment_counts.mature using substrateMonomerCompartmentIndexs;
  run next_update; project the 8x2 back out; compare to states_after.
- Assert additionally: on ticks 6/46/68 the returned update is non-empty and
  the projected matrix differs from the overlaid one (anti-identity guard,
  D4 Beat-4).
- `enzymes`/`boundEnzymes` are pass-through: rebuilt from states_before, not
  read from the process (consistent with A15's `pass_through` declaration).
```

### 6.7 `tests/vivarium/test_protein_translocation_compartments.py` (Stage 2)

```
Claim C15 (translocation moves authoritative counts)
- Seed processed_i["MG_015_MONOMER"] = {c: 4} (or any integral-membrane WID)
  with sufficient allocated ATP/H2O/enzymes; run next_update.
- Expected: processed_i[wid]["c"] decreases by n and processed_i[wid]["m"]
  increases by the same n; no `protein.location` key exists anywhere;
  total across compartments is conserved.
- Kills: PT's current `location` string + `unprocessed_counts` decrement
  (M14/M15), which destroys copies.

Claim C16 (destination map)
- For every translocating WID, destination compartment ==
  {tc: "c", tm: "m"}.get(kb_compartment, kb_compartment), per
  ProteinTranslocation.m:198-200, and MG_191/MG_192 are NOT excluded.
- Kills: PT-TO-EXCLUSION.

Claim C17 (form discipline)
- Translocation reads and writes ONLY the processed_i form; nascent is
  untouched.
- Kills: PT-QUEUE-CONFLATION.
```

### 6.8 `tests/vivarium/test_protein_activation_merge.py` (Stage 4)

```
Claim C18: ProteinActivation's canonical_state(), recomputed from the merged
authority, is byte-identical to the pre-merge canonical_state() for all 6
regulated proteins x 6 compartments (active and inactive).
Claim C19: protein.activity[wid] == int(any(mature[wid][k] != 0)) recomputed
from the authority; the activation_* branches no longer exist.
```

### 6.9 Regeneratable probes the tests should own (not throwaway)

```
- probe A: AST protein-port manifest regenerator; output compared against a
  checked-in golden manifest (the 2.4 table as TSV). Any new/changed protein
  port fails CI until the manifest is updated. This is how the inventory stays
  true over time.
- probe B: `karr_dna_supercoiling` protein side-effect WID set (resolves M26 /
  QO2): construct the process, drive it to emit side effects, collect the WIDs
  written under protein.counts, intersect with MIGRATED_WIDS.
```

### Beat-4 inversion (verification claims)

```
- How could these claims pass while the design is still wrong?
  (a) Every constructed-state test (C4-C7) could be written against the NEW
      implementation's behavior instead of against the MATLAB algorithm. The
      role separation is the structural guard: Gemini writes them from the
      quoted MATLAB in 0.2 before the doer's code exists, and the expected
      values in C4-C7 are already written out in this document so they can be
      diffed against the committed test.
  (b) C1 (write rejection) could pass because the rejecting updater is
      attached but the projection never runs, so the flat view is frozen at
      its default. C13 + C1c close that.
  (c) C3 could pass while C4-C7 are silently skipped (e.g. an import error in
      a parametrized fixture). Guard: the suite must assert its own test count
      and the repo-wide expected skip count stays 5 (4.8 constraint 1).
- Additional guardrail to close that hole:
  A "mutation canary" test: monkeypatch the transfer to `inc += 1` instead of
  `inc += uninc` inside a copy of the algorithm and assert that C4 and C5
  FAIL. This proves the suite has the discriminating power claimed, rather
  than asserting it. (Implemented as a self-test over a deliberately broken
  local subclass -- no production toggle, no test-only production mode.)
```

---

## 7) Open questions for operator

```
QO1. Is compartment index 2 == `d` (DNA/chromosome)?
- Why unresolved: no monomer or complex fixture row occupies index 2, so it
  cannot be read off the data; it is derived by elimination plus the
  alphabetical consistency of {c,d,e,m,tc,tm} with the five proven indices,
  corroborated by docs/phase_f/PROTEIN_DECAY_PROJECTION.md:37-38.
- Options: 1) accept `d`; 2) name it `unknown_2` until a chromosome-state
  fixture proves it.
- Recommended default: accept `d`. No arithmetic depends on it.
- Risk if wrong: a cosmetic label in emitted data; zero numeric impact
  (the column is identically zero for monomers).

QO2. Does `karr_dna_supercoiling` write protein.counts for any of the 8
     terminal-organelle WIDs (manifest row M26)?
- Why unresolved: the module builds its protein port dynamically, so the AST
  scan found the write site (L1395-1402) but not the WID set.
- Options: 1) run probe B (6.9) before Stage 1 and extend the Stage-1 module
  list if it intersects; 2) assume no intersection.
- Recommended default: (1). This is a BLOCKING prerequisite, not an option.
- Risk if wrong: a surviving second writer for a migrated WID -- the exact
  INTENT Beat-4 inversion.

QO3. May the existing L2.1 TOA replay test (A16) be rewritten to overlay the
     oracle into the authoritative store, and may TOA drop its unused
     `enzymes`/`boundEnzymes` ports?
- Why unresolved: the TOA L2.1 verdict is currently GENUINE; rewriting its
  harness touches the artifact that produced that verdict.
- Options: 1) rewrite the harness (Decision D4, chosen); 2) keep a read-only
  derived 8x2 `substrates` view so the current harness runs unchanged.
- Recommended default: (1), because (2) adds a second protein-count surface
  whose exactness must itself be proven, and the schema TOML already declares
  enzymes/boundEnzymes as pass-through with 0 mutated ticks.
- Risk if wrong: a rewritten harness could be weaker than the original; C14's
  anti-identity guard is the mitigation.

QO4. Are there protein-count consumers outside `opencell/vivarium` --
     specifically `opencell/vivarium/persist.py`, division/divider logic, or
     analysis scripts that assume `protein.counts` is writable?
- Why unresolved: the AST scan covers ports and subscripts, not
  string-keyed dict access through indirection, and `_divider` specs were not
  enumerated.
- Options: 1) add a divider-and-persistence sweep to Stage 1's prerequisites;
  2) defer to Stage 3.
- Recommended default: (1) for `persist.py` and any `_divider` on protein
  leaves; (2) for analysis scripts (read-only).
- Risk if wrong: cell division splits the flat view and the authority
  independently, producing daughters whose flat view is not Pi(authority).

QO5. Confirm the flat-view semantics chosen in D6:
     `protein.counts[wid] = sum over 6 compartments of the MATURE row`.
- Why unresolved: the repo currently holds three incompatible meanings (2.4);
  choosing one changes observable numbers for ProteinActivation's 6 regulated
  proteins (from "active in compartment 0" to "mature total").
- Options: 1) mature-row compartment sum (chosen); 2) all-form all-compartment
  total; 3) per-WID exceptions.
- Recommended default: (1).
- Risk if wrong: every enzyme-availability reader (M13/M16/M27/M30/M31) and
  the L2.4 conservation gate shift by the amount of non-mature protein mass.

QO6. Is a Stage-1 scope of 8 WIDs x 10 forms x 6 compartments (480 leaves,
     ~13 modules touched) acceptable as a single reviewable commit, or should
     Stage 1 be split further (e.g. 1a = store + projection + lint with ZERO
     behavior change; 1b = TOA + writer re-homing)?
- Why unresolved: it is a reviewability judgement, not a technical one.
- Options: 1) one commit; 2) split 1a/1b.
- Recommended default: (2). Stage 1a introduces the authority, the projection
  Steps and the lint while the authority is still EMPTY (no migrated WIDs), so
  it is provably behavior-neutral; Stage 1b flips the 8 WIDs.
- Risk if wrong: a large commit that the reviewer cannot audit line by line.

QO7. Should ProteinDecay (currently L2.1-blocked for exactly this reason,
     A20) be explicitly enrolled as the Stage-3 beneficiary, or left out of
     this design's scope entirely?
- Why unresolved: A20 documents the same root cause and proposes the opposite
  (lossy) remedy; leaving it unaddressed risks that stale doc being used later
  as the spec.
- Options: 1) note in this design that A20's collapse-projection remedy is
  superseded, and leave the ProteinDecay work to a later design;
  2) bring ProteinDecay into Stage 3 now.
- Recommended default: (1). This document supersedes A20's *direction* but
  does not claim to close ProteinDecay (see 7 / overclaim guard in 8).
- Risk if wrong: duplicated or contradictory ProteinDecay work later.
```

---

## 8) Which pre-L2.5 blockers this closes -- and which it does NOT

### Closes (upon completion of the stated stage)

| finding | stage | why it is closed |
|---|---|---|
| `TOA-REDUCED-STATE` | 1 | The 8x2 unincorporated/incorporated matrix becomes a real view of the authoritative compartment state; `evolveState` L316-337 is transcribed verbatim (fixed point + full-count); the activity gate, the assembled counters and the target cap are deleted. Proven by C3-C8. |
| `TOA-PRODUCTION-TOPOLOGY` | 1 | The substrate compartment state is available on the `protein` port the composite already wires (D8); no topology edit needed and no unmapped ports remain. Proven by C3 running inside the built v6 composite, and by C12. |
| `TOA-TRACE-HINT` | 1 | `_substrate_deltas_from_trace_hint` and the `trace_hint` read are deleted. Proven by C9 (static + runtime). |
| `TOA-COMPARTMENT-PROJECTION` | 1 | `compartment_0/compartment_1` are replaced by the biological ids resolved from `substrateMonomerCompartmentIndexs` (`tm/m`, `tc/c` per protein). Proven by C11 and by C5/C7, which assert transfers into the correct named compartment. |
| `TOA-PLANE-SWAP` (new, 4.4) | 1 | Requirement planes are derived from `compartmentIndexs_incorporated/_unincorporated` rather than hard-coded. Proven by C6 state B. |
| `PPII-UNDECLARED-WRITE` (new, M08) | 1 | Fixed as a side effect of re-homing processing-II's writes; enforced by C2b. |
| `PT-TO-EXCLUSION`, `PT-QUEUE-CONFLATION`, and ProteinTranslocation's compartment projection | 2 | Proven by C15-C17. |
| ProteinActivation's third authority (M18-M20) | 4 | Proven by C18-C19. |

### Explicitly does NOT close (no overclaiming)

1. **ProteinDecay.** A20 shows ProteinDecay is L2.1-blocked because it needs
   the full `4820 x 6` surface *and* form-specific decay kernels. This design
   supplies the state surface (at Stage 3) but implements none of ProteinDecay's
   algorithm. `karr_protein_decay_light` remains a "light" port. **No claim.**
2. **ChromosomeCondensation** (`CC-COMPARTMENT-PROJECTION`, baseline L50-56)
   and any other `*-COMPARTMENT-PROJECTION` finding on non-protein state
   (metabolites, RNA, complexes). This design touches protein monomers only.
3. **ProteinFolding / ProteinProcessingI / ProteinProcessingII /
   ProteinModification algorithmic fidelity.** Stage 1 re-homes *where they
   write*; it does not audit *what they compute*. Their own baseline findings
   are untouched. The Stage-1 doer must read their `.m` sources to place the
   writes in the right form rows and compartments (9.2 prerequisite), but that
   is a plumbing correctness requirement, not an algorithmic audit.
4. **TOA's L2.1 verdict.** TOA is already `behavior_verdict: GENUINE`; this
   work targets `eligibility: BLOCKED_CODE_DEVIATION`. Closing the four (five)
   findings makes TOA *eligible*; it does not by itself move any gate verdict,
   and the eligible count (3/28 today) should be re-derived by the baseline
   tooling, not asserted.
5. **Karr's sequential `evalOrder` intra-tick visibility.** Vivarium runs all
   Processes against one pre-tick snapshot (4.6). That is a chassis-wide
   deviation this design neither creates nor fixes. It is named here so that
   no downstream role writes a test claiming same-tick cross-process
   visibility exists.
6. **L2.4 conservation numbers.** Changing the meaning of `protein.counts`
   (D6/QO5) may shift measured protein mass. The doer must re-run L2.4 at four
   seeds and report the delta; this design does not predict it.

---

## 9) Migration and rollout path

### 9.1 Strategy

In-place, **WID-sliced**, with an always-empty-or-complete authority: at every
commit boundary, a WID is either fully on the authority (and absent from every
legacy writable leaf) or fully on the legacy branches. There is never a WID
with two writable homes. New code is additive first (Stage 1a) and behavior
flips second (Stage 1b).

### 9.2 Stage 1a -- authority + projection + lint, zero migrated WIDs

Prerequisite (blocking): answer QO2 via probe B, and QO4 for `persist.py` /
dividers.

New files:
- `opencell/vivarium/protein_state.py` -- `FORMS` (10, ordered as
  ProteinMonomer.m:95-104), `COMPARTMENTS = ("c","d","e","m","tc","tm")`,
  `MIGRATED_WIDS` (empty at 1a), the schema builder, the
  `compartment_delta(form, wid, compartment, n)` constructor, the
  `ProteinFlatProjectionWriteError`, the rejecting updater callable, and the
  `Pi` projection function.
- `opencell/vivarium/protein_flat_projection_step.py` -- the Step class.

Edited files:
- `opencell/vivarium/karr_composite.py` -- register
  `protein_flat_projection_pre` / `_post` in `steps=` and add the `flow=`
  edges listed in D5, in **all three** composite builders that wire a
  `protein` port (topology blocks at L880-886, L1428-1440, L2162-2247).

Behavior-neutral because `MIGRATED_WIDS` is empty: the projection writes
nothing, the rejecting updater is attached to nothing.

Exit criteria: C12, C13 pass; full scoped suite unchanged; L2.4 unchanged.

### 9.3 Stage 1b -- flip the 8 terminal-organelle WIDs

Files (exact list; every one is anchored in the 2.4 manifest):
1. `opencell/vivarium/protein_state.py` -- `MIGRATED_WIDS` = the 8 TOA WIDs;
   initial values seeded from `ProteinMonomer_flat.mat` mature rows (4.2).
2. `opencell/vivarium/karr_terminal_organelle_assembly.py` -- **rewrite**
   (D4): one `protein` port, MATLAB-verbatim `evolveState`, planes derived
   from the fixture, biological compartment ids, delete `_load_substrate_projection_schema`,
   `_substrate_deltas_from_trace_hint`, `_substrate_deltas_from_compartment_transfer`,
   `_reaction_is_eligible`'s activity gate and target cap, and the `cell` port.
3. `opencell/vivarium/karr_protein_translocation.py` -- remove the 8 WIDs from
   `unprocessed_counts`/`location`/`counts` leaf dicts; route MG_318 (and,
   after removing `_TERMINAL_ORGANELLE_EXCLUSIONS`, MG_191/MG_192) through the
   authority's `processed_i` rows. (This is the Stage-2 mechanism applied to 3
   WIDs; Stage 2 generalizes it.)
4. `opencell/vivarium/karr_translation_v3.py` -- M01: 8 WIDs out of
   `unprocessed_counts`, into `compartment_counts.nascent[wid]["c"]`.
5. `opencell/vivarium/karr_protein_processing_i.py` -- M02/M03/M04.
6. `opencell/vivarium/karr_protein_processing_ii.py` -- M05/M06/M07 **and M08**
   (delete the undeclared `counts` write).
7. `opencell/vivarium/karr_protein_folding.py` -- M09/M10.
8. `opencell/vivarium/karr_protein_modification.py` -- M11/M12 (MG_217, MG_317).
9. `opencell/vivarium/karr_protein_decay_light.py` -- M17.
10. `opencell/vivarium/karr_dna_supercoiling.py` -- **only if** probe B shows
    an intersection (QO2).
11. `opencell/vivarium/karr_composite.py` -- initial-state seeding for the
    authority; no topology change (D8).
12. `opencell/vivarium/karr_host_interaction.py`, `karr_observability_step.py`,
    `karr_request_calculators.py` -- **no code change expected**; they keep
    reading `protein.counts`, which is now derived. Listed because they are the
    compatibility consumers whose numbers must be re-verified (C1c, C13).

Prerequisite reading for the doer (per 2.3 inversion (b)): the `.m` sources for
ProteinProcessingI, ProteinProcessingII, ProteinFolding and ProteinModification,
to place each re-homed write in the correct form row and compartment column.
This is mandatory, not optional -- a re-homed write that lands in the wrong form
row is invisible to every test in 6) except C8.

Exit criteria: all of 6.1-6.6 green; L2.4 four seeds x 100 ticks; L1b 115/115
and 28/28; baseline integrity check re-run; Ruff clean.

### 9.4 Stage 2 -- ProteinTranslocation and the translocatable set

`MIGRATED_WIDS` += the 117 translocatable WIDs (+ the 2 un-excluded).
Files: `karr_protein_translocation.py` (full rewrite of `next_update`'s
bookkeeping; the randperm-over-copies loop and the allocator contract are
UNCHANGED), plus the same re-homing edits in M01/M02/M03/M05-M12/M17 for the
newly migrated WIDs. `protein.location` is deleted repo-wide (M15, M32, M33).
Exit criteria: 6.7 green; A09 content verified (2.5).

### 9.5 Stage 3 -- remaining WIDs and retirement of legacy branches

`MIGRATED_WIDS` = all 482. The legacy branches
(`unprocessed_counts`/`processed_counts`/`unfolded_counts`/`unmodified_counts`/
`modified_counts`/`signal_sequence_counts`) become derived form views produced
by the projection Step alongside `protein.counts`, or are deleted where no
reader remains. Authority size: 28,920 leaves.

### 9.6 Stage 4 -- fold ProteinActivation in

Per D6: `activation_active_noncytosol_counts` -> `compartment_counts.mature`;
`activation_inactive_counts` -> `compartment_counts.inactivated`;
`protein.activity` becomes a derived projection of the authority.
Exit criteria: 6.8 green.

### 9.7 Backout and partial-migration failure rules

1. **One stage = one commit.** Backout of any stage is `git revert <sha>` of
   that single commit. No stage depends on a later stage's code.
2. **Backout triggers (any one is sufficient):**
   - L2.4 conservation regresses at any of the four seeds;
   - the pre-L2.5 baseline integrity check reports anything other than
     `INTEGRITY_OK`, or the eligible count decreases;
   - the repo-wide pytest skip count is anything other than 5 (4.8);
   - any test in 6.1-6.5 is red after the doer declares done;
   - the doer cannot satisfy a frozen test without editing it.
3. **Partial-migration detector (must be implemented in Stage 1a, not left to
   review):** `protein_state.py` asserts at import/construction that
   `MIGRATED_WIDS` is identical across (a) the authority schema builder,
   (b) the rejecting-updater attachment set, (c) the projection Step's key
   set, and (d) the exclusion sets applied to every legacy branch in the 2.4
   manifest. If any two disagree, construction raises
   `ProteinStateMigrationInconsistent` naming the differing sets. A half-applied
   stage therefore fails loudly at build time, not silently at tick 4000.
4. **No compatibility period with two writable authorities.** If a stage
   cannot be completed, it is reverted; it is NOT left half-applied behind a
   flag. There is no migration flag, no dual-write mode, and no
   `use_compartment_state` parameter. (`use_protein_counts_compat` in M04 is
   an existing example of the pattern being banned here and must be removed,
   not extended.)
5. **Frozen tests.** The doer may not edit any file under `tests/` that the
   Gemini role committed. If a frozen test is believed wrong, the doer stops
   and hands back with the disagreement stated.

### Beat-4 inversion (migration)

```
- How migration could strand partially-updated code:
    A module's legacy leaf dict is trimmed (WIDs removed) but its update
    builder still emits those WIDs, so the deltas are applied to leaves that
    no longer exist in that process's schema -- and Vivarium's Store will
    happily CREATE them (D8 Beat-4), resurrecting the second authority under a
    path nobody declared.
- Checkpoint or guard to detect that state:
    C1b (exact leaf-path set after a 100-tick run) plus C2b
    (declared-writes-only) plus the item-3 build-time detector. C1b is the
    one that catches path resurrection specifically, because it compares the
    realized store tree against the declared set rather than checking values.
```

---

## 10) Risks and residual unknowns

```
R1. A surviving writer for a migrated WID outside the enumerated module set.
- Likelihood: medium (M26 is a known unknown; dynamic port builders defeat
  static scans).
- Impact: high -- reintroduces the exact dual authority the work exists to
  remove; masked by the projection's repair behavior.
- Detection: C1 (rejection raises), C2/C2b, C1b, probe B.
- Mitigation: rejecting updater raises rather than repairs on the common path;
  QO2 is a blocking prerequisite.
- Owner: Stage-1 doer.

R2. Re-homed writes land in the wrong form row.
- Likelihood: medium-high -- OC's branch names do not map 1:1 onto Karr's form
  blocks (`unprocessed_counts` is used for BOTH nascent and the translocation
  queue, 4.4 PT-QUEUE-CONFLATION; `counts` is used for mature AND, by M08, for
  unprocessed).
- Impact: high and quiet -- conservation still holds, so C8 passes.
- Detection: only by reading the four `.m` sources and by per-form assertions.
- Mitigation: 9.3 makes that reading a blocking prerequisite; the Gemini role
  should add per-form seed/assert tests for at least folding and processing-II.
- Owner: Stage-1 doer + reviewer.

R3. The flat-view semantics change (D6/QO5) shifts externally-visible numbers.
- Likelihood: high (it is a deliberate semantic change for ProteinActivation's
  6 WIDs and potentially for any reader that was seeing a partial pool).
- Impact: medium -- L2.4 conservation numbers, protein mass in observability,
  the host adhesion gate.
- Detection: re-run L2.4 at four seeds and diff; C1c/C13.
- Mitigation: QO5 escalation before Stage 1b; report the delta rather than
  silently absorb it.
- Owner: operator (decision) + doer (measurement).

R4. Store size and emit cost at Stage 3 (28,920 leaves).
- Likelihood: medium.
- Impact: medium -- tick wall time and emitter volume in the 32,400-tick run.
- Detection: time a 100-tick v6 run before/after Stage 3.
- Mitigation: `_emit: False` on the authority; only the derived flat view
  emits. If still too slow, revisit D2 option 3 for Stage 3 ONLY, behind a
  fresh design decision, never as an ad-hoc change.
- Owner: Stage-3 doer.

R5. Cell division / dividers split the flat view and the authority
    inconsistently.
- Likelihood: unknown (QO4 unresolved).
- Impact: high if the chassis divides within a validated run.
- Detection: a division test asserting flat == Pi(authority) in both daughters.
- Mitigation: put a `_divider` on the authority subtree and NONE on the flat
  leaves (the projection regenerates them post-division, since
  Engine re-runs steps).
- Owner: Stage-1 doer (investigation), Stage-3 doer (implementation).

R6. The rewritten L2.1 harness is weaker than the one it replaces.
- Likelihood: medium.
- Impact: medium -- a GENUINE verdict could become unearned.
- Detection: C14's anti-identity guard; reviewer diff of old vs new harness.
- Mitigation: QO3; keep the same three observables and the same tick loop.
- Owner: Gemini test writer + reviewer.

R7. `_updater` override escape (S12) is used by future code.
- Likelihood: low now, rises over time.
- Impact: high (silently defeats single authority).
- Detection: C10 static lint.
- Mitigation: lint runs in CI with the rest of the suite.
- Owner: whoever owns CI.

R8. Scope creep from Stage 1 into Stages 2-4 inside one PR.
- Likelihood: medium-high; the maturation chain invites "while I'm here".
- Impact: unreviewable diff; the failure mode the prompt explicitly names.
- Detection: the Stage-1 file list in 9.3 is exhaustive; any file outside it
  in the diff is a review failure.
- Mitigation: reviewer checks the diff file list against 9.3 before reading
  any code.
- Owner: GPT reviewer.
```

---

## 11) Operator review checklist

1. Does the inventory (2.4) list concrete modules with line anchors, and does
   it include at least one prior failed attempt (A20, `PROTEIN_DECAY_PROJECTION.md`)
   and at least one primary source (A01-A05)?
2. Are the cross-surfaces (3) explicit and testable -- in particular S4
   (scheduler phase) and S6 (plane orientation), the two that can pass a naive
   test suite while being wrong?
3. Does every decision card (5) carry options, rationale, a Beat-4 inversion
   and a falsifier? D6 and D7 are the two that change the shape of the work;
   read those first.
4. Are operator decisions (7) separated from implementer assumptions? QO2
   (supercoiling writers) and QO5 (flat-view semantics) are blocking; the rest
   have recommended defaults.
5. Is the scope boundary tight? Check 9.3's file list against 8)'s
   "does NOT close" list: does anything in the file list imply a claim the
   design disclaims?
6. Does 6) contain at least one test that fails a *dual-store* implementation
   (C1, C1d) and at least one that fails a *single-pass* implementation
   (C4, C5)? Those are the two inversions this whole design exists to prevent.
7. Is the "no period with two writable authorities" rule enforced
   mechanically (9.7 item 3, build-time detector) rather than by convention?

---

## Scope boundary

```
In scope:
1. The authoritative compartment-resolved ProteinMonomer state, its schema,
   its update constructor, and its migration-consistency detector.
2. The derived flat `protein.counts` view, its rejecting updater, and its two
   projection Step instances plus their flow edges.
3. TerminalOrganelleAssembly: full rewrite onto the authority (Stage 1).
4. ProteinTranslocation: compartment moves on the authority (Stage 1 for the
   3 TO-membrane WIDs; Stage 2 for the rest).
5. Re-homing the writes of the protein maturation chain for migrated WIDs.
6. Folding ProteinActivation's compartment branches into the authority
   (Stage 4).
7. The adversarial test specification in 6).

Out of scope:
1. ProteinDecay's algorithm (state surface only; see 8).
2. Non-protein compartment projections (ChromosomeCondensation, metabolites,
   RNA, complexes).
3. Algorithmic fidelity audits of folding/processing/modification.
4. Karr's sequential evalOrder semantics in the Vivarium chassis.
5. Any change to the allocator, the request calculators' arithmetic, or the
   RNG discipline.
6. Any change to plan.md, any push, any gate-verdict claim.

Deferred follow-ups:
1. Re-derive the pre-L2.5 eligible count and source digest after each stage
   (parent orchestrator owns this).
2. Revisit docs/phase_f/PROTEIN_DECAY_PROJECTION.md once Stage 3 lands; its
   collapse-projection direction is superseded (QO7).
3. Performance measurement of the 28,920-leaf store (R4).
```

```
Beat-4 inversion (scope):
- Most likely scope-creep vector: "while re-homing folding's write, also fix
  folding's algorithm" -- because the doer must read ProteinFolding.m anyway
  (9.3 prerequisite) and will see deviations.
- How this doc prevents it: 8) states explicitly that no algorithmic claim is
  made for those processes; 9.3 gives an exhaustive file list; R8 makes "any
  file outside 9.3" a reviewer stop condition.
```

---

## Acceptance bar self-audit

| # | DESIGN_TEMPLATE acceptance item | where | status |
|---|---|---|---|
| 1 | Contract stated as a system property | 1) "Done =" | met |
| 2 | Inventory manifest machine-checkable, >= 8 entries | 2.1-2.2 (22 artifacts), 2.4 (36 manifest rows) | met |
| 3 | Interaction-surface map names cross-boundaries | 3) S1-S12 | met |
| 4 | Every major decision has options/chosen/rationale/Beat-4 | 5) D1-D8 | met (8 cards, >= 5 required for an architectural fork) |
| 5 | Falsifiable expected outcomes before implementation | 6) C1-C19 | met |
| 6 | Operator questions >= 5 | 7) QO1-QO7 | met |
| 7 | Scope boundary explicit | "Scope boundary" | met |
| 8 | Migration/backout documented | 9), 9.7 | met |
| 9 | Risks and residual unknowns explicit | 10) R1-R8 | met |
| -- | Slot-1 five beats, INTENT block present | "DAP Intent" | met (Beat 5 delegated to the doer; stated, not skipped) |
| -- | Slot-3 spec quoted verbatim before decisions | 0.1, 0.2 | met |

