# Phase D.2 — `MacromolecularComplexation` + `RibosomeAssembly`: Design Document v2

| Field           | Value                                                                 |
|-----------------|-----------------------------------------------------------------------|
| Status          | DESIGN v2 — implementation deferred (awaiting human review)           |
| Branch          | `agent/d2-design-v2` (do **not** merge to `main` until reviewed)      |
| Supersedes      | `agent/d2-design-doc:docs/design/d2_complex_assembly.md` (v1, 496 LOC)|
| Decisions baked | **Q1** = hybrid staged oracle, **Q2** = scope split (assembly only)   |
| MATLAB ref      | `+process/MacromolecularComplexation.m` (392 LOC), `+process/RibosomeAssembly.m` (370 LOC), `+state/ProteinComplex.m` (236 LOC) |
| Companion data  | `data/karr_fixtures/karr_protein_complexes.json` (201 complexes, schema `karr_protein_complexes__v1`) |
| Companion data  | `data/karr_fixtures/d2_mature_subset.json` (158 complexes with mature ≥ 1, **new in this PR**) |
| Critical-path   | Unblocks p10 (mass at division), p5/p6/p7 (RNAP/holoenzyme/70S), and the v2 chassis swap + M5 replisome |

---

## 0. Executive summary

D.2 builds Karr's 201 protein complexes from already-translated monomers,
mature RNAs, sub-complexes, metabolite cofactors, and prosthetic groups; it
emits the assembled **mature** form to a `complex.counts` store and emits
negative-coefficient byproducts (H⁺, AMP, PAP, PPI, PI, Mg, Zn) back to the
shared `substrates` store. After Q1 it **does not** emit a `bound` form —
that is the consumer process's responsibility (M2v2 RNAP, M3v2 ribosomes,
M5 replisome, F gyrase). After Q2 it **does not** model folding,
chaperone-assisted folding, activation, or sigma loading — those are
deferred to D.3 / D.4 / M6.

The algorithm mirrors Karr's `MacromolecularComplexation.evolveState()` at
the **network level** (greedy stoichiometric solver over the full complex
graph in topological order, with shared-subunit competition resolved by
Karr's collision-theory mass-action rule), plus a special path for the 70S
ribosome via `RibosomeAssembly.evolveState()`. v1's per-complex Monte-Carlo
collapse is dropped — it changed Karr's physics.

The oracle is **hybrid staged**: D.2 unit tests check conservation,
topo-ordering, shared-subunit competition, the 158-complex mature snapshot
subset, and the aggregate mature-complex dry mass (~1.20 × 10⁻¹⁵ g cytosol
+ 3.04 × 10⁻¹⁶ g membrane in Karr's snapshot). The 10 bound-heavy anchors
(`RIBOSOME_70S`, `RNA_POLYMERASE`, `DNA_GYRASE`, the four MG_*_DIMER /
MG_213_214_298_6MER_ADP DNA-repair / FtsZ helpers, MG_469_*MER_ATP, and
MG_428_DIMER) get integration tests **deferred** to v2-swap + M5 with an
`xfail("D.2 emits mature only; bound owned by consumer")` marker; they
must satisfy `D.2.mature + Σconsumers.bound ≈ snapshot.total` once those
processes exist.

The deliverable lands as a single doc-only commit on `agent/d2-design-v2`
plus the new mature-subset manifest fixture. **No code, no tests, no
chassis wiring** in this PR.

---

## 1. Scope (post-Q2)

### 1.1 In scope for D.2

| Karr process                  | What we cover                                                  |
|-------------------------------|----------------------------------------------------------------|
| `MacromolecularComplexation`  | Network-level greedy stoichiometric solver over **all** 201 complexes whose `formationProcesses` flag is `Process_MacromolecularComplexation` (≈185 of 201; the rest are routed to `RibosomeAssembly`). |
| `RibosomeAssembly`            | The 70S particle assembly path (consumes 30S + 50S + GTP + H₂O via 6 GTPases; emits GDP/Pi/H). |
| Byproduct emission            | The 20 complexes carrying negative `metabolites`/`prosthetic` coefficients (§4.4). |

### 1.2 Out of scope (deferred)

| Concern                  | Why deferred                                              | Lands in |
|--------------------------|-----------------------------------------------------------|----------|
| ProteinFolding           | Distinct Karr process with chaperone-capacity kinetics; not on D.2's critical path for p10 mass. | **D.3**  |
| ProteinActivation        | Cofactor loading, prosthetic-group attachment beyond stoichiometric assembly, redox-state activation. | **D.4** or fold into **M6 regulation** (TBD by reviewer). |
| Chaperone routing        | Requires fixing the corrupted `chaperones` field for `MG_392_393_21MER` (currently lists 46 metabolite WIDs — see §8). | **D.3** prerequisite. |
| `bound` form emission    | Per Q1, the `bound` count for each consumer is owned by the consumer (M2v2 RNAP, M3v2 ribosomes, M5 replisome, F gyrase). | Each consumer's v2. |
| Translation-factor pool dynamics | Karr models EF-Tu / IF / RF as bound complexes during translation. | M3v2.    |

### 1.3 Phenotypes unblocked

| ID  | Phenotype                       | Status today          | After D.2 (mature-only) |
|-----|---------------------------------|-----------------------|--------------------------|
| p10 | Cell dry mass at division       | partial (monomers + RNA only) | adds ≈ 1.2 × 10⁻¹⁵ g cytosolic complex mass + 0.30 × 10⁻¹⁵ g membrane = **~38 % of cellDry** that is currently missing. |
| p5  | RNAP count                      | constant              | live mature pool; bound pool stays a stub until M2v2. |
| p6  | RNAP holoenzyme count           | constant              | live (mature only).      |
| p7  | 70S ribosome count              | constant              | mature == 0 in snapshot (all 56 are **bound** — see §6.2); live count appears once M3v2 lands. |
| p8  | 30S/50S free pool               | unmodelled            | live mature pool.        |
| p11+| FtsZ ring, gyrase load          | unmodelled            | enables D.3 / Phase F.   |

---

## 2. Inputs (verified data sources)

### 2.1 Already-extracted fixtures

| Path                                                    | Schema                          | Used for |
|---------------------------------------------------------|---------------------------------|----------|
| `data/karr_fixtures/karr_protein_complexes.json`        | `karr_protein_complexes__v1`    | 201-complex composition (monomers/subcomplexes/metabolites/prosthetic/rnas), DAG topology, byproduct enumeration, formation compartment, activation rules. |
| `data/karr_archive/karr_archive.npz` (via `opencell._karr_archive.load_karr_archive()`) | `protein_complexes` block | Same 201 complexes via struct-array view (alternative, equivalent payload). |

### 2.2 Already-in-archive (read by `opencell._karr_archive`)

D.2 itself does **not** need any *runtime* fields from
`sim_fitted_targeted` beyond what's already loaded — the runtime path is
"pull subunits → run solver → push complexes". The archive fields below
are needed only by **oracles / test fixtures**:

| Karr `.mat` path                                   | Archive key                                  | Notes |
|----------------------------------------------------|----------------------------------------------|-------|
| `parameters.states.Mass.cellInitialDryWeight`      | already in `sim_fitted_targeted` spec        | aggregate-mass oracle baseline |
| `states.State_Mass.dump.cellDry`                   | already in `sim_fitted_targeted` spec        | denominator for "complex ≈ 38 % of cellDry" |

### 2.3 ARCHIVE_SPEC extensions required (must land before D.2 code)

The snapshot path Karr uses to publish per-complex counts is
`data.states.State_Mass.dump.complex.*`. Verified present in
`data/karr_archive/full_inventory.json` (4837 leaves; all paths below have
real shapes/dtypes). **None** of these are currently in `ARCHIVE_SPEC`.

Add the following entries under
`scripts/build_karr_archive.py::ARCHIVE_SPEC["sim_fitted_targeted"]["fields"]`:

| # | Karr `.mat` path (relative to `data.`)                   | Shape / dtype       | Python field (after archive flattening)                  | Consumed by                              |
|---|----------------------------------------------------------|---------------------|----------------------------------------------------------|------------------------------------------|
| 1 | `states.State_Mass.dump.complex.counts`                  | `[1206, 6]` uint8   | `arch.sim_fitted_targeted.states__State_Mass__dump__complex__counts` | D.2 mature-subset oracle, aggregate dry-mass oracle, integration anchor oracle (deferred). |
| 2 | `states.State_Mass.dump.complex.matureIndexs`            | `[201]` uint16      | `…__matureIndexs`                                        | D.2 mature-subset oracle (projects 1206 → 201 mature rows; 1-based). |
| 3 | `states.State_Mass.dump.complex.boundIndexs`             | `[201]` uint16      | `…__boundIndexs`                                         | Integration-anchor oracle (deferred to v2-swap + M5). |
| 4 | `states.State_Mass.dump.complex.nascentIndexs`           | `[201]` uint8       | `…__nascentIndexs`                                       | Snapshot-form sanity (Karr snapshot has nascent == 0; assertion). |
| 5 | `states.State_Mass.dump.complex.inactivatedIndexs`       | `[201]` uint16      | `…__inactivatedIndexs`                                   | Snapshot-form sanity (37 in snapshot; documented, not asserted by D.2). |
| 6 | `states.State_Mass.dump.complex.misfoldedIndexs`         | `[201]` uint16      | `…__misfoldedIndexs`                                     | D.3 future use.                           |
| 7 | `states.State_Mass.dump.complex.damagedIndexs`           | `[201]` uint16      | `…__damagedIndexs`                                       | D.3 future use.                           |
| 8 | `states.State_Mass.dump.complex.molecularWeights`        | `[1206]` float64    | `…__molecularWeights`                                    | Aggregate dry-mass oracle (`mature_counts · mw[matureIndexs] / N_A`). |
| 9 | `states.State_Mass.dump.complex.dryWeight`               | `[6]` float64       | `…__dryWeight`                                           | Aggregate dry-mass oracle (direct comparison: `1.2009 × 10⁻¹⁵ g` cytosol, `3.043 × 10⁻¹⁶ g` membrane). |
|10 | `states.State_Mass.dump.complex.compartments`            | `[1206]` uint8      | `…__compartments`                                        | Per-compartment projection during oracle aggregation. |
|11 | `states.State_Mass.dump.complex.formationProcesses`      | `[1206]` uint32     | `…__formationProcesses`                                  | Discriminator: which complexes go through `MacromolecularComplexation` vs. `RibosomeAssembly`. |
|12 | `states.State_Mass.dump.complex.proteinComplexComposition` | `[525, 201, 6]` uint8 | `…__proteinComplexComposition`                       | Solver adjacency (alternative to building from `karr_protein_complexes.json` — same data, different shape). Use as cross-check fixture. |
|13 | `states.State_Mass.dump.complex.ribosome70SIndexs`       | `[]` int64 (scalar) | `…__ribosome70SIndexs`                                   | `RibosomeAssembly` special path entry point. |
|14 | `states.State_Mass.dump.complex.ribosome30SIndexs`       | `[]` int64 (scalar) | `…__ribosome30SIndexs`                                   | `RibosomeAssembly` predecessor identification. |
|15 | `states.State_Mass.dump.complex.ribosome50SIndexs`       | `[]` int64 (scalar) | `…__ribosome50SIndexs`                                   | `RibosomeAssembly` predecessor identification. |
|16 | `states.State_Mass.dump.complex.translationFactorIndexs` | `[3]` uint8         | `…__translationFactorIndexs`                             | Documents the 3 translation factors that exist in `bound` form during translation (M3v2 concern, not D.2). |
|17 | `states.State_Mass.dump.complex.rnaPolymeraseIndexs`     | `[2]` uint8         | `…__rnaPolymeraseIndexs`                                 | Anchors RNA_POLYMERASE / RNA_POLYMERASE_HOLOENZYME pair for M2v2 hand-off. |
|18 | `states.State_Mass.dump.complex.replisomeIndexs`         | `[4]` uint8         | `…__replisomeIndexs`                                     | M5 hand-off.                              |
|19 | `states.State_Mass.dump.complex.dnaPolymeraseIndexs`     | `[3]` uint8         | `…__dnaPolymeraseIndexs`                                 | M5 hand-off.                              |
|20 | `states.State_Mass.dump.complex.ftsZGTPIndexs`           | `[]` int64 (scalar) | `…__ftsZGTPIndexs`                                       | FtsZ ring (Phase F).                      |
|21 | `states.State_Mass.dump.complex.ftsZGDPIndexs`           | `[]` int64 (scalar) | `…__ftsZGDPIndexs`                                       | FtsZ ring (Phase F).                      |
|22 | `states.State_Mass.dump.complex.dnaAPolymerIndexs`       | `[12]` uint8        | `…__dnaAPolymerIndexs`                                   | M5 origin firing (Phase F).               |

**Total: 22 new ARCHIVE_SPEC entries.** All MATLAB-side arrays are uint8
/ uint16 / uint32 / float64; combined ≈ 1206·6 + 201·6 + 1206·2 + 525·201·6
= ~660 KB raw, well within the archive size budget.

The doc-only commit **does not** modify `scripts/build_karr_archive.py`;
the spec extension is the first action of the D.2 implementation PR.

### 2.4 No new MATLAB extraction needed for `RibosomeAssembly` cost data

v1 claimed `RibosomeAssembly.m`'s GTP/H₂O costs lived only in MATLAB
source. Re-inspection confirms the per-particle costs (1 GTP, 1 H₂O per
GTPase per particle, 6 GTPases) are **already encoded** in
`karr_protein_complexes.json`:

- The 30S → 30S_IF3 path is in `subcomplexes` + `monomers` + `metabolites`.
- The 70S = 30S + 50S path is in `subcomplexes` (cofs 1.0 each) and the
  6×GTP / 6×H₂O / −6×GDP / −6×Pi balance is in `metabolites` and
  `prosthetic`.
- `RibosomeAssembly.m`'s "all-or-nothing per timestep" rule applies the
  same `floor(min(…))` formula as `MacromolecularComplexation`'s
  no-competition branch; no new fitted constants enter.

Therefore: **no new fixture file is required** for ribosome costs. The
"all-or-nothing" semantics are encoded in the algorithm (§4.5), not the
data. v1 BLOCKER 1 is resolved by reading the fixture more carefully, not
by extending the archive (beyond the 22 entries above which are needed
for *oracles*, not for runtime).

---

## 3. Algorithm — mirroring Karr's network-level solver

v1 collapsed Karr's network MC into a per-complex MC. That **changes the
physics**: shared-subunit competition was lost, and complexes that depend
on each other via sub-complexes were no longer guaranteed to be built in
the right order. v2 mirrors Karr's two-stage approach exactly.

### 3.1 Pre-computation (once at process construction)

1. Load 201 complexes from `karr_protein_complexes.json`. Build:
   - Composition matrix `C[#subunits × 201]` summed over compartments.
     Subunits = monomers ∪ subcomplexes ∪ rRNAs (positive coefficients
     only). `#subunits` ≈ 525 (matches the
     `proteinComplexComposition[525, 201, 6]` shape extracted in §2.3).
   - Byproduct matrix `B[#metab × 201]` (negative-coefficient
     `metabolites` + `prosthetic` rows; sign flipped to "produced").
   - Cofactor consumption matrix `K[#metab × 201]` (positive-coefficient
     metabolites — these are *consumed* during assembly, e.g. GTP).
   - Topological ordering of complexes via Kahn's algorithm on the
     `subcomplexes`-induced DAG (verified acyclic in current fixture).
   - Network decomposition via `findNonInteractingRowsAndColumns` —
     subunits that participate in **only one** complex form Network 0
     (no competition, go-to-completion). Remaining subunits with
     `≥ 2` parent complexes form competition networks N₁, N₂, … (in
     Karr's wild-type fitted KB this resolves to Network 0 + 1 large
     competition network containing ribosomal proteins and RNAP
     subunits, plus a handful of small networks).
   - Special flag: `is_ribosome_assembly[c]` true when
     `formationProcesses[c] == Process_RibosomeAssembly` (4 complexes:
     `RIBOSOME_30S`, `RIBOSOME_30S_IF3`, `RIBOSOME_50S`, `RIBOSOME_70S`
     — the exact set is data-driven via the new
     `formationProcesses` archive field, §2.3 #11).

### 3.2 Per-step `evolveState` (mirrors `MacromolecularComplexation.m` lines ~140–280)

```python
def next_update(self, timestep, states):
    # Snapshot pools (immutable inside this function)
    pool = self._gather_pools(states)            # dict[(wid, comp)] -> count
    new_complexes = defaultdict(int)             # per (complex_wid, formation_comp)
    byprod_delta = defaultdict(int)              # per (metab_wid, comp)
    cofactor_delta = defaultdict(int)            # per (metab_wid, comp)
    rng = self._rng_for_step(states)             # seeded per-step

    # Walk in topological order so a sub-complex is fully populated
    # before any parent that consumes it is tried.
    for net_id in [0] + self._competition_network_ids:
        complexes_in_net = self._complexes_by_network[net_id]
        if net_id == 0:
            # No competition: go to completion in topo order.
            for cx in self._topo_sort(complexes_in_net):
                if self._is_ribosome_assembly[cx]:
                    self._evolve_ribosome(cx, pool, new_complexes,
                                          byprod_delta, cofactor_delta)
                else:
                    self._evolve_no_competition(cx, pool, new_complexes,
                                                byprod_delta, cofactor_delta)
        else:
            # Competition: Karr's Monte-Carlo loop over the network.
            self._evolve_competition_network(
                net_id, complexes_in_net, pool, new_complexes,
                byprod_delta, cofactor_delta, rng,
            )

    return self._emit_update(new_complexes, byprod_delta, cofactor_delta, pool)
```

### 3.3 No-competition branch (`_evolve_no_competition`)

Direct port of `buildProteinComplexs_bounds` (MATLAB lines ~290–305):

```python
n_form = min(
    floor(pool[s] / C[s, cx])  for s in subunits_of(cx) if C[s, cx] > 0
)
n_form = min(n_form, floor(pool[m] / K[m, cx])  for m in cofactors_of(cx))
if n_form > 0:
    pool minus= C[:, cx] · n_form          # consume subunits
    pool minus= K[:, cx] · n_form          # consume cofactors
    new_complexes[cx] += n_form
    byprod_delta += B[:, cx] · n_form      # emit byproducts
```

`floor(min(...))` is Karr's exact rule. **Deterministic.**

### 3.4 Competition branch (`_evolve_competition_network`) — Karr's exact MC

Direct port of `buildProteinComplexs_montecarlokinetic` (MATLAB lines
~310–390). The key insight v1 missed: the MC loop is over the **network**,
not the complex. Each iteration draws **one complex** weighted by its
mass-action rate, builds **one copy** of it, decrements subunits, and
recomputes rates for the entire network.

```python
def _evolve_competition_network(self, net_id, cxs, pool, new_complexes,
                                byprod_delta, cofactor_delta, rng):
    iter_cap = self.params.n_mc_iterations_max  # safety bound, default 10_000
    for _ in range(iter_cap):
        # Per-complex upper bounds in the current pool state.
        ub = self._upper_bounds(cxs, pool)
        # Per-complex collision-theory mass-action rate.
        # rate_j = prod_i (pool_i / mean_pool) ** C[i, j]   (MATLAB line ~340)
        # mean_pool computed over the union of subunits in the network.
        rates = self._mass_action_rates(cxs, pool)
        rates[ub == 0] = 0.0
        if rates.sum() == 0:
            break                          # network exhausted
        # Draw one complex weighted by cumulative probability.
        cum = rates.cumsum() / rates.sum()
        u = rng.random()
        j = int(np.searchsorted(cum, u))   # first cum[j] >= u
        cx = cxs[j]
        # Build exactly one copy.
        pool minus= C[:, cx]
        pool minus= K[:, cx]
        new_complexes[cx] += 1
        byprod_delta += B[:, cx]
    else:
        # Hit iter_cap: log a once-per-step warning. Karr's fitted runs
        # converge in ~few hundred iterations even for the largest
        # networks, so this is a guardrail, not a normal path.
        self._warn_iter_cap_hit(net_id)
```

**Why this is correct (and why per-complex MC is wrong):** if complex A
and B share subunit s, the per-complex MC of v1 builds A first to
exhaustion of s, **then** tries B. That collapses Karr's competitive
allocation into a strict priority order, breaking the empirical
~RNAP_holo:RNAP ratio (≈ 120:200) which depends on simultaneous
competition for σ vs. core. Network-level MC reproduces the ratio.

### 3.5 Ribosome-assembly branch (`_evolve_ribosome`)

Direct port of `RibosomeAssembly.evolveState`. The only complex in the
fixture flagged `Process_RibosomeAssembly` is the 70S (and its
predecessors 30S, 30S_IF3, 50S, all of which `MacromolecularComplexation`
assembles in the same step). The 70S step is:

```python
def _evolve_ribosome(self, cx, pool, new_complexes, byprod_delta, cofactor_delta):
    # All-or-nothing per Karr header: either fully form within one tick
    # or make no progress.  Compute the integer particle count.
    n_max = floor_min(
        pool[("RIBOSOME_30S_IF3", "c")] / 1,
        pool[("RIBOSOME_50S",    "c")] / 1,
        pool[("GTP", "c")] / 6,                # 6 GTPases × 1 GTP each
        pool[("H2O", "c")] / 6,
    )
    if n_max <= 0:
        return
    pool[("RIBOSOME_30S_IF3","c")] -= n_max
    pool[("RIBOSOME_50S",   "c")] -= n_max
    pool[("GTP","c")] -= 6 * n_max
    pool[("H2O","c")] -= 6 * n_max
    new_complexes[(cx, "c")]      += n_max
    cofactor_delta[("GDP","c")] += 6 * n_max   # produced
    cofactor_delta[("PI", "c")] += 6 * n_max
    cofactor_delta[("H",  "c")] += 6 * n_max
```

The 6 GTPases (EngA/EngB/Era/Obg/RbfA/RbgA) are *catalysts* — they're
checked to be `> 0` but not consumed. The fixture's `metabolites` row for
70S already encodes the `+6 GTP, +6 H2O, −6 GDP, −6 PI, −6 H` balance, so
in practice `_evolve_ribosome` is structurally identical to
`_evolve_no_competition` for the 70S row, and **the special-case is only
needed if a future fixture rebuild splits ribosome assembly out from the
unified-balance table** (which Karr's MATLAB does, and which D.3/D.4 may
re-introduce). For D.2 v2 we keep the special branch as a one-line guard
against that future rebuild.

### 3.6 Mass balance & emit

```python
def _emit_update(self, new_complexes, byprod_delta, cofactor_delta, pool_after):
    return {
        "complex":    {"counts": {wid: int(n) for (wid, _comp), n in new_complexes.items()}},
        "protein":    {"counts": self._monomer_deltas_from_pool(pool_after)},
        "rna":        {"counts": self._rna_deltas_from_pool(pool_after)},
        "substrates": {**byprod_delta_to_substrate_deltas(byprod_delta),
                       **cofactor_delta_to_substrate_deltas(cofactor_delta)},
    }
```

All four output ports use **`accumulate` updaters** (matching M3's
substrate convention). The `complex.counts` port uses `set` semantics in
the same style as `rna.counts` / `protein.counts` (chassis convention) —
D.2 emits the **delta** as `accumulate` and chassis state holds the
running count. Either choice is mechanically valid; we choose
**`accumulate`** to mirror M3's pattern and avoid double-bookkeeping.
Final selection is an implementation-PR decision; the doc records the
preference.

---

## 4. Composition data — gotchas re-verified against fixture

### 4.1 Counts (computed live from `karr_protein_complexes.json`)

| Metric                                                | Value                            |
|-------------------------------------------------------|----------------------------------|
| `n_complexes`                                         | **201**                          |
| Complexes with ≥1 monomer subunit                     | 172                              |
| Complexes with ≥1 sub-complex                         | 36 (drives topo order)           |
| Complexes with ≥1 metabolite cofactor                 | 22                               |
| Complexes with ≥1 prosthetic group                    | 5                                |
| Complexes with ≥1 RNA subunit                         | 4 (16S/23S/5S rRNA, RNase P)     |
| Complexes with **negative** coefs (byproducts)        | **20** (enumerated §4.4)         |
| Formation compartment = `c` (cytosol)                 | 174                              |
| Formation compartment = `m` (membrane)                | 27                               |
| Complexes with non-empty `activation_rule`            | 7 (6 distinct rules, all TRUE in baseline) |

### 4.2 Activation rules — pinned TRUE for D.2

| Rule                                                                     | Affected complexes |
|--------------------------------------------------------------------------|--------------------|
| `!ciprofloxacin & !difloxacin & !sparfloxacin`                           | DNA_GYRASE, DNA_GYRASE_CIPROFLOXACIN_2 |
| `!gentamicin & !spectinomycin & !streptomycin & !tetracycline`           | RIBOSOME_30S |
| `!azithromycin & !chloramphenicol & !clarithromycin & !clindamycin & !erythromycin & !lincomycin & !pristinamycin` | RIBOSOME_50S |
| `G6P>5`, `temperature>=43`, `PI>20`                                      | three regulators (one each) |

In wild-type Karr baseline all stimuli evaluate the rules to TRUE; the
v2 process implements rule evaluation but pins the inputs to TRUE
defaults. Stimulus dynamics are a Phase G concern. v1's mini-parser
design carries forward; not duplicated here.

### 4.3 Topology (DAG, verified acyclic)

`subcomplexes` introduces inter-complex dependencies. Key chains:

- `RIBOSOME_70S` ← `RIBOSOME_30S_IF3` + `RIBOSOME_50S`.
- `RIBOSOME_30S_IF3` ← `RIBOSOME_30S` + `MG_173_MONOMER` (IF3).
- `RNA_POLYMERASE_HOLOENZYME` ← `RNA_POLYMERASE` + sigma monomer.
- `DNA_POLYMERASE_2CORE_BETA_CLAMP_GAMMA_COMPLEX_PRIMASE` ←
  `DNA_POLYMERASE_CORE` × 2 + `DNA_POLYMERASE_GAMMA_COMPLEX` + 2 monomers.
- 8 FtsZ activated polymers (2-mer through 9-mer) chain off
  `MG_224_MONOMER_GTP`.

D.2 must Kahn-sort at construction time and **fail loudly** if the DAG
cycle assertion ever fires (would indicate a fixture bug).

### 4.4 The 20 byproduct-emitting complexes (re-verified from fixture)

These complexes carry negative-coefficient entries in
`metabolites`/`prosthetic`. Karr convention: negative coef = **produced**
as a byproduct of assembly. D.2 emits them to the corresponding
`substrates[(wid, comp)]` slot via the `byprod_delta` channel. **No
silent drops.** If the destination key is absent from the chassis store,
fail hard (do not warn-and-skip — that's how the v1 design lost mass).

| Complex                              | Byproducts (wid coef / compartment)                             |
|--------------------------------------|-----------------------------------------------------------------|
| `MG_102_DIMER_ox`                    | H −4 / c                                                        |
| `MG_124_MONOMER_ox`                  | H −2 / c                                                        |
| `MG_127_MONOMER_ox`                  | H −2 / c                                                        |
| `MG_224_9MER_GDP`                    | H −9 / c, PI −9 / c                                             |
| `MG_229_231_TETRAMER_ox`             | H −4 / c                                                        |
| `MG_239_HEXAMER`                     | MG −1 / c                                                       |
| `MG_271_272_273_274_192MER_ox`       | H −24 / c                                                       |
| `MG_287_MONOMER_ACP`                 | H −1 / c, PAP −1 / c                                            |
| `MG_287_MONOMER_ddcaACP`             | AMP −1, H −1, PAP −1, PPI −1 (all / c)                          |
| `MG_287_MONOMER_hdeACP`              | AMP −1, H −1, PAP −1, PPI −1 (all / c)                          |
| `MG_287_MONOMER_myrsACP`             | AMP −1, H −1, PAP −1, PPI −1 (all / c)                          |
| `MG_287_MONOMER_ocdcaACP`            | AMP −1, H −1, PAP −1, PPI −1 (all / c)                          |
| `MG_287_MONOMER_octeACP`             | AMP −1, H −1, PAP −1, PPI −1 (all / c)                          |
| `MG_287_MONOMER_palmACP`             | AMP −1, H −1, PAP −1, PPI −1 (all / c)                          |
| `MG_287_MONOMER_tdeACP`              | AMP −1, H −1, PAP −1, PPI −1 (all / c)                          |
| `MG_295_MONOMER_ox`                  | H −2 / c                                                        |
| `MG_367_DIMER`                       | MG −1 / c                                                       |
| `MG_427_DIMER_ox`                    | H −4 / c                                                        |
| `MG_454_DIMER_ox`                    | H −4 / c                                                        |
| `MG_457_HEXAMER`                     | ZN −1 / c                                                       |

Distinct byproduct WIDs (with #complexes that emit them): H (17), PAP
(8), AMP (7), PPI (7), MG (2), PI (1), ZN (1). All seven are in M1's
585-substrate vocabulary, so the chassis store has destination keys for
all of them.

### 4.5 The chaperones-field corruption (D.3 problem, **not D.2's**)

`MG_392_393_21MER` has 46 entries in its `chaperones` field, but the
entries are **metabolite WIDs** (G6P, ARG, ASP, AMP, CO2, HDCA, GLU,
HIS, lomefloxacin, m2G, …). This is a fixture-build bug in
`karr_native_ingest_complexes.py` — it flattened the wrong column from
the KB struct array. D.2 v2 **does not consume `chaperones`** (Q2 puts
folding/chaperone routing in D.3), so this corruption does not block D.2.

D.3's prerequisite: re-build the fixture with the correct column
selection, OR add a one-shot scrub script. Recorded in §8.

---

## 5. Vivarium Process spec — verified against current chassis

### 5.1 Class & file

```
opencell/processes/protein_complex_assembly.py
  class ProteinComplexAssemblyProcess(Process):
      defaults = {
          "fixture_path": "data/karr_fixtures/karr_protein_complexes.json",
          "rng_seed": 0,
          "n_mc_iterations_max": 10_000,
          "activation_overrides": {},            # {complex_wid: bool}
          "time_step": 1.0,                      # seconds
          "substrate_default": _M1_SUBSTRATE_DEFAULT,
      }
```

### 5.2 Ports (matched to current chassis schema)

Verified by reading `opencell/vivarium/karr_composite.py` (lines 100–272)
and `opencell/vivarium/karr_m{2,3}.py`. Current chassis uses the
following shared stores:

| Store              | Owner so far          | D.2's role          |
|--------------------|-----------------------|---------------------|
| `protein.counts`   | M3 writes (set)       | D.2 reads (subunit pool); writes negative deltas (`accumulate`) for monomers consumed. |
| `rna.counts`       | M2 writes (set)       | D.2 reads rRNA / RNase-P RNA subunits; writes negative deltas for those consumed. |
| `substrates`       | M1/M2/M3 (accumulate) | D.2 reads metabolite cofactors; writes negative deltas (cofactor consumption) and positive deltas (byproducts). |
| **`complex`** ←(new) | D.2 owns              | D.2 writes mature complex deltas (`accumulate` per §3.6); future M5 / M2v2 / M3v2 can read for routing into their `bound` pools. |

`complex` is a **new** top-level store. Schema by analogy with `protein`:

```python
def ports_schema(self) -> dict[str, Any]:
    return {
        "protein":    {"counts": {pid: {"_default": 0, "_emit": True,
                                        "_updater": "accumulate"}
                                  for pid in self._monomer_subunit_wids}},
        "rna":        {"counts": {rid: {"_default": 0, "_emit": True,
                                        "_updater": "accumulate"}
                                  for rid in self._rna_subunit_wids}},   # 4 rRNAs
        "substrates": {sid: {"_default": self.params["substrate_default"],
                             "_emit": True, "_updater": "accumulate"}
                       for sid in self._substrate_wids},
        "complex":    {"counts": {cid: {"_default": 0, "_emit": True,
                                        "_updater": "accumulate"}
                                  for cid in self._all_201_complex_wids}},
    }
```

D.2's reads are **negative-delta** writes back to the same store on the
same step (Vivarium's standard pattern when a process both consumes and
produces from a single store; M2 already does this for the substrate
store).

### 5.3 Topology (proposal for chassis composer)

```python
# Conceptual addition to build_karr_m1_m2_m3_engine after D.2 lands:
processes = {
    "m1_karr": m1_proc, "m2_karr": m2_proc, "m3_karr": m3_proc,
    "d2_complex": d2_proc,
}
topology = {
    "m1_karr": m1_topo, "m2_karr": m2_topo, "m3_karr": m3_topo,
    "d2_complex": {
        "protein":    ("protein",),
        "rna":        ("rna",),
        "substrates": ("substrates",),
        "complex":    ("complex",),
    },
}
initial_state = {..., "complex": {"counts": {wid: 0 for wid in all_201_wids}}}
```

The composer change is documented here but **not implemented in this
PR** (doc-only deliverable).

### 5.4 Order of execution

D.2 runs after M3 within a 1-second tick: M3 publishes monomers, D.2
consumes them. Vivarium's "unique update" topology resolution handles
this naturally because M3 and D.2 share `protein.counts` and Vivarium
queues writers. No explicit `next_update_priority` needed.

### 5.5 Cold-start

v1's "cold-start hack" doesn't establish steady state and was flagged
HIGH-3. **Replacement:** the chassis seeds `complex.counts` from the
Karr snapshot (`State_Mass.dump.complex.counts[matureIndexs, :]`,
summed across compartments) at engine construction time, using the same
`_M1_SUBSTRATE_DEFAULT`-style default machinery already used for `rna`
and `protein`. This is **not** a workaround — it is the same approach
M2 and M3 already use (`rna_init = m2_model.counts_mature[i, condition]`,
`prot_init = m3_model.counts_mature[i]`). D.2 simply adds
`complex_init = mature_counts_per_wid[i]`. No bootstrap circularity:
Karr's snapshot already has consistent monomer + complex steady-state
values, so the first tick's solver is presented with a fully-formed pool.

---

## 6. Oracle plan (post-Q1 hybrid staged)

### 6.1 D.2-unit oracles (this PR's test deliverables, run at impl-PR time)

| Oracle                         | Test file                              | Tolerance                          | Notes |
|--------------------------------|----------------------------------------|------------------------------------|-------|
| Conservation                   | `tests/d2/test_complex_assembly.py::test_conservation` | exact (integer) | For each step: Σ subunits_consumed × C[:, cx] == Σ new_complexes × subunit-stoich. Negative pools forbidden. |
| Topo-ordering                  | `tests/d2/test_complex_assembly.py::test_topo_order`   | exact            | Synthetic fixture: A depends on B; assert B is built before A in the same tick. Inspect internal call ordering via a hook. |
| Shared-subunit competition     | `tests/d2/test_competition.py`         | per-Karr (network-level)           | Synthetic 2-complex fixture sharing one scarce monomer; assert allocation matches Karr's `buildProteinComplexs_montecarlokinetic` over N=50 seeds, median ratio. |
| Byproducts                     | `tests/d2/test_byproducts.py`          | exact (integer)                    | For each of the 20 complexes in §4.4: forming N copies emits exactly `−coef × N` of the byproduct WID into `substrates`. No silent drops. Hard-fail when destination key missing. |
| Mature-subset snapshot         | `tests/d2/test_complex_assembly.py::test_mature_subset` | per-complex tolerance per phenotype convention (default ±20 % on counts ≥ 10, ±2 absolute on counts < 10) | 158 complexes — manifest in `data/karr_fixtures/d2_mature_subset.json`. |
| Aggregate dry mass             | `tests/d2/test_complex_assembly.py::test_aggregate_drymass` | ±15 % on cytosol total (1.20 × 10⁻¹⁵ g), ±20 % on membrane (3.04 × 10⁻¹⁶ g) | Sum `mature_counts · molecularWeights / N_A` per compartment, compare to `State_Mass.dump.complex.dryWeight[c]` and `[m]`. |

**Mature-subset choice — threshold and count:** computed live from
`sim_fitted_targeted.mat::data.states.State_Mass.dump.complex.counts`
projected through `matureIndexs` and summed across compartments:

| Threshold            | # complexes |
|----------------------|-------------|
| `mature_total ≥ 10`  | 136         |
| `mature_total ≥ 2`   | 156         |
| **`mature_total ≥ 1`** (chosen) | **158** |
| `mature_total == 0`  | 43          |

**Choice: threshold = 1 → 158 complexes.** This is fewer than the
"~191" estimate in the user brief; the discrepancy comes from the brief
rounding upward and from 43 complexes whose mature snapshot count is
genuinely 0 (some are pure-bound entities like RIBOSOME_70S, others are
oxidised/regulatory minor forms). The 43 zero-mature complexes are
**still tested** for conservation/topo/byproducts but excluded from the
per-complex snapshot oracle. The exhaustive list lands as
`data/karr_fixtures/d2_mature_subset.json` (committed in this PR).

**Snapshot-form sanity (one-time assertion at fixture-load):**
nascent_total == 0, misfolded_total == 0, damaged_total == 0,
inactivated_total == 37 in the snapshot. D.2 v2 does not generate
nascent/misfolded/damaged forms (those are D.3); inactivated is read
but not re-derived.

### 6.2 Integration-level oracles (deferred to v2-swap + M5)

For 10 bound-heavy anchors the snapshot's mature count is small
(0–8) but bound count is large (2–78). D.2 alone cannot reproduce the
total because the bound pool is owned by the consumer process. The
integration oracle `D.2.mature + Σconsumers.bound ≈ snapshot.total`
becomes meaningful once those consumers exist.

The 10 anchors (re-derived from
`State_Mass.dump.complex.counts[boundIndexs, :].sum(axis=1)`):

| #  | Complex WID                       | Karr mature | Karr bound | Consumer (where `bound` will live)     |
|----|-----------------------------------|-------------|------------|----------------------------------------|
|  1 | `MG_213_214_298_6MER_ADP`         | 3           | **78**     | DNA repair (Phase F)                   |
|  2 | `MG_089_DIMER`                    | 65          | 68         | DNA repair / mismatch (Phase F)        |
|  3 | `MG_433_DIMER`                    | 54          | 68         | DNA replication (M5)                   |
|  4 | `MG_451_DIMER`                    | 71          | 68         | DNA replication (M5)                   |
|  5 | `RIBOSOME_70S`                    | **0**       | 56         | Translation (M3v2)                     |
|  6 | `DNA_GYRASE`                      | 3           | 47         | DNA replication / topology (Phase F)   |
|  7 | `RNA_POLYMERASE`                  | **0**       | 40         | Transcription (M2v2)                   |
|  8 | `MG_469_1MER_ATP`                 | 2           | 23         | DnaA replication-origin firing (M5)    |
|  9 | `MG_469_7MER_ATP`                 | 0           | 4          | DnaA replication-origin firing (M5)    |
| 10 | `MG_428_DIMER`                    | 8           | 2          | Cell division (Phase F)                |

The user-brief estimate of "10 anchors" is exactly correct at
`bound ≥ 1` (or `bound ≥ 2`). At `bound ≥ 5` the count drops to 8
(MG_469_7MER_ATP + MG_428_DIMER fall out). We carry **all 10**.

These tests will be authored at D.2 implementation time but marked:

```python
@pytest.mark.xfail(
    reason="D.2 emits mature only (Q1 hybrid staged). "
           "Bound pool owned by consumer process; oracle becomes valid "
           "once v2-swap (M2v2/M3v2) and M5 land.",
    strict=False,
)
def test_anchor_total_includes_bound(...):
    ...
```

The marker is **lifted automatically** once both consumer processes
exist (we'll detect via `pytest.importorskip("opencell.processes.m5_replisome")`).

### 6.3 v1 reasoning explicitly dropped

v1 included an "assembly_rate × mean_lifetime ≈ snapshot.total" check
that motivated several of its tolerances. **Drop it everywhere.**
Karr's complex assembly is not a fitted-rate birth-death process — it
is subunit-limited completion with mostly-infinite or 72 000 s
half-lives (`State_Mass.dump.complex.halfLives` array). The argument
breaks down because:

1. There is no fitted formation rate in the source — the MATLAB header
   explicitly says "complexation … proceeds to completion rapidly".
2. Half-lives are too long for a steady-state rate balance to give
   anything but `count ≈ produced` over any plausible test window.
3. The check was used to paper over per-complex MC error (BLOCKER 3).

v2's mature-subset + dry-mass oracles replace it cleanly.

---

## 7. Test plan summary & file targets

| File                                    | Purpose                              | Conflict check |
|-----------------------------------------|--------------------------------------|----------------|
| `tests/d2/test_complex_assembly.py`     | Conservation, topo, mature-subset, dry-mass oracles. | New directory `tests/d2/` — confirmed absent in repo (`tests/` has `phaseB`, `phaseC`, `phaseD0` etc., no `d2`). |
| `tests/d2/test_byproducts.py`           | Byproduct emission for the 20 complexes.             | New file.      |
| `tests/d2/test_competition.py`          | Synthetic shared-subunit fixture; network-level MC.  | New file.      |
| `tests/d2/test_anchor_integration.py`   | The 10 bound-heavy anchors; **xfail-strict=False** until M5 + v2-swap. | New file.      |

All four files are authored at D.2 implementation time (next PR). This
doc-only PR adds none of them.

---

## 8. Known issues / tech debt

| ID  | Issue                                                                   | Owner   | Severity |
|-----|-------------------------------------------------------------------------|---------|----------|
| TD1 | `MG_392_393_21MER.chaperones` field is corrupted — contains 46 metabolite WIDs (G6P, ARG, ASP, AMP, CO2, lomefloxacin, m2G, …) instead of chaperone protein WIDs. Root cause: wrong column flattened in `scripts/karr_native_ingest_complexes.py`. | **D.3**   | Med — D.3 will read this field; D.2 ignores it (Q2). |
| TD2 | Bound-heavy anchor oracle gap: 10 anchors (incl. `RIBOSOME_70S`, `RNA_POLYMERASE`, `DNA_GYRASE`) cannot be checked end-to-end until the bound side lives in M2v2/M3v2/M5. | v2-swap + M5 | Med — `xfail` until then. |
| TD3 | `complex` is a new chassis store. Composer wiring lives in a separate PR after this design lands. | D.2 impl PR | Low. |
| TD4 | `simplify_cells=True` in scipy still leaves 1206-row string arrays (`wholeCellModelIDs`, `names`) deeply nested when read straight from `sim_fitted_targeted.mat`; archive flattening (the existing `karr_archive_strings.json` path) is the workaround. Anyone debugging the snapshot directly should use the existing fixture's WID order (sort `karr_protein_complexes.json::complexes` by `idx_1based`), which is verified equal to `matureIndexs`-projected ordering. | impl    | Low (documented). |
| TD5 | Snapshot mature totals: this PR found 4006 mature, 454 bound, 37 inactivated, 0 nascent/misfolded/damaged across 1206×6. The user-brief stated "3264 mature"; the difference is non-trivial but does not change Q1's strategy. | doc only | None — captured in `d2_mature_subset.json`. |

---

## 9. Risk register

| #  | Risk                                                                                                  | Sev | Mitigation                                                                                           |
|----|-------------------------------------------------------------------------------------------------------|-----|------------------------------------------------------------------------------------------------------|
| R1 | Network-level MC non-determinism flakes oracle tests.                                                 | Med | Run N=50 seeded numpy.Generator instances; assert on median per Karr-convention; tolerance per §6.1. |
| R2 | DAG cycle introduced by future fixture rebuild.                                                       | Low | Hard-fail at process construction via Kahn's algorithm; pinned unit test enumerates today's DAG.     |
| R3 | New complex store missing from initial_state on chassis swap.                                         | Med | Init from Karr snapshot (§5.5); composer asserts initial_state has all 201 wids.                     |
| R4 | Iter-cap (10 000) exceeded in pathological pool starvation.                                           | Low | Once-per-step warning; profile during impl; raise cap if needed (Karr's WT case converges in ~few hundred). |
| R5 | Byproduct destination WID missing from M1's 585-substrate vocabulary (would silently drop mass).      | Low | All 7 distinct byproduct WIDs (H, AMP, PAP, PPI, MG, PI, ZN) confirmed present in `m1_model.raw["ids"]["substrate_wcm_585"]`. Implementation hard-fails on KeyError, never warn-and-skip. |

---

## 10. Open questions for human

After this rework, **Q1 (oracle strategy) and Q2 (scope) are resolved**.
The two remaining genuine open questions for reviewer decision:

1. **`complex.counts` updater semantics: `accumulate` (D.2 emits delta;
   chassis sums) vs. `set` (D.2 publishes the full new count; chassis
   replaces).** §3.6 / §5.2 propose `accumulate` to match M3's substrate
   pattern; M2/M3 themselves use `set` for `rna.counts`/`protein.counts`
   so there's no in-repo precedent that makes the choice obvious. A 1-line
   answer either way is sufficient.

2. **D.4 vs. M6 home for ProteinActivation.** The Q2 split is firm —
   D.2 ships assembly-only — but reviewer should pick the deferral target
   so the next planning cycle has the right slot. (No effect on this
   PR's deliverable.)

There is **no Q3+**. v1 had five open questions; three are closed by
Q1/Q2 and the snapshot path verification, the remaining two are listed
above.

---

## 11. Verification log (this PR)

The following were checked at design-time and recorded for the impl PR:

- ✅ All 22 ARCHIVE_SPEC paths in §2.3 exist in
  `data/karr_archive/full_inventory.json` with the listed shapes/dtypes
  (re-confirmed live; total entries = 4837).
- ✅ Chassis port names verified by reading
  `opencell/vivarium/karr_composite.py`, `karr_m2.py`, `karr_m3.py`.
  Existing stores: `protein`, `rna`, `substrates`,
  `metabolic_reaction`, optional `m1_pools`,
  `m1_dynamic_diagnostics`. New store: `complex`.
- ✅ Bound-heavy anchor list re-derived from
  `sim_fitted_targeted.mat::State_Mass.dump.complex.counts[boundIndexs]`
  using `scipy.io.loadmat(simplify_cells=True)`. **10 anchors** at
  `bound ≥ 1` threshold; matches GPT-5.4's claim. Full list in §6.2.
- ✅ Mature-subset count = **158** at `mature_total ≥ 1` threshold
  (43 complexes have zero mature count in the snapshot). Manifest in
  `data/karr_fixtures/d2_mature_subset.json`.
- ✅ 20 byproduct-emitting complexes enumerated from
  `karr_protein_complexes.json` (§4.4). Distinct byproduct WIDs: H, PAP,
  AMP, PPI, MG, PI, ZN — all present in M1's 585-substrate vocabulary.
- ✅ `MG_392_393_21MER.chaperones` corruption confirmed (46 metabolite
  WIDs); flagged as TD1 for D.3.
- ✅ DAG of `subcomplexes` is acyclic in the current fixture.
- ✅ Aggregate complex dryWeight: 1.2009 × 10⁻¹⁵ g (cytosol) +
  3.043 × 10⁻¹⁶ g (membrane) = 1.5053 × 10⁻¹⁵ g total. The user-brief
  "≈ 1.20 × 10⁻¹⁵ g (~38 % of cellDry)" matches the cytosol-only number.

---

## Appendix A. v1 → v2 diff summary

| v1 problem (rubber-duck)                                  | v2 fix                                                                |
|-----------------------------------------------------------|------------------------------------------------------------------------|
| BLOCKER 1: ribosome-cost data path wrong                  | §2.4 — costs already in `karr_protein_complexes.json`; no new fixture needed. |
| BLOCKER 2: oracle path wrong + counts unsupported         | §2.3 — 22 ARCHIVE_SPEC extensions for `State_Mass.dump.complex.*`; §6.1 / §6.2 recompute anchors. |
| BLOCKER 3: per-complex MC collapses Karr physics          | §3.4 — network-level MC restored; per-complex collapse explicitly rejected. |
| HIGH 1: activation rules half-baked                       | §1.2 — out of scope (Q2 → D.4/M6). Activation gating in D.2 stays a TRUE-pinned guard only. |
| HIGH 2: chassis store mismatch                            | §5.2 — verified port names against current chassis; new `complex` store added explicitly. |
| HIGH 3: cold-start hack                                   | §5.5 — replaced with the same Karr-snapshot-seeding pattern M2/M3 already use. |
| HIGH 4: scope creep (folding/activation)                  | §1.2 — Q2 split, deferred to D.3/D.4/M6.                              |
| MEDIUM: `MG_392_393_21MER` chaperones corruption          | §4.5 / §8 TD1 — owned by D.3, no longer D.2's blocker.                |
| MEDIUM: byproducts silently dropped                       | §3.6 / §4.4 — hard-fail on missing key; all 7 destination WIDs verified in M1's vocab. |
| 5 open questions                                          | 2 remain, both implementation-detail (§10).                            |
