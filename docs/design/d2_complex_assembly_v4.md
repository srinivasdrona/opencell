# Phase D.2 — `MacromolecularComplexation` + `RibosomeAssembly`: Design Document v4 + Execution Plan

| Field | Value |
|---|---|
| Status | DESIGN v4 — supersedes v1/v2/v3; awaiting v4 cross-model critique |
| Branch | `agent/d2-design-v4` (to be created from current `agent/d2-design-v3`) |
| Supersedes | `docs/design/d2_complex_assembly.md` (v3 on this branch — to be replaced or annotated) |
| Critique antecedent | `docs/design/d2_v3_critique_2026-05-22.md` (Opus 4.6 + GPT-5.5 convergent REWORK) |
| Source-truth evidence | `artifacts/d2_v3_evidence.json` + `artifacts/d2_v3_evidence.md` (to be regenerated with full 7-process exclusion) |
| MATLAB source | `data/karr_fixtures/per_process/{RibosomeAssembly,MacromolecularComplexation,ProteinComplex,Metabolite}_flat.mat` |
| Critical path | Unblocks p10 (mass), p5/p8 (mature 30S/50S/RNAP pools); v2-chassis-swap and M5 replisome downstream |

---

## 0. Executive summary

D.2 v4 builds the mature form of every Karr protein complex owned by `Process_MacromolecularComplexation` (882 form-entries, ≈147 unique complex WIDs) plus the two ribosomal subunits `RIBOSOME_30S` and `RIBOSOME_50S` owned by `Process_RibosomeAssembly`. **D.2 does not build `RIBOSOME_30S_IF3` or `RIBOSOME_70S`** — both are `Process_Translation`-owned per the source-truth fixture, deferred to M3v2.

The algorithm is a topologically-ordered greedy stoichiometric solver with Karr's collision-theory competition resolution for shared subunits, plus a randomized-order 30S/50S assembly path with verified GTPase catalysts (2 GTPases for 30S, 4 for 50S).

The emit contract uses **signed per-key accumulation** (single dict per port leaf, signed integer deltas) and emits **one signed `metabolite_delta`** covering both byproducts produced AND cofactors consumed. Mass conservation is a hard test invariant, not a comment.

The updater-conflict with M2/M3 (which currently use `_updater: set` on `rna.counts` / `protein.counts`) is resolved by **the one-tick-lag pattern**: D.2 reads previous-tick monomer/RNA counts, writes consumption to a separate `d2_consumed_*` port, and the chassis composer reconciles at tick boundary. This preserves M2/M3 semantics and tests. A documented migration path exists to free/bound-decomposition (Option (c)) when M5/M6 force it.

The oracle is **hybrid staged**: D.2-unit tests check mature-only mass aggregates (1.1549598107588903e-15 g target) and per-complex snapshot for the 158-mature subset. Integration tests (`D.2.mature + Σ_consumers.bound ≈ snapshot.total`) are deferred to v2-swap + M5.

The document **commits to** `_updater: "accumulate"` for D.2's output ports. The hedge is gone.

The deliverable is the v4 design doc, a regenerated evidence extractor output, a verified snapshot-protein-counts check, and a section-by-section v3→v4 propagation checklist. **No code, no tests** in the design PR. Implementation is the next PR (see §13 Execution Plan).

---

## 1. v3 → v4 supersession ledger

Every v3 section is in one of three states. **This ledger is the propagation contract for v4.**

| v3 Section | v4 status | Action |
|---|---|---|
| §0 Executive summary | **REWRITTEN** | Drop 70S claims; commit to one-tick-lag; commit to `accumulate` |
| §1.1 Scope | **PRESERVED** | v3's whitelist + exclusion list was correct |
| §1.2 Out of scope | **PRESERVED** | Add `RIBOSOME_30S_IF3` / `RIBOSOME_70S` (deferred to M3v2) |
| §1.3 Phenotypes unblocked | **CLARIFIED** | p7 (70S) removed from D.2's list; moves to M3v2 |
| §2.1–§2.3 Inputs / Archive spec | **PRESERVED** | 22 ARCHIVE_SPEC extensions still required |
| §2.4 Ribosome cost data | **REWRITTEN v4** | 30S = 2 GTPases (Era, RbfA); 50S = 4 GTPases (EngA, EngB, Obg, RbgA); no 70S |
| §3.1 Pre-computation | **REWRITTEN v4** | `is_ribosome_assembly` flag list shrinks to 2 (30S, 50S) |
| §3.2 Per-step evolveState | **CLARIFIED** | Add explicit "read previous-tick monomer counts" comment |
| §3.3 No-competition branch | **PRESERVED + EXAMPLE** | Add worked numeric example |
| §3.4 Competition branch | **PRESERVED + EXAMPLE** | Add worked example with 2-complex toy + concrete MC iteration |
| §3.5 Ribosome-assembly branch | **REWRITTEN v4** | 30S and 50S only; randomized order; per-subunit GTPase catalyst guards |
| §3.6 Mass balance & emit | **REWRITTEN v4** | Signed per-key accumulator; single metabolite_delta; worked example uses D.2-owned subcomplex |
| §4.1 Counts | **CORRECTED** | Clarify 147 unique D.2-owned vs 201 total; 525 row count is monomers not subunits |
| §4.2 Activation rules | **PRESERVED** | Pin TRUE; defer to Phase G |
| §4.3 Topology DAG | **PRESERVED + VERIFIED** | 60 edges, acyclic; 9 subcomplex-bearing in 158-mature subset |
| §4.4 Byproduct sign convention | **CLARIFIED** | One-sentence canonical statement |
| §4.5 Chaperone corruption | **PRESERVED** | D.3's problem |
| §5.1 Class / file | **PRESERVED** | `opencell/processes/d2_complex_assembly.py` |
| §5.2 Ports | **REWRITTEN v4** | New ports: `protein.counts` (read-only), `rna.counts` (read-only), `complex.counts` (read+write D.2-owned subset only), `substrates.counts` (write metabolite_delta), `d2.consumed_monomers` (write — new), `d2.consumed_rnas` (write — new) |
| §5.3 Topology | **REWRITTEN v4** | Chassis composer wiring with one-tick-lag reconciliation |
| §5.4 Order of execution | **REWRITTEN v4** | Drop "Vivarium handles naturally" claim; explicit lag semantics |
| §5.5 Cold start | **REWRITTEN v4** | Assertion-based: \|D.2 deltas\| < tol at t=1; verification script reference |
| §6.1 D.2 unit oracles | **REWRITTEN v4** | Per-compartment mature-only targets; regenerated by extractor |
| §6.2 Integration oracles | **PRESERVED** | xfail until consumers ship |
| §6.3 v1 reasoning dropped | **PRESERVED** | Historical note |
| §7 Test plan | **EXPANDED** | Add the v4-required tests: conservation invariant; one-tick-lag determinism; updater-conflict regression |
| §8 Known issues | **PRESERVED + ADD** | Add: snapshot free-only assumption; one-tick-lag migration to (c) |
| §9 Risk register | **EXPANDED** | Add M5/M6 forcing function for free/bound decomposition |
| §10 Open questions | **CLOSED** | Q1 → `accumulate`; Q3 → one-tick-lag; remaining open Q deferred to M5 |
| §11 Verification log | **NEW v4** | Section-by-section propagation checklist (§3.5 propagated from §1.1 Decision (b): ✓ etc.) |
| §12 Project rule compliance | **NEW v4** | Units, reference frame, RNG spawn, DOI provenance, naked numbers — explicit |
| §13 Execution plan | **NEW v4** | Implementation phasing (see §13 below) |
| Appendix A v1→v2 diff | **PRESERVED** | Historical |
| Appendix B v2→v3 diff | **PRESERVED** | Historical |
| Appendix C v3→v4 diff | **NEW v4** | This ledger expanded |

---

## 2. Scope (v4 — final)

### 2.1 In scope

| Karr process | D.2 ownership | Form-entry count |
|---|---|---|
| `Process_MacromolecularComplexation` | YES | 882 |
| `Process_RibosomeAssembly` (30S, 50S only) | YES | 12 (of which 2 unique complex WIDs) |
| Byproduct emission for the 20 negative-coef complexes | YES (subset of MC) | — |

**D.2 unique complex WID count: ≈147** (intersection of whitelist with unique-by-WID).

### 2.2 Out of scope (deferred)

| Concern | Lands in | Why deferred |
|---|---|---|
| `RIBOSOME_30S_IF3` assembly | M3v2 | `Process_Translation`-owned in snapshot |
| `RIBOSOME_70S` joining | M3v2 | `Process_Translation`-owned; biologically translation initiation |
| ProteinFolding | D.3 | Chaperone-capacity kinetics out-of-scope per Q2 |
| ProteinActivation | D.4 or M6 | Cofactor loading beyond stoichiometric assembly |
| Chaperone routing fix | D.3 prereq | `chaperones` field corruption in JSON fixture |
| `bound` count emission | Each consumer's v2 | Per Q1 hybrid staged oracle |
| FtsZ ring, gyrase load, DnaA polymerization | F / M5 | Distinct Karr processes |

### 2.3 Phenotypes unblocked by D.2 v4

| ID | Phenotype | After D.2 v4 |
|---|---|---|
| p10 | Cell dry mass at division | Adds ≈ 1.155e-15 g mature complex mass (per-compartment from regenerated extractor) |
| p5 | RNAP free pool count | Live mature pool from D.2; bound pool stays stub until M2v2 |
| p6 | Free RNAP / sigma | Live mature pools from D.2 |
| p8 | 30S / 50S free pool | Live from D.2 directly |
| ~~p7~~ | ~~70S count~~ | **MOVED to M3v2** (Translation owns 70S assembly) |

---

## 3. Algorithm (v4)

### 3.1 Pre-computation (once at process construction)

```python
def __init__(self, parameters=None):
    super().__init__(parameters)

    # Load source-truth ownership map and filter to D.2 whitelist
    self._d2_wids: list[str] = self._load_d2_owned_complex_wids()
    # ≈147 unique WIDs after whitelist + uniqification

    # Composition matrix: subunits[i] x complexes[j] -> stoichiometric coefficient
    # Loaded from karr_protein_complexes.json + ProteinComplex_flat.mat
    self._S_protein: np.ndarray  # (n_protein_monomers, n_d2_complexes), nonneg integers
    self._S_rna: np.ndarray      # (n_rna_mature, n_d2_complexes), nonneg integers
    self._S_subcomplex: np.ndarray  # (n_d2_complexes, n_d2_complexes), nonneg integers
    self._B: np.ndarray  # (n_byproducts, n_d2_complexes), signed
                         # +produced (e.g. H+), -consumed (e.g. GTP)
                         # Sign convention §4.4

    # Topological order of D.2 complexes (subcomplex dependency)
    self._topo_order: list[int]  # 60 edges, acyclic verified

    # Ribosome assembly flag — TRUE for exactly 2 indices
    self._is_ribosome_assembly: np.ndarray  # (n_d2_complexes,) bool
    # = [True for RIBOSOME_30S, True for RIBOSOME_50S, False for all 145 others]

    # GTPase catalyst lookup (verified from RibosomeAssembly_flat.mat)
    self._gtpases_30S: list[str] = ["MG_387_MONOMER", "MG_143_MONOMER"]      # Era, RbfA
    self._gtpases_50S: list[str] = ["MG_329_MONOMER", "MG_335_MONOMER",      # EngA, EngB
                                     "MG_384_MONOMER", "MG_442_MONOMER"]    # Obg, RbgA

    # Non-biological tuning constants (project-rule classification, see §12)
    self._n_mc_iterations_max: int = 10_000  # competition MC convergence cap
    self._convergence_tol: float = 1e-9       # rate-balance tolerance
    self._time_step_s: float = 1.0            # tick length, matches chassis

    # RNG (project-rule SeedSequence pattern, see §12)
    self._seed_seq = np.random.SeedSequence(self.parameters.get("seed", 42))
    self._rng_per_step: np.random.Generator | None = None  # spawned per evolveState
```

### 3.2 Per-step `evolveState` (mirrors `MacromolecularComplexation.m` lines ~140–280)

```python
def next_update(self, timestep: float, states: dict) -> dict:
    # One-tick-lag pattern: read PREVIOUS tick's monomer/rna counts
    # The chassis composer ensures these reflect end-of-previous-tick state
    pool = {
        ("protein", wid): states["protein"]["counts"][wid] for wid in self._protein_wids
    }
    pool.update({
        ("rna", wid): states["rna"]["counts"][wid] for wid in self._rna_wids
    })
    pool.update({
        ("complex", wid): states["complex"]["counts"][wid] for wid in self._d2_wids
    })
    pool.update({
        ("substrates", wid): states["substrates"]["counts"][wid] for wid in self._substrate_wids
    })

    # Per-step RNG (SeedSequence spawn pattern, see §12)
    step_idx = int(self.parameters.get("step_count", 0))
    self._rng_per_step = np.random.default_rng(
        self._seed_seq.spawn(step_idx + 1)[-1]
    )

    # Initialize delta accumulators (signed per-key)
    deltas = {
        "complex":  Counter(),
        "protein":  Counter(),  # negative only — consumption
        "rna":      Counter(),  # negative only — consumption
        "metabolites": Counter(),  # signed — byproduct +, cofactor -
    }

    # Traverse complexes in topological order
    for c_idx in self._topo_order:
        if self._is_ribosome_assembly[c_idx]:
            # Defer to randomized-order ribosome path (§3.5)
            continue

        # Choose branch
        if self._has_subunit_competition(c_idx, pool, deltas):
            self._evolve_competition_network(c_idx, pool, deltas)
        else:
            self._evolve_no_competition(c_idx, pool, deltas)

    # Ribosome assembly: randomize order between 30S and 50S
    ribosome_idxs = [i for i, f in enumerate(self._is_ribosome_assembly) if f]
    self._rng_per_step.shuffle(ribosome_idxs)
    for c_idx in ribosome_idxs:
        self._evolve_ribosome_subunit(c_idx, pool, deltas)

    return self._emit_update(deltas)
```

### 3.3 No-competition branch (worked example)

```python
def _evolve_no_competition(self, c_idx, pool, deltas):
    """Assemble as many copies of complex c_idx as the pool allows."""
    n_max = self._max_assemblies(c_idx, pool, deltas)
    if n_max <= 0:
        return
    self._consume_subunits(c_idx, n_max, pool, deltas)
    self._produce_complex(c_idx, n_max, pool, deltas)
    self._emit_byproducts(c_idx, n_max, deltas)
```

**Worked numeric example.** Assume a complex `MG_X_DIMER` requires 2× `MG_X_MONOMER`. Initial state: `pool[("protein","MG_X_MONOMER")] = 100`. No other complex competes.

| Step | Computation | Result |
|---|---|---|
| 1. n_max | floor(100 / 2) | 50 |
| 2. consume | `deltas["protein"]["MG_X_MONOMER"] -= 100`; `pool[...] -= 100` | pool monomer = 0 |
| 3. produce | `deltas["complex"]["MG_X_DIMER"] += 50` | pool complex += 50 |
| 4. byproducts | (none for this complex) | — |

Post-step: pool consistent; deltas = `{complex: {DIMER: +50}, protein: {MONOMER: -100}}`.

### 3.4 Competition branch (worked example)

```python
def _evolve_competition_network(self, c_idx, pool, deltas):
    """Karr's collision-theory MC over shared subunits.

    For each shared subunit, compute the formation rate of each candidate
    complex via mass-action; sample one event proportional to rate; iterate
    until no candidate has nonzero rate or pool is exhausted.
    """
    candidates = self._competing_complexes_for(c_idx)
    for iteration in range(self._n_mc_iterations_max):
        rates = self._collision_rates(candidates, pool, deltas)
        if rates.sum() < self._convergence_tol:
            break
        chosen = self._rng_per_step.choice(candidates, p=rates/rates.sum())
        self._consume_subunits(chosen, 1, pool, deltas)
        self._produce_complex(chosen, 1, pool, deltas)
        self._emit_byproducts(chosen, 1, deltas)
    else:
        # Convergence failure: log + flag, do not crash
        self._log_convergence_failure(c_idx, candidates, iteration)
```

**Worked numeric example.** Two complexes compete for a shared monomer `X`:
- `C1 = X + X` (2 X → C1)
- `C2 = X + Y + GTP` (1 X, 1 Y, 1 GTP → C2 + 1 H+)

Initial pool: `X=10, Y=5, GTP=20`. Collision-theory mass-action rates:
- rate(C1) ∝ k1 · X(X-1) = k1 · 90
- rate(C2) ∝ k2 · X · Y · GTP = k2 · 1000

With k1 = k2 = 1: p(C1) = 90/1090 ≈ 0.083, p(C2) ≈ 0.917.

| Iter | Rng draw | Choice | Pool after |
|---|---|---|---|
| 1 | 0.5 | C2 | X=9, Y=4, GTP=19, H+ +=1 |
| 2 | 0.2 | C2 | X=8, Y=3, GTP=18, H+ +=1 |
| ... | ... | ... | ... |

Loop terminates when Y=0 (C2 starves) AND X<2 (C1 starves) AND all other candidates starve.

### 3.5 Ribosome-assembly branch (REWRITTEN v4 — 30S and 50S only)

**Authoritative scope:** D.2 v4 builds only `RIBOSOME_30S` and `RIBOSOME_50S`. `RIBOSOME_30S_IF3` and `RIBOSOME_70S` are NOT in D.2's whitelist (see §2.2).

```python
def _evolve_ribosome_subunit(self, c_idx, pool, deltas):
    """Assemble one ribosomal subunit (30S or 50S).

    Karr's RibosomeAssembly randomizes order between 30S and 50S within
    a tick (caller handles this via shuffle in §3.2). Each subunit has
    its own GTPase catalyst set: 2 for 30S, 4 for 50S. Catalysts are
    checked > 0 but NOT consumed (true catalysts).
    """
    wid = self._d2_wids[c_idx]
    if wid == "RIBOSOME_30S":
        gtpases = self._gtpases_30S  # 2 factors: Era, RbfA
        n_gtp_per_subunit = 2         # 2 GTP hydrolyzed (one per GTPase)
    elif wid == "RIBOSOME_50S":
        gtpases = self._gtpases_50S  # 4 factors: EngA, EngB, Obg, RbgA
        n_gtp_per_subunit = 4         # 4 GTP hydrolyzed
    else:
        raise AssertionError(f"_evolve_ribosome_subunit called on non-ribosome WID {wid}")

    # GTPase catalyst guard: each must be present (not zero)
    for gtpase_wid in gtpases:
        if pool[("protein", gtpase_wid)] <= 0:
            return  # skip this subunit's assembly this tick

    # n_max bounded by: rRNA + ribosomal proteins + GTP + H2O availability
    n_max = self._max_assemblies(c_idx, pool, deltas)
    n_max = min(n_max, pool[("substrates", "GTP")] // n_gtp_per_subunit)
    n_max = min(n_max, pool[("substrates", "H2O")] // n_gtp_per_subunit)
    if n_max <= 0:
        return

    # Consume rRNA + ribosomal proteins (from composition matrix)
    self._consume_subunits(c_idx, n_max, pool, deltas)
    # Produce the mature subunit
    self._produce_complex(c_idx, n_max, pool, deltas)
    # Energy cost: per-subunit GTPases
    gtp_total = n_max * n_gtp_per_subunit
    deltas["metabolites"][("substrates", "GTP")] -= gtp_total
    deltas["metabolites"][("substrates", "H2O")] -= gtp_total
    deltas["metabolites"][("substrates", "GDP")] += gtp_total
    deltas["metabolites"][("substrates", "PI")]  += gtp_total
    deltas["metabolites"][("substrates", "H")]   += gtp_total
    # Catalysts NOT consumed (no GTPase delta)
```

**Worked numeric example.** Pool: enough rRNA + r-proteins for 5 copies of 50S; pool[GTP]=30, pool[H2O]=40; all 4 50S GTPases present (count > 0 each).

- n_max from composition: 5
- n_max from GTP / 4 per subunit: 30 / 4 = 7 → no constraint
- n_max from H2O / 4: 40 / 4 = 10 → no constraint
- Effective n_max = 5
- GTP consumed: 5 × 4 = 20; H2O consumed: 20; GDP/PI/H produced: 20 each
- Post-step: deltas include `complex[RIBOSOME_50S]: +5`, `metabolites[GTP]: -20, H2O: -20, GDP: +20, PI: +20, H: +20`, plus all the rRNA/r-protein consumption deltas

### 3.6 Mass balance & emit (REWRITTEN v4)

**The contract:**

```python
def _emit_update(self, deltas: dict[str, Counter]) -> dict:
    """Emit signed per-key deltas.

    deltas[port] is a Counter mapping (port, wid) -> signed int.
    Returns the Vivarium update dict with _updater: accumulate for all leaves.
    """
    # Conservation check (test invariant, also active assertion in dev)
    self._assert_mass_conservation(deltas)

    return {
        "complex": {
            "counts": dict(deltas["complex"]),  # signed: + new, - consumed-subcomplex
        },
        "d2_consumed_monomers": {
            "counts": dict(deltas["protein"]),  # signed (always negative for D.2)
        },
        "d2_consumed_rnas": {
            "counts": dict(deltas["rna"]),      # signed (always negative for D.2)
        },
        "substrates": {
            "counts": dict(deltas["metabolites"]),  # signed: + byproduct, - cofactor
        },
    }
```

**Critical departures from v3:**

1. **Signed Counters, not dict-merge.** Same key formed and consumed in same tick is `formed_delta - consumed_delta`, computed correctly by Counter arithmetic. No `**plus, **minus` overwriting.

2. **Separate consumption ports `d2_consumed_monomers` / `d2_consumed_rnas`.** D.2 does NOT write to `protein.counts` or `rna.counts` directly. The chassis composer reconciles at tick boundary by subtracting D.2's consumption from M2/M3's set value (one-tick-lag pattern, see §5.3).

3. **`substrates.counts` carries one signed `metabolite_delta`** covering both byproducts produced (positive) and cofactors consumed (negative). No vanishing GTP/H2O.

**Conservation invariant (test):**

For every key `k` in `deltas["complex"]`:
- if `k` is a complex with subcomplexes, sum of consumed-subcomplex deltas in `deltas["complex"]` for those subcomplex WIDs must equal (negative) the produced-complex count × stoichiometric coefficient
- protein-monomer consumption (in `d2_consumed_monomers`) must equal Σ over produced complexes of (n_complex × monomer stoichiometry)
- substrate balance: emitted GTP delta + emitted H2O delta + emitted GDP/PI/H deltas must sum to zero net atoms (covered by Karr's pre-balanced fixture)

**Worked numeric example (D.2-owned, replacement for HOLOENZYME):**

Pick a complex from the 9 subcomplex-bearing-in-mature-subset set. **Implementer to choose deterministically at implementation time** by inspecting `data/karr_fixtures/d2_mature_subset.json` filtered to entries with `subcomplexes.length > 0`. Suggested template:

> Forming 10 copies of `EXAMPLE_TETRAMER` (which requires 2× `EXAMPLE_DIMER` + 1× ATP cofactor and produces 1× ADP + 1× PI byproducts):
>
> - `deltas["complex"]["EXAMPLE_TETRAMER"] += 10`
> - `deltas["complex"]["EXAMPLE_DIMER"] -= 20` (subcomplex consumption — signed within same Counter)
> - `deltas["metabolites"]["ATP"] -= 10` (cofactor)
> - `deltas["metabolites"]["ADP"] += 10` (byproduct)
> - `deltas["metabolites"]["PI"] += 10` (byproduct)
>
> Conservation: `EXAMPLE_DIMER` delta of -20 should equal (number of TETRAMERs formed × stoichiometric coef of DIMER in TETRAMER) = 10 × 2 = 20 ✓.

---

## 4. Composition data (preserved from v3, with corrections)

### 4.1 Counts (corrected)

| Metric | Value |
|---|---|
| Total unique complex WIDs in fixture | 201 |
| **D.2-owned unique complex WIDs** | **≈147** (whitelist ∩ unique-by-WID) |
| Of which: subcomplex-bearing | 9 (within 158-mature subset) |
| Of which: have negative-coef byproducts | 20 (enumerated §4.4) |
| Composition matrix shape | (525 monomer rows, 201 complex cols, 6 compartments) |
| ⚠ Row count 525 ≠ subunit count | 525 = total protein monomer count in chassis |

### 4.2 Activation rules (preserved)

Pin TRUE in baseline; defer stimulus dynamics to Phase G. (No change from v3.)

### 4.3 Topology DAG (preserved + verified by GPT-5.5)

- 60 edges, acyclic (verified by independent load of `MacromolecularComplexation_flat.mat`).
- 36 complexes carry subcomplexes; 9 of those in the 158-mature subset.

### 4.4 Byproduct sign convention (canonical statement)

**Convention:** Fixture stores negative coefficients for *produced* species (Karr's MATLAB convention). Solver flips to positive in `metabolite_delta`. Emit applies the positive delta to `substrates.counts` via `accumulate`. Consumed cofactors (GTP, H₂O) carry positive coefficients in fixture, solver stores them as negative in `metabolite_delta`. **End state: `metabolite_delta` is a signed dict where positive = produced/added to pool, negative = consumed/removed.**

---

## 5. Vivarium Process spec (v4)

### 5.1 Class & file

```python
# opencell/processes/d2_complex_assembly.py
from vivarium.core.process import Process

class D2ComplexAssembly(Process):
    name = "d2_complex_assembly"
    defaults = {
        "time_step": 1.0,  # seconds
        "seed": 42,
        "n_mc_iterations_max": 10_000,
        "convergence_tol": 1e-9,
    }
```

### 5.2 Ports (v4 — explicit one-tick-lag)

```python
def ports_schema(self):
    return {
        # READ ONLY — previous-tick state
        "protein": {
            "counts": {
                wid: {"_default": 0, "_updater": "set", "_emit": False}
                for wid in self._protein_wids
            }
        },
        "rna": {
            "counts": {
                wid: {"_default": 0, "_updater": "set", "_emit": False}
                for wid in self._rna_wids
            }
        },

        # READ + WRITE — D.2-owned complex WIDs only (signed accumulate)
        "complex": {
            "counts": {
                wid: {"_default": 0, "_updater": "accumulate", "_emit": True}
                for wid in self._d2_wids  # only the ~147 D.2-owned
            }
        },

        # WRITE ONLY — consumption deltas (chassis composer reconciles)
        "d2_consumed_monomers": {
            "counts": {
                wid: {"_default": 0, "_updater": "accumulate", "_emit": True}
                for wid in self._protein_wids_consumed
            }
        },
        "d2_consumed_rnas": {
            "counts": {
                wid: {"_default": 0, "_updater": "accumulate", "_emit": True}
                for wid in self._rna_wids_consumed
            }
        },

        # READ + WRITE — substrate metabolite_delta (signed)
        "substrates": {
            "counts": {
                wid: {"_default": 0, "_updater": "accumulate", "_emit": True}
                for wid in self._substrate_wids
            }
        },
    }
```

### 5.3 Chassis composer wiring (the one-tick-lag pattern)

The chassis composer (`opencell/vivarium/karr_composite.py`) wires D.2 so that:

1. **At tick t:** M2 and M3 run first, writing `set` updates to `rna.counts` and `protein.counts`.
2. **D.2 also runs at tick t** (in parallel from Vivarium's POV, but logically sees t-1 state via the next point).
3. **At end-of-tick t:** the chassis composer applies a `reconcile_d2` derived/deriver step that does:
   - `protein.counts[wid] -= d2_consumed_monomers.counts[wid]` for every wid in D.2's consumption set
   - `rna.counts[wid] -= d2_consumed_rnas.counts[wid]` for every wid in D.2's consumption set
   - Resets `d2_consumed_monomers` and `d2_consumed_rnas` to zero
4. **At tick t+1:** M2 and M3 read post-reconciliation values.

**Why this works:**
- M2/M3 keep `_updater: set` (no regression in their semantics or tests)
- D.2 writes only to its own ports + shared `substrates`/`complex` (no conflict)
- Reconciliation is deterministic and in a single derived step (one place to test)
- One-tick lag is biologically negligible at 1-second resolution for assembly kinetics (assembly time constants are seconds-to-minutes; one-second lag rounds to noise)

### 5.4 Order of execution (corrected)

The "Vivarium handles this naturally" claim from v3 §5.4 was **wrong**. Vivarium processes within the same timestep see start-of-tick state, not each other's updates. v4 replaces this with the explicit one-tick-lag + deriver pattern in §5.3. The deriver runs in Vivarium's `next_update` reconciliation phase after all `Process.next_update` calls complete.

### 5.5 Cold start (v4 — assertion-based)

**Assumption (must be verified before implementation):** Karr's snapshot `protein.counts` and `rna.counts` represent **free monomers/RNAs only** (already net of incorporation into complexes). This is the natural reading of Karr's MATLAB State model where `ProteinMonomer.counts` and `ProteinComplex.counts` are distinct state objects.

**Verification script (must run before implementation PR):** `scripts/verify_snapshot_protein_counts_are_free.py`. The script:
1. Loads the snapshot's `State_ProteinMonomer.counts`, `State_Rna.counts`, `State_ProteinComplex.counts`.
2. Computes "implied total protein" = `protein.counts` + Σ (complex × monomer-stoichiometry).
3. Checks that implied total matches the Karr paper's reported total cell protein count.
4. Emits `data/provenance/snapshot_protein_counts_verification.json` with the verification outcome.

**Cold-start test invariant:** At t=1 (first D.2 evolveState call after snapshot load), |D.2 total delta magnitude| < `tolerance` (set to 0.1% of mature complex pool). If violated, the snapshot is not at steady state OR `protein.counts` is not free-only OR composition matrix is wrong. Test name: `test_d2_cold_start_steady_state`.

---

## 6. Oracle plan (v4)

### 6.1 D.2-unit oracles (implementer PR test deliverables)

| Test | Target | Method |
|---|---|---|
| Conservation invariant | Σ inputs = Σ outputs every tick | Property test over 100 random seeds × 100 ticks each; for every key, formed - consumed - delta = 0 |
| Topology ordering | Subcomplex consumed before parent produced | Deterministic check on `_topo_order` against subcomplex DAG |
| Competition equilibrium | Mass-action rates converge | At fixed pool, MC converges in ≤ `n_mc_iterations_max` for 95% of random seeds |
| 158-mature-subset oracle | Per-complex mature count matches snapshot ±5% | Run from seeded snapshot for 100 ticks; mature counts settle within tolerance |
| Aggregate mature mass | Total mature dry mass = 1.155e-15 g ± 5% | Per-compartment regenerated by extractor (close finding Opus #5) |
| One-tick-lag determinism | Same seed → same trajectory | Run 2× with seed=42, byte-compare deltas |
| Cold-start steady state | \|delta\| < 0.1% at t=1 | See §5.5 |
| Updater-conflict regression | D.2 doesn't break M2/M3 tests | Run `tests/m2/` and `tests/m3/` after D.2 wired; expect 100% green |
| Project-rule compliance | No naked numbers in D.2 module | `tools/naked_numbers_lint.py opencell/processes/d2_complex_assembly.py` clean |

### 6.2 Integration oracles (deferred to v2-swap + M5)

| Anchor | mature (snapshot) | bound (snapshot) | Owned by |
|---|---|---|---|
| RNA_POLYMERASE | 0 | 40 | M2v2 |
| DNA_GYRASE | 3 | 47 | F (Phase F) |
| MG_469_1MER_ATP | 2 | 23 | M5 (DnaA) |
| MG_469_7MER_ATP | 0 | 4 | M5 (DnaA) |
| MG_428_DIMER | 8 | 2 | F (Phase F) |
| MG_451_DIMER | 71 | 68 | M5 (DNA repl.) |
| ~~RIBOSOME_70S~~ | ~~0~~ | ~~56~~ | M3v2 — NOT D.2 |

These get `xfail("D.2 emits mature only; bound owned by consumer")` markers until the consumer ships. Test invariant once consumers exist: `D.2.mature + Σ_consumers.bound ≈ snapshot.total` within ±5%.

---

## 7. Test plan summary

```
tests/d2/
    test_conservation_invariant.py       # property-test, 100 seeds × 100 ticks
    test_topology_ordering.py            # deterministic
    test_competition_convergence.py      # MC equilibrium under fixed pool
    test_158_mature_subset_oracle.py     # snapshot comparison
    test_aggregate_mature_mass.py        # per-compartment from extractor
    test_one_tick_lag_determinism.py     # byte-comparison
    test_cold_start_steady_state.py      # |delta| < 0.1% at t=1
    test_ribosome_30S_50S_only.py        # explicit scope guard
    test_emit_signed_counter.py          # dict-merge regression
    test_metabolite_delta_emission.py    # cofactor accounting
    test_updater_conflict_regression.py  # M2/M3 suites stay green
```

Plus implementer-level unit tests inside `tests/d2/test_solver_branches.py` for the three branches (no-comp, competition, ribosome) using the worked examples in §3.

---

## 8. Known issues / tech debt (v4)

1. **Snapshot free-only assumption** — verified via `scripts/verify_snapshot_protein_counts_are_free.py` before implementation. If violated, design needs further rework.
2. **One-tick-lag migration** — when M5/M6 force the issue, migrate to Option (c) free/bound decomposition. Specific trigger: when any process needs to read D.2's just-emitted complex counts within the same tick (e.g., M5 replisome consuming MG_469_7MER_ATP). Migration path documented but not implemented in D.2 v4.
3. **`d2_v3_evidence.json` regeneration** — extractor must emit all 7 excluded process names, not 4. Re-run as part of v4 implementation prerequisite.
4. **Chaperone field corruption** — `MG_392_393_21MER`'s `chaperones` lists 46 metabolite WIDs (clearly wrong). D.3's problem; D.2 ignores the `chaperones` field entirely.

---

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Snapshot is NOT free-only | LOW | HIGH (cold-start design broken) | Verification script in §5.5 |
| One-tick-lag introduces phenotype-visible artifact | LOW | MEDIUM | Test `test_one_tick_lag_determinism` + cross-check vs Karr phenotypes |
| M5 lands before migration to (c) is planned | MEDIUM | MEDIUM | Trigger documented in §8; M5 design must include D.2-coupling test |
| Competition MC doesn't converge for pathological pools | LOW | LOW | Convergence-failure logged + skipped; covered in `test_competition_convergence` |
| Composition matrix has off-by-one (525 vs 524) | MEDIUM | LOW | Caught by `test_conservation_invariant` |

---

## 10. Open questions (status post-v4 decisions)

| Q | v3 status | v4 disposition |
|---|---|---|
| Q1 | hybrid staged oracle | **CLOSED** — bake into §6 |
| Q2 | scope split | **CLOSED** — bake into §2 |
| Q3 | `complex.counts` updater (set vs accumulate) | **CLOSED** — commit to `accumulate` (signed) |
| Q4 | co-write semantics with M2/M3 | **CLOSED** — one-tick-lag (§5.3) |
| Q5 | RIBOSOME_30S_IF3 / 70S ownership | **CLOSED** — Decision (b): not D.2's (§2.2) |
| Q6 | Free/bound decomposition timing | **DEFERRED** — M5/M6 forcing function |
| Q7 | Cold-start free-only assumption | **DEFERRED** — verification script (§5.5) |

---

## 11. Verification log (v4 — section-by-section propagation checklist)

**This is the catch for v3's failure pattern.** Every v1.x decision propagated to every section that depends on it. Initialize unchecked; mark ✓ once verified.

| Decision | Sections that depend on it | All propagated? |
|---|---|---|
| Decision (b): D.2 doesn't own 30S_IF3 / 70S | §0, §1.1, §1.3, §2.2, §3.1, §3.5, §4.1, §5.2, §6.2 | ☐ verify before merge |
| 30S = 2 GTPases (Era, RbfA), 50S = 4 (EngA, EngB, Obg, RbgA) | §3.1, §3.5, §3.6 worked example | ☐ verify |
| Signed Counter emit (no dict-merge overwrite) | §3.3, §3.4, §3.5, §3.6, §7 test | ☐ verify |
| Single `metabolite_delta` covering byproduct + cofactor | §3.3, §3.4, §3.5, §3.6, §4.4, §5.2 | ☐ verify |
| One-tick-lag with `d2_consumed_*` ports | §3.2, §5.2, §5.3, §5.4, §7 test | ☐ verify |
| `_updater: accumulate` commitment (no hedge) | §3.6, §5.2, §10 Q3 closed | ☐ verify |
| Mature-only mass = 1.155e-15 g (not 1.505e-15) | §0, §6.1 per-compartment regenerated | ☐ verify |
| 9-way ownership histogram, 7 excluded processes | §2.1, evidence JSON regen, finding H closed | ☐ verify |
| Worked example uses D.2-owned subcomplex (not HOLOENZYME) | §3.6 | ☐ verify |
| Cold start = assertion-based + verification script | §5.5, §7 test, §8 known issues | ☐ verify |
| pint units, reference frame, RNG spawn, DOI provenance | §12 | ☐ verify |

**v4 critique reviewers (next round) MUST verify each row.**

---

## 12. Project rule compliance (v4 — new section)

### 12.1 Units & reference frame

- **Reference frame:** per-cell (whole-cell), absolute integer molecule counts. Not per-volume, not per-gDW.
- **Unit validation:** pint `Quantity` at chassis port boundaries (registered at composer level, not within D.2 itself — D.2 receives raw integers). Pint enforcement lives in `opencell.core.units`.
- **Time:** all times in seconds; `time_step = 1.0 s` (matches Karr's tick).
- **Mass targets:** grams (`1.155e-15 g` for mature-only mass). Composition coefficients are unitless integers.

### 12.2 No naked biology numbers

Every biological constant references a parameter ID:
- GTPase WIDs (Era, RbfA, EngA, EngB, Obg, RbgA) → from `data/karr_archive/karr_archive_strings.json`
- 30S/50S subunit GTPase counts (2, 4) → from `RibosomeAssembly_flat.mat` (parameter IDs `enzymeIndexs_30S_assembly_gtpase`, `enzymeIndexs_50S_assembly_gtpase`)
- Composition coefficients → from `karr_protein_complexes.json` parameter IDs
- Mass targets → from `ProteinComplex_flat.mat` aggregates

**Non-biological tuning parameters** (exempt from data-layer rule, classified at process construction):
- `n_mc_iterations_max = 10_000` — MC convergence cap, not a biological constant
- `convergence_tol = 1e-9` — numerical tolerance
- `time_step_s = 1.0` — solver tick length (matches chassis convention)

### 12.3 Stochastic RNG discipline

```python
self._seed_seq = np.random.SeedSequence(self.parameters.get("seed", 42))
# Per-step Generator via spawn
self._rng_per_step = np.random.default_rng(self._seed_seq.spawn(step_idx + 1)[-1])
# For N-ensemble tests: SeedSequence(base).spawn(N) yields N independent streams
```

No `np.random.seed()`. No unseeded distribution calls. Explicit `Generator` everywhere.

### 12.4 Evidence provenance

| Biological claim | Citation |
|---|---|
| 6 GTPases (3 per subunit pair) catalyze ribosome assembly | Karr et al. 2012, DOI:10.1016/j.cell.2012.05.044, Supplementary Methods §"Ribosome Assembly" |
| MacromolecularComplexation collision-theory mass-action | Karr 2012, Supp. Methods §"Macromolecular Complexation"; Gillespie 1977 (PMID 11748326) for theory |
| 201 protein complexes in M. genitalium | Karr 2012, Supp. Table S3 |
| Mature complex dry mass aggregate ~1.155e-15 g | Snapshot extraction (see `artifacts/d2_v3_evidence.md`); cross-check vs Karr 2012 Fig 4D |

### 12.5 Decision registry

D.2 v4's decisions land as YAML entries in `decisions/` per project rule:
- `decisions/d2-ownership-not-30S_IF3-not-70S.yaml`
- `decisions/d2-emit-signed-counter.yaml`
- `decisions/d2-one-tick-lag.yaml`
- `decisions/d2-accumulate-not-set.yaml`

---

## 13. Execution plan (the build-out)

### Phase A — v4 design approval (this PR)

| # | Step | Owner | Effort | Output |
|---|---|---|---|---|
| A1 | Write v4 design doc | this session | 2 hr | `docs/design/d2_complex_assembly_v4.md` (this file) |
| A2 | Regenerate evidence JSON (7-process exclusion) | this session | 30 min | updated `artifacts/d2_v3_evidence.json` |
| A3 | Cross-model v4 critique (Sonnet + Opus 4.6 + GPT-5.5 — three this time, since v4 is bigger) | next session | 30 min wall (parallel) | 3 critique outputs |
| A4 | Log all 3 critiques via `scripts/log_llm_interaction.py` | next session | 5 min | 3 JSONL entries |
| A5 | Synthesize critiques; either approve or v5 | next session | 1 hr | decision recorded |
| A6 | If approved: merge `agent/d2-design-v4` to main; mark `d2-design-v3-rework` done | next session | 15 min | clean main, todo done |

### Phase B — implementation prerequisites (after v4 approved)

| # | Step | Effort | Output |
|---|---|---|---|
| B1 | Write & run `scripts/verify_snapshot_protein_counts_are_free.py` | 1 hr | verification artifact |
| B2 | If B1 fails: design adjustment for cold-start (potential v5) | TBD | — |
| B3 | Add 22 ARCHIVE_SPEC extensions to extractor; regenerate archive | 2 hr | extended archive, manifest update |
| B4 | Per-complex MAT loader for composition + cost data | 2 hr | `opencell/processes/_d2_data_loader.py` |
| B5 | Decision YAML entries (4 files) | 30 min | `decisions/d2-*.yaml` |

### Phase C — implementation (the actual D.2 module)

| # | Step | Effort | Output |
|---|---|---|---|
| C1 | Module skeleton + ports_schema | 1 hr | `opencell/processes/d2_complex_assembly.py` (≈100 LOC) |
| C2 | `_evolve_no_competition` branch + unit tests | 2 hr | branch impl + `test_solver_branches.py::no_comp` |
| C3 | `_evolve_competition_network` branch + unit tests | 3 hr | branch impl + `test_solver_branches.py::competition` |
| C4 | `_evolve_ribosome_subunit` branch (30S + 50S only) + unit tests | 2 hr | branch impl + `test_solver_branches.py::ribosome` |
| C5 | `_emit_update` signed-Counter implementation + conservation test | 2 hr | emit impl + `test_emit_signed_counter.py` |
| C6 | One-tick-lag deriver in chassis composer | 2 hr | `opencell/vivarium/karr_composite.py` update + `test_one_tick_lag_determinism.py` |
| C7 | Oracle tests (5 files in `tests/d2/`) | 4 hr | full `tests/d2/` suite |
| C8 | Full test suite green | 30 min | passing CI |

**Phase C total estimate: ~17 hr of focused work** (likely spans 2–3 sessions).

### Phase D — chassis integration & validation

| # | Step | Effort | Output |
|---|---|---|---|
| D1 | Wire D.2 into `build_karr_m1_m2_m3_engine` → `build_karr_m1_m2_m3_d2_engine` | 1 hr | composer + smoke test |
| D2 | Run M2/M3 test suites with D.2 wired | 30 min | `test_updater_conflict_regression.py` |
| D3 | p10 cell-mass phenotype re-measurement (closes ~38% gap) | 1 hr | updated phase E report |
| D4 | Update plan.md: D.2 complete; v2-chassis-swap unblocked | 30 min | plan.md updated |
| D5 | Mark `d2-complex-assembly` todo done; sync both DBs | 15 min | reconciled stores |
| D6 | Blog post: "D.2 shipped" | 2 hr | new entry in `docs/blog/` |

### Phase E — post-D.2 chain reaction

D.2 unblocks the following pending todos (currently blocked):
- `v2-chassis-swap` — M2v2 + M3v2 mechanism oracles can now read live RNAP + 30S/50S pools
- `m5-replication-cellcycle` — replisome can read DnaA complex counts from D.2
- `m6-regulation` — TFs can read their complex forms from D.2

**Critical path from here:** D.2 v4 design (this PR, 1 session) → v4 critique (next session) → implementation (Phase C, 2–3 sessions) → chassis wiring (Phase D, 1 session) → v2-chassis-swap (1 week) → M5 (2–4 weeks) → M6 (1–2 weeks) → M7 validation → v1.0.

---

## Appendix A — v1 → v2 diff summary

(Preserved from v3; historical.)

## Appendix B — v2 → v3 diff summary

(Preserved from v3; historical.)

## Appendix C — v3 → v4 diff summary

**Methodology kept:**
- Bottom-up extraction from `_flat.mat` source-truth (v3's correct innovation)
- Per-machine Python extractor producing committed JSON artifact
- BLOCKER traceability table at top of doc
- Supersession-with-history (v2 sections kept marked)

**Methodology added (v4 new):**
- **Section-by-section propagation checklist** (§11) — the v3 catch
- **Cross-model v4 critique with 3 reviewers** (not 2) — wider net
- **Test invariants stated as code-checkable predicates**, not prose claims

**Substantive changes from v3:**
- Removed: 70S and 30S_IF3 from D.2 ownership
- Removed: blanket 6× ribosome cost
- Removed: dict-merge `**plus, **minus` emit pattern
- Removed: "Vivarium handles this naturally" claim
- Removed: HOLOENZYME worked example (out-of-scope)
- Added: one-tick-lag pattern with `d2_consumed_*` ports + chassis deriver
- Added: signed `metabolite_delta` (cofactors + byproducts in one signed dict)
- Added: 30S (2 GTPases) + 50S (4 GTPases) per-subunit assembly with catalyst guards
- Added: explicit §12 project rule compliance section
- Added: §13 execution plan with phased estimates
- Added: §11 verification log as propagation contract

---

*End of D.2 v4 design + execution plan. Ready for v4 cross-model critique (Phase A3).*
