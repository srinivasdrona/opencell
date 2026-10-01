# PROTEIN_TRANSLOCATION_STAGE2_DESIGN

**Class:** REVISION (refines §9.4 of `docs/design/compartmental_protein_state_migration.md`; no new architecture).
**Base:** `d898a3f` on `fix/protein-translocation-stage2-20261001`.
**Slot-2 template:** `docs/prompts/DESIGN_TEMPLATE.md` revision-class minimum.
**Probe outputs:** `artifacts/stage2_probes/p{1,3,4,5,7,8,9}_out.txt` (regeneratable, gitignored).

---

## 0) Spec-authority quotations

### 0.1 `docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml` (verbatim)

```yaml
  - name: ProteinTranslocation
    behavior_gate: L2.2
    behavior_verdict: PASS
    eligibility: BLOCKED_CODE_DEVIATION
    findings:
      - id: PTRANS-DEVIATIONS
        kind: CODE_DEVIATION
        disposition: OPEN
        summary: >-
          Two behavior deviations remain open and two wiring-row claims are
          wrong.
        evidence:
          - path: docs/phase_f/audits/ProteinTranslocation_semantic_audit.md
            lines: "58-61"
```

`ProteinTranslocation_semantic_audit.md:58-61` (verbatim) is the aggregate block
`- VERIFIED: 6` / `- ROW_WRONG: 2` / `- CODE_DEVIATES: 2` / `- MISSING: 0`.
`CODE_DEVIATES` = **PT-S4-03** (request pool-floor) and **PT-S5-02** (non-migrated
representation). `ROW_WRONG` = **PT-S4-01** (stale deviation prose) and **PT-S4-02**
(row formula omits the capacity mins). Row repair is a wiring-row edit, banned on
this branch: this design closes the two `CODE_DEVIATES` findings and hands the two
`ROW_WRONG` items to the operator as a named precondition for eligibility.

### 0.2 `ProteinTranslocation.m` (highest authority)

```matlab
% :198-203
this.monomerCompartments(... == terminalOrganelleCytosolIndexs)  = this.compartment.cytosolIndexs;
this.monomerCompartments(... == terminalOrganelleMembraneIndexs) = this.compartment.membraneIndexs;
this.monomerIndexs_translocating = find(this.monomerCompartments ~= this.compartment.cytosolIndexs);
this.monomerSRPPathways = ismember({knowledgeBase.proteinMonomers.signalSequenceType}',{'lipoprotein','secretory'}');

% :284-301  calcResourceRequirements_Current
translocases = ceil(min(this.enzymes([ATPase pore])) * this.translocaseSpecificRate * this.stepSizeSec);
SRPs         = ceil(min(this.enzymes([SRP SRPreceptor])) * this.stepSizeSec);
result(atp)  = min(translocases, this.monomers(this.monomerIndexs_translocating, cytosolIndexs)' * ceil(this.monomerLengths(this.monomerIndexs_translocating)/this.preproteinTranslocase_aaTranslocatedPerATP));
result(gtp)  = this.SRP_GTPUsedPerMonomer * min(SRPs, this.monomerSRPPathways' * this.monomers(:, cytosolIndexs));
result(water)= result(atp) + result(gtp);

% :350-353  evolveState transfer
this.monomers(idx_monomer, this.monomerCompartments(idx_monomer)) = ... + 1;
this.monomers(idx_monomer, this.compartment.cytosolIndexs)        = ... - 1;
```

`:190` fixes the row basis: `monomerWholeCellModelIDs = monomer.wholeCellModelIDs(
monomer.processedIIndexs)` — the process's entire monomer state is the
**processed-I** form block. No `location` string, no second queue, anywhere.

---

## DAP intent (slot-1 carryover)

1. **Contract (Beat 1).** Every Karr-translocatable monomer copy is owned by
   `protein.compartment_counts.processed_i[wid][compartment]`; translocation moves
   exact copies cytosol → source-derived destination; the request equals Karr's
   `calcResourceRequirements_Current` exactly.
2. **Surface (Beat 2).** 7 production modules + `protein_state.py` + one composite
   topology row (§3, §7). Suspect patterns found and named: the `if not
   cytoplasmic_counts:` location-ignoring fallback, the set-ordered migrated tail,
   the `max(need, pool)` floor, and `RequestCalculatorPTransloc`'s legacy leaf
   declarations for already-migrated WIDs.
3. **Expected observable (Beat 3).** `MIGRATED_WIDS` goes 8 → **124**;
   `protein.compartment_counts` holds **7,440** leaves; PT's `location` and
   `unprocessed_counts` branches hold **0** leaves; and on constructed state
   `(pending={MG_014:10, MG_032:7}, enzymes=[3,3,1000,1000], pool=0)` the request
   is exactly `ATP=320, GTP=6, H2O=326` (today: `320/14/334`).
4. **Inversion (Beat 4).** The most embarrassing pass-while-wrong: the doer
   expands `MIGRATED_WIDS`, every authority test goes green, and 116 WIDs silently
   lose their nascent→mature chain because one maturation writer's legacy branch
   was trimmed but its *update builder* still emits those WIDs — Vivarium creates
   the undeclared leaf and a second authority is resurrected under a path nobody
   declared. C5 + C6 exist specifically to kill this.
5. **PM sanity-check.** *PM: I am assuming Stage 2 must be a full-WID enrollment
   (all 10 forms × 6 compartments for 124 WIDs), per D7 and the directive's "all
   10x6 authority leaves" test — not a `processed_i`-only form slice. A form slice
   would be ~6× smaller but would straddle PPI's nascent→processedI and PPII's
   processedI→processedII boundaries, which D7 already rejected. If you want the
   form slice instead, this design is wrong at D1.*

---

## 1) Design contract

```
Required behavior:
  R1 The translocatable WID set is derived at construction from
     ProteinTranslocation_flat.mat `monomerIndexs_translocating`; no literal WID
     list, no exclusion set, no hardcoded cardinality.
  R2 For every such WID the processed-I pool lives only at
     protein.compartment_counts.processed_i[wid][c|e|m]; translocation emits
     {-n at c, +n at dest} in one update. No `location`, no queue decrement.
  R3 RequestCalculatorPTransloc emits exactly Karr's
     calcResourceRequirements_Current for ATP/GTP/H2O and 0 elsewhere.
  R4 One persistent RNG stream; one randperm per tick over total cytosolic
     copies; copy->WID mapping follows fixture order.
Done = (property): for every (form, wid, compartment) cell of the 124 enrolled
  WIDs there is exactly one writable store path, and the ProteinTranslocation
  request is a pure function of (authority processed_i cytosol counts, enzyme
  counts) with no substrate-pool term.
Beat-4 inversion: see DAP item 4.
Falsifier: a Karr code path that writes processedI counts for a translocatable
  WID outside the 7 modules in section 3.
```

---

## 2) Empirical preflight (all probes run; outputs quoted in STATUS)

| # | Question | Result |
|---|---|---|
| P1 | True translocatable cardinality | **119**, not "117 + 2". Fixture `monomerIndexs_translocating` = 119 / 482; non-translocating = 363. The design's "117 + 2" is the *old port count* (119 minus the 2 then-excluded TOA WIDs), not two extra WIDs. **3** are already migrated (MG_191, MG_192, MG_318) ⇒ **116 new**. |
| P1 | Class / pathway split | dest code 3 (`e`) = 20, all SRP; dest code 4 (`m`) = 99, of which SRP = 14 (lipoprotein) and non-SRP = 85 (integral membrane). SRP total = 34 = exactly `ismember(signalSequenceType,{'lipoprotein','secretory'})`. The class docstring ("SRP is true for integral membrane") is **wrong**; the code is authority. OC's derived sets match the fixture 1:1 (0 symmetric difference). |
| P1 | SRP-flagged non-translocating monomers | **0** ⇒ Karr's GTP term over `monomers(:,cytosol)` (all 482) is numerically identical to the translocating-only sum. Implement it over all monomers anyway; assert the equality. |
| P2 | Destination mapping | Remap is applied *before* the translocating set is derived. KB `processedI` compartments: 358 `c`, 20 `e`, 96 `m`, 5 `tc`, 3 `tm`. Only MG_191/192/318 are `tm`→`m`; **no Stage-2-new WID is remapped**, so for all 116, destination == KB home compartment == the `migrated_compartment_by_wid` value PPII/Folding/Modification already use. 0 destination mismatches vs current OC map. |
| P3 | Writer/reader intersection | Exact per-module Stage-2-new leaf counts (no "same writers"): translation_v3 `unprocessed_counts` 116; processing_i `unprocessed_counts` 116 + `processed_counts` 116; processing_ii `processed_counts` 116 + `unfolded_counts` 116 + `signal_sequence_counts` 116 (+ undeclared dynamic `counts` write); folding `unfolded_counts` 116 + `counts` 116; decay_light `counts` 116; translocation `counts` 117→1, `unprocessed_counts` 116, `location` 116. Readers: observability `counts` 116, host_interaction `counts` 4. **Zero** overlap: protein_modification (18 leaves), ribosome_assembly (58), dna_supercoiling (1), replication_initiation (1), chromosome_segregation (3), protein_activation (3), dna_repair (9), txn_regulation (3), rna_* (1/5/7). |
| P3 | Stage-1 leak found | `RequestCalculatorPTransloc.ports_schema` declares `unprocessed_counts` and `location` for **all 119**, including MG_191/MG_192/MG_318 — writable legacy leaves for already-migrated WIDs. The existing C2 test skips it (empty `branches` tuple in the manifest). Stage 2 must fix both the schema and the manifest row. |
| P4 | Request algebra | Hand-derived vs current, 6 constructed states. `zero enzymes`: Karr 0/0/0, OC 500000/400000/900000. `pool >> need`: Karr 320/14/334, OC 500000/400000/900000. `SRP cap 3 < 7 pending`: Karr 320/**6**/326, OC 320/14/334. `translocase enzymes 0`: Karr **0**/14/14, OC 500000/400000/900000. Pool-empty control matches (320/14/334) — the current code is right only when the pool is empty. Units: `translocases` is in **amino acids** (not divided by `aaPerATP`, unlike `evolveState`); with rate 2.71e12 the ATP min() binds **only at zero enzymes**. `SRPs = ceil(min(SRP,receptor)*stepSizeSec)` is in monomers and binds routinely. |
| P5 | F-trace activity | 100 ticks, seed 0. Mutating ticks: substrates 13, monomers 13; enzymes/boundEnzymes 0 (pass-through). 17 copies move total, 8 distinct WIDs, max 2/tick. Per-compartment: `c` −17, `e` +4, `m` +13; grand total conserved exactly every tick. Enzymes constant `[29,16,13,13]` ⇒ SRP cap 16/tick, translocase cap 3.5e13 ⇒ **neither capacity ever binds in the F trace**. The current harness projects `np.arange(482)` = cytosol only, so arrival is never compared. **Replay can distinguish**: departure counts, substrate stoichiometry, per-tick event counts, and (after the harness change) arrival into `e`/`m`. **Replay cannot distinguish**: the capacity-min repair, the pool-floor repair, or stream persistence — all three need constructed-state tests. |
| P7 | RNG / ordering | Current code appends migrated WIDs **after** the fixture-ordered legacy group, and iterates a `set`. For pending `{MG_014 (pos 0), MG_191 (pos 49), MG_468 (pos 118)}` Karr's group order is `[MG_014, MG_191, MG_468]`; OC produces `[MG_014, MG_468, MG_191]` — same randperm draw, different copy→WID mapping. Set iteration order is hash-randomized across interpreter runs. `searchsorted(cum,r,'left')` over nonzero groups == MATLAB `find(r<=cumsum,1,'first')` (0 mismatches), so skipping zero-count groups is safe; **order is not**. Stream is persistent within an instance; reconstruction replays the prefix. |
| P8/P9 | Seed discontinuity | `ProteinMonomer_flat.mat` mature row carries **4,203** copies for the 116 (433 in `e`, 3,770 in `m`, 0 in `c`); the current flat seed `m3_model.counts_mature` is **0** for all 116 (and was 0 for the Stage-1 8, which added +192). Stage 2 therefore adds **+4,203** mature copies at t=0 — source-faithful and precedent-consistent, but it moves chassis initial mass and must be measured by L2.4, not assumed. |

---

## 3) Interaction surfaces needed to implement

| ID | Producer → Consumer | Contract unit | Failure if mismatched | Anchor |
|---|---|---|---|---|
| S1 | `protein_state.MIGRATED_WIDS` → every module's `ports_schema` | the 124-WID set, loaded from fixtures, not literals | partial migration ⇒ dual authority | `protein_state.py:66`, `9.7` item 3 |
| S2 | PPI `processed_i[wid]["c"]` → PT read | cytosol processed-I pool | PT sees 0 pending, becomes inert | `karr_protein_processing_i.py:332-348` |
| S3 | PT `processed_i[wid][dest]` → PPII read at `migrated_compartment_by_wid[wid]` | destination letter must equal PPII's home letter | signal-peptide cleavage never fires | `karr_protein_processing_ii.py:88-91`, P2 |
| S4 | `RequestCalculatorPTransloc` → `karr_allocation_step` | `requests[name][ATP/GTP/H2O]` | fair-share theft from 27 peers (`@Simulation/evolveState.m:36-38`) | `karr_composite.py:930-934, 997-1005` |
| S5 | `complex.counts` / `protein.counts` → request calculator enzyme capacity | 3 complex + 1 monomer enzyme | capacity term unreadable ⇒ cap can't be applied | `karr_composite.py:904-910` (PT has it; the calculator does **not**) |
| S6 | `ProteinFlatProjectionStep` → `protein.counts` rejecting updater | 124 flat leaves | any legacy mature writer raises at runtime | `protein_state.py:160-176` |
| S7 | L2.1/L2.2 harness `observable_store_path("monomers")` → `("protein","unprocessed_counts")` | oracle input routing | branch becomes empty ⇒ oracle input silently dropped ⇒ hollow green | `l2_replay_common.py:493-497` |

---

## 4) Decision ledger

### D1 — `MIGRATED_WIDS` expansion and atomicity boundary
- **Question:** which cells migrate, and in how many commits?
- **Options:** (1) `processed_i` form slice for 119 WIDs; (2) full-WID enrollment of the 119; (3) all 482 (Stage 3); (4) staged sub-batches of the 119.
- **Chosen:** **(2)** — `MIGRATED_WIDS` = TOA-8 ∪ translocatable-119 = **124 WIDs**, all 10 forms × 6 compartments = **7,440** authority leaves; **one** commit for the whole enrollment + re-homing.
- **Rationale:** D7's closed-cut argument is per WID, not per form. Option 1 leaves PPI's nascent→processedI and PPII's processedI→processedII straddling the boundary, requiring flat→compartment adapters that invent a compartment. Option 3 is the banned big bang (the other 358 WIDs have no source pressure here). Option 4 creates an interval in which `MIGRATED_WIDS` and the legacy branches disagree — exactly the banned dual-writable period.
- **Tradeoff:** the blast radius is 7 production modules, not 1. P3 bounds it exactly.
- **Beat-4 inversion:** 124 is asserted but one WID is dropped because a module's exclusion uses `self.translocatable_wids` (class-grouped, 119) while another uses `MIGRATED_WIDS` (124) — the two differ by the 5 non-translocating TOA WIDs. Guard: every exclusion must test `wid not in MIGRATED_WIDS`, never a local list; C6 enumerates realized leaf paths.
- **Falsifier:** a Karr source path that writes processedI counts for a translocatable WID outside §3.

### D2 — Form and compartments for the transfer
- **Chosen:** form `processed_i`; source `"c"`; destination `COMPARTMENTS[monomerCompartments[i] - 1]` read from the fixture **after** Karr's tc→c / tm→m remap. Update shape: `{"protein": {"compartment_counts": {"processed_i": {wid: {"c": -n, dest: +n}}}}}`.
- **Rationale:** `:350-353` increments `monomerCompartments(idx)` and decrements cytosol in the same statement pair; `:198-200` is the only remap.
- **Beat-4 inversion:** the doer uses the **ProteinMonomer KB** compartment column directly and gets `tm` for MG_191/192/318, landing copies in a compartment PT never writes in Karr. Guard: C4 asserts dest ∈ {`c`,`e`,`m`} for all 124, and `m` specifically for the three tm WIDs.
- **Falsifier:** a translocatable WID whose post-remap code is 5 or 6 (P2: none).

### D3 — Re-homing every maturation writer
- **Chosen:** extend each module's **existing** `MIGRATED_WIDS` branch (all six already implement the pattern for the 8) to the 124, with no new code shape:

| File | Legacy branch → authority cell | Source anchor |
|---|---|---|
| `karr_translation_v3.py` | `unprocessed_counts` → `nascent[wid]["c"]` | already at `:212-219, 789-797` |
| `karr_protein_processing_i.py` | `unprocessed_counts`→`nascent["c"]`, `processed_counts`→`processed_i["c"]` | `:332-348` (cites `ProteinProcessingI.m:163-164`) |
| `karr_protein_processing_ii.py` | `processed_counts`→`processed_i[home]`, `unfolded_counts`→`processed_ii[home]`, `signal_sequence_counts`→`signal_sequence[home]`; the undeclared dynamic `counts` write must disappear for all 124 | `:88-91, 407-423` |
| `karr_protein_folding.py` | `unfolded_counts`→`processed_ii[home]`, `counts`→`folded[home]` | `:157-160, 361-374` |
| `karr_protein_modification.py` | **no change** — 0 Stage-2 overlap (P3) | — |
| `karr_protein_decay_light.py` | `counts`→`mature[home]` exclusion extends to 124 | `:380, 1027` |
| `karr_protein_translocation.py` | `unprocessed_counts` + `location` branches **deleted**; `counts` keeps only `MG_297_MONOMER` | this design |

- **Beat-4 inversion:** a branch dict is trimmed but the update builder still emits the WID; Vivarium creates the leaf. Guard: C5 (declared-writes-only) + C6 (realized leaf-path set).
- **Falsifier:** P3 re-run after the change showing any non-zero Stage-2 count in a legacy writable branch.

### D4 — Request-calculator inputs, formula, and topology
- **Chosen:** rewrite `RequestCalculatorPTransloc.next_update` as a literal transcription of `:284-301`: `translocases = ceil(min(ATPase,pore)·translocaseSpecificRate·dt)`; `SRPs = ceil(min(SRP,receptor)·dt)`; `ATP = min(translocases, Σ_translocating pending_c[wid]·ceil(len/35))`; `GTP = 2·min(SRPs, Σ_all_482 srpFlag[wid]·pending_c[wid])`; `H2O = ATP + GTP`; every other requested WID 0. `pending_c[wid]` comes **only** from `protein.compartment_counts.processed_i[wid]["c"]`; the `substrates` port leaves the read path entirely (the pool floor goes with it).
- **Topology change required (yes):** add a `complex` port mapped to `("complex",)`. Three of the four enzymes (`MG_0001_048`, `MG_072_DIMER`, `MG_055_170_277_464_476_20MER`) live in `complex.counts` and the calculator cannot read them today. Schema: drop `unprocessed_counts` and `location`; declare `compartment_counts.processed_i` for the 124 and `protein.counts` for `MG_297_MONOMER` only.
- **Beat-4 inversion:** the doer divides `translocases` by `aaPerATP` "to match `evolveState`", silently changing the cap 35×. Guard: C8 pins the literal `ceil(min(e)·rate·dt)` at a binding and a non-binding enzyme level.
- **Falsifier:** a MATLAB revision in which `calcResourceRequirements_Current` divides by `preproteinTranslocase_aaTranslocatedPerATP` (it does not).

### D5 — RNG stream and per-copy ordering
- **Chosen:** one `MatlabRandStream` per instance, built in `__init__`, never re-seeded. Build the pending map by iterating `translocatable_wids_in_fixture_order` **once** — no migrated/non-migrated split, no trailing append; drop zero-count WIDs (order-safe, P7-b); one `randperm(total_copies)` per `next_update`; `searchsorted(cum, r, "left")`. Delete the `if not cytoplasmic_counts:` location-ignoring fallback. `migrated_translocating_wids` must stop being a `set` in any ordering context.
- **Beat-4 inversion:** a test reconstructs the process per tick and therefore cannot see stream drift — exactly what the L2.2 Design-A harness does. Guard: C11 runs ≥3 `next_update` calls on **one** instance and asserts both draw advance and fixture-ordered copy mapping.

### D6 — Deletion of `protein.location`
- **Chosen:** delete the branch from `karr_protein_translocation.py` and `karr_request_calculators.py` (M15/M33). It has no Karr analogue (§2.4) and after D1 no WID could use it. Grep for `"location"` under `opencell/vivarium/` must return 0 protein-port hits.
- **Beat-4 inversion:** a reader still maps the port and silently reads defaults forever. Guard: C3 asserts no `"location"` key in any protein port.

### D7 — Evidence configuration (L2.1/L2.2) repair
- **Chosen:** `l2_replay_common.observable_store_path("monomers")` gains an explicit PT route to `("protein","compartment_counts","processed_i")`, and the PT replay test's `_INDEX_PROJECTION_LITERAL` widens from `np.arange(482)` (cytosol only) to all 2,892 indices, mapping `COMPARTMENTS[j] ↔ flat index j*482 + i`.
- **Rationale:** after D1 the `unprocessed_counts` branch is empty, so the current `if isinstance(unprocessed, dict) and unprocessed:` test falls through to `("protein","counts")` — a leaf PT no longer declares. The oracle input would be silently dropped and the gate would go green on an all-zero no-op. Highest-probability hollow-green in this change.
- **Remaining mismatch (NOT closed):** `_protein_translocation_process(_sample_seed(seed, tick))` reconstructs the process every tick. That is intrinsic to L2.2 Design A (per-tick independent samples), not a bug — but it means **L2.2 cannot be cited as evidence for D5**. C11 is the only evidence for stream persistence, and STATUS must say so when eligibility is proposed.

### D8 — Migration, commits, backout
- **Chosen:** three commits, each independently revertable, none leaving two writable authorities for one cell: `S2-a` Gemini's frozen tests + harness routing (red); `S2-b` `protein_state.py` enrollment + all 7 production modules + topology row (the atomic flip — must be one commit); `S2-c` deletion of now-dead legacy branches/manifest rows. Backout = `git revert S2-b`.
- **Triggers (any one):** L2.4 conservation regresses at any of the four seeds; baseline integrity ≠ `INTEGRITY_OK` or eligible count decreases; repo-wide skip count ≠ 5; any frozen test red after the doer declares done; the doer cannot satisfy a frozen test without editing it.
- **Beat-4 inversion:** `S2-b` is split "for reviewability" and the tree sits dual-authority between commits. Guard: `assert_migration_consistency()` runs at import and fails loudly on partial application.

### D9 — Stage-3 avoidance
- **Chosen:** the remaining **358** cytosolic WIDs stay legacy. Source proof: `monomerIndexs_nontranslocating` = 363, and nothing in `ProteinTranslocation.m` reads or writes any monomer outside `monomerIndexs_translocating`. `assert_migration_consistency`'s independent external source becomes `TOA_flat.substrateWholeCellModelIDs ∪ PT_flat.monomerIndexs_translocating`.

---

## 5) Falsifiable claims (the Gemini test specification)

| ID | Claim | Measurement | Exact value |
|---|---|---|---|
| C1 | Complete source-derived WID set | load `MIGRATED_WIDS`; recompute the union from the two fixtures | `len == 124`; symmetric difference `== set()`; no literal WID list in `karr_protein_translocation.py` outside the fixture parse |
| C2 | Full authority enrollment | count leaves of `compartment_counts_schema(MIGRATED_WIDS)` | `10 × 124 × 6 == 7440`; every enrolled WID present in all 10 form dicts |
| C3 | Legacy absence | for every module in the manifest, `set(MIGRATED_WIDS) & set(branch)` | `== set()` for every legacy writable branch; **and** `"location"` absent from every protein port |
| C4 | Conserving per-copy transfer | seed `processed_i[wid]["c"]=k` for one SRP and one direct WID; run `next_update` | `Σ_compartments` unchanged; `c` delta `== -n`; `dest` delta `== +n`; dest ∈ {`c`,`e`,`m`}; `m` specifically for MG_191/192/318; no `location` key in the update |
| C5 | Declared-writes-only | for each of the 7 modules, written protein leaf paths ⊆ declared | `== True` (this is the D1 Beat-4 killer) |
| C6 | No leaf-path resurrection | realized store-tree protein leaf set after a 100-tick chassis run vs declared set | equal; no undeclared `protein.counts` path for any of the 124 |
| C7 | Request == Karr, adversarial states | hand-derived values, not re-derived from the implementation | zero enzymes → `0/0/0`; pool 5e5/4e5/9e5 with plentiful enzymes → `320/14/334`; SRP cap 3 vs 7 pending → `320/6/326`; translocase enzymes 0 → `0/14/14` |
| C8 | Capacity semantics | vary enzymes only | `translocases = ceil(min(ATPase,pore)*2.71e12*dt)` exactly (no `/35`); zero capacity ⇒ zero request on the capped species |
| C9 | No pool floor | hold pending/enzymes fixed, sweep pool ∈ {0, 1e3, 1e9} | request identical across all three |
| C10 | Water identity | any state | `H2O == ATP + GTP` exactly; ADP/GDP/PI/H requests `== 0` |
| C11 | Stream persistence + order | 3 `next_update` calls on **one** instance; pending includes an early-fixture-position enrolled WID | consecutive randperm draws differ; realized copy→WID order equals the fixture-ordered reference; the test must not construct a second process |
| C12 | Production same-tick path | run the Engine one tick; capture `requests` then `substrates_allocated` | the request value equals C7's formula evaluated on the authority's `processed_i["c"]` counts, not on any flat mature count |
| C13 | No collateral change | non-translocating WIDs and the 8 TOA WIDs | TOA transfer tests (`test_toa_karr_transfer.py`, Stage-1 nodes) byte-identical; the 358 unmigrated WIDs keep their legacy branches |
| C14 | Seed accounting | Π(authority mature seed) for the 116 vs prior flat seed | `+4203` (`e` +433, `m` +3770), asserted explicitly so the change is recorded, not discovered |

**Plant inversions (must FAIL when planted, in a deliberately-broken local subclass — no production toggle):**
P-1 restore `max(need, pool)` → C9 fails. P-2 emit a `location` string → C3/C4 fail.
P-3 decrement `c` without incrementing dest → C4 fails. P-4 use the pre-remap KB
compartment (`tm`) for MG_191 → C4 fails. P-5 re-seed the RNG each `next_update`
→ C11 fails. P-6 drop the SRP `min()` → C7 case 3 fails. P-7 divide `translocases`
by 35 → C8 fails.

---

## 6) Tests Gemini must freeze before implementation

| File | Nodes |
|---|---|
| `tests/vivarium/test_protein_translocation_stage2.py` (new) | `test_c1_source_derived_wid_set_124`, `test_c2_full_10x6_enrollment`, `test_c4_per_copy_transfer_conserves_and_routes`, `test_c11_persistent_stream_and_fixture_order`, `test_c13_toa_and_nontranslocating_unchanged`, `test_c14_mature_seed_accounting` |
| `tests/vivarium/test_ptransloc_request_karr_algebra.py` (new) | `test_c7_adversarial_states[zero_enzymes|pool_gt_need|srp_capped|translocase_zero]`, `test_c8_capacity_units`, `test_c9_pool_independence`, `test_c10_water_identity`, `test_c7_plant_inversions` |
| `tests/vivarium/test_protein_state_no_dual_writer.py` (extend) | `test_c3_legacy_leaves_exclude_migrated_wids` widened to 124; **add `RequestCalculatorPTransloc` and `RequestCalculatorProteinPathway` to `PROTEIN_PROCESS_MANIFEST` with non-empty `branches`** (today they are skipped, which is why the Stage-1 leak survived); `test_c5_declared_writes_only` |
| `tests/vivarium/test_protein_state_authority.py` (extend) | `test_c1b_no_leaf_path_drift` → 7,440 leaves; `test_c6_no_path_resurrection_after_100_ticks` |
| `tests/vivarium/test_karr_protein_translocation_l2_replay.py` (rewrite) | widen `_INDEX_PROJECTION_LITERAL` to all 2,892 indices; assert arrival columns (`e` +4, `m` +13 over 100 ticks) |
| `tests/vivarium/l2_replay_common.py` (edit) | explicit PT route for `observable_store_path("monomers")` → `("protein","compartment_counts","processed_i")` |
| `tests/vivarium/test_karr_protein_translocation.py` (rewrite) | `test_protein_location_store_updates` must be **retired** (it asserts the deleted branch); the rest re-expressed against the authority |
| `tests/integration/test_ptransloc_enrollment_v3_v4.py` | add the `complex` port/topology assertion from D4 |

---

## 7) Production files the doer may touch

`opencell/vivarium/`: `protein_state.py`, `karr_protein_translocation.py`, `karr_request_calculators.py`, `karr_protein_processing_i.py`, `karr_protein_processing_ii.py`, `karr_protein_folding.py`, `karr_protein_decay_light.py`, `karr_translation_v3.py`, `karr_composite.py` (one topology row + one port). **Nothing else.** `karr_protein_modification.py`, `karr_translation.py`/`_v2.py` (non-runtime legacy), `karr_observability_step.py` and `karr_host_interaction.py` are already pure functions of `MIGRATED_WIDS` — verify by re-running P3, do not edit.

---

## 8) Risks, backout, and what this does NOT close

```
R1 Seed discontinuity: +4203 mature copies at t=0 (P9). Likelihood: certain.
   Impact: chassis initial mass changes; L2.4 could regress. Detection: C14 +
   L2.4 four seeds x 100 ticks. Mitigation: precedent is Stage 1's +192 with
   L2.4 still PASS; if L2.4 regresses, revert S2-b. Owner: doer.
R2 Hollow green via S7: the harness drops the oracle's monomer input once
   `unprocessed_counts` empties. Likelihood: high if D7 is skipped. Detection:
   the replay test must assert >=1 mutated tick and total moved copies == 17.
R3 Blast radius: 7 modules in one commit (D1). Mitigation: all six maturation
   writers already implement the identical MIGRATED_WIDS pattern; the diff is
   set-membership, not new logic. Detection: C5/C6.
R4 `use_protein_counts_compat` in ProteinProcessingI is a banned-shape flag
   (9.7 item 4) this change does not remove. It is PPI's blocker, not PT's;
   named here so it is not silently inherited.
```

**Does NOT close:** PT-S4-01/PT-S4-02 (`ROW_WRONG` — wiring-row edits, banned here); the L2.2 per-tick reconstruction (D7, intrinsic to Design A); Stage 3/4; any other process's baseline finding. **Eligibility may be promoted to `ELIGIBLE` only if** C1-C14 are green, L2.4 holds at four seeds, baseline integrity still reports `INTEGRITY_OK`, **and** the operator separately lands the two row corrections — otherwise the honest verdict stays `BLOCKED_ROW_CLAIM` and the baseline stays at 4/28.

---

## 9) Self-audit — every baseline blocker mapped

| Baseline / audit item | Decision | Test |
|---|---|---|
| PT-S4-03 `CODE_DEVIATES` — request pool floor | D4 | C7, C9, C12 |
| PT-S5-02 `CODE_DEVIATES` — non-migrated representation | D1, D2, D3, D6 | C1-C6, C13 |
| PT-S4-02 `ROW_WRONG` — missing capacity mins in the row formula | D4 (code side) | C7, C8 — **row edit out of scope** |
| PT-S4-01 `ROW_WRONG` — stale deviation prose | D5 (code side) | C11 — **row edit out of scope** |
| Design 9.4 "117 + 2" | D1 (resolved: 119 total, 116 new) | C1 |
| Design 6.7 C15/C16/C17 | D2, D3 | C4 (C15), C4 dest assertions (C16), C2/C5 (C17) |
| Stage-1 leak: calculator declares legacy leaves for migrated WIDs | D4 | C3 with the widened manifest |
| RNG ordering/set-iteration deviation (P7) | D5 | C11 |
| Harness routing break (S7) | D7 | replay test + C12 |
