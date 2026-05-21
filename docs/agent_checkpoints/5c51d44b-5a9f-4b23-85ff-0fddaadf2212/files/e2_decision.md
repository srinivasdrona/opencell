# E.2 Decision Artifact — D.2 vs M5 vs v2 mechanics

Status: decision artifact (not implementation).
Inputs: 10-phenotype matrix from `data/karr_fixtures/karr_phenotype_targets.json`
+ phenotype harness in `tests/phaseE/test_karr_phenotypes.py` (commits
`c12d68f`, `f94f5eb`, `65ca7d8`, `e6d748a`).

## Phenotype state today (post m2-counts-fix)

| #  | name                          | category         | status   | meaning                                                              |
|----|-------------------------------|------------------|----------|----------------------------------------------------------------------|
| 1  | growth_per_s                  | fba_prediction   | green    | Real ground-truth (within structural ceiling 0.4–1.1× target)        |
| 2  | doubling_time_h               | fba_prediction   | green    | Real (inverse of #1)                                                 |
| 3  | fba_oracle_median_log2_ratio  | fba_prediction   | green    | Real per-reaction oracle                                             |
| 4  | TX_GLCPTS uptake              | fba_prediction   | **xfail**| Structural gap — PTS routes outside FBA; needs M4–M28                |
| 5  | mRNA total                    | chassis_wiring   | green*   | Circular today (M2 v1 round-trips prescribed counts)                 |
| 6  | protein total                 | chassis_wiring   | green*   | Circular today (M3 v1 round-trips prescribed counts)                 |
| 7  | mRNA stability over 20s       | chassis_wiring   | green*   | Integrator-bug catcher; circular until v2                            |
| 8  | protein stability over 20s    | chassis_wiring   | green*   | Same                                                                 |
| 9  | per-AA pool stability         | closed_loop      | green    | Real prediction (Phase C closed loop)                                |
| 10 | cell dry mass                 | closed_loop      | **xfail**| 21% of target; missing complexes (~25%), DNA (~15%), lipid+pool (~39%) |

\* circular = round-trips a value that v1 prescribes by construction; becomes
real once mechanism-driven v2 replaces prescribed rates.

Real predictive tests today: 4 (#1, #2, #3, #9).
Xfails surfacing structural gaps: 2 (#4, #10).

## The three options

### Option A — D.2: Protein complex assembly

- **Phenotype yield:**
  - Direct: closes ~25 % of p10's mass gap (ribosomes, RNAP, replisome
    ≈ 1.0e-15 g of the missing 3.1e-15 g).
  - Indirect: enables real M2v2/M3v2 (RNAP/ribosome are *complexes*, not
    bulk prescribed rates) and is a hard prerequisite for M5 (replisome).
- **Effort: medium.** Composition is already extracted (Phase D.0+D.1,
  `karr_protein_complexes.json`, 201 complexes). Remaining work: assembly
  process (subunit counting → complex formation), wire into chassis as a
  Process, validate against Karr's complex SS counts (already in archive).
- **Risk: low.** Stoichiometric. No new physics. Closed-loop integration
  pattern is well-trodden after Phase C.

### Option B — M5: DNA replication / cell cycle

- **Phenotype yield:**
  - Direct: closes ~15 % of p10's mass gap (chromosome ~6e-16 g).
  - Indirect: cell-cycle phenotypes (replication initiation, fork
    progression). Division is **deferred** per plan (Phase 5.4 / Phase 6).
- **Effort: high.** Chromosome state, replication initiation, fork
  dynamics, dNTP coupling — all new. Hard-depends on D.2 (replisome is a
  complex).
- **Risk: medium.** Cell-cycle timing is sensitive; integrator
  interactions with other processes need care.

### Option C — v2 mechanics chassis swap (M2v2 + M3v2)

- **Phenotype yield:**
  - Direct: promotes p5, p6, p7, p8 from "circular wiring" to "real
    predictive". **4 phenotypes upgraded from circular → real.**
  - Indirect: no p10 mass progress.
- **Effort: medium.** Mechanism oracles already shipped standalone
  (commits `f9daac4` for M2 v2, `0244f36` for M3 v2). Remaining work:
  replace v1 prescribed-rate Processes in the chassis with the v2
  mechanism Processes; recalibrate the closed-loop pool replenishment;
  ensure phenotypes #5–#8 still pass (no longer trivially).
- **Risk: medium.** Closed-loop has been carefully calibrated for v1 rates
  (Phase C.4). v2 mechanism rates will differ from prescribed values by
  oracle-quality margin — closed-loop may regress until re-tuned.
  Polymerase/ribosome counts: v2 needs these as state inputs; without D.2,
  you'd seed them as constants (acceptable for first cut).

## Yield-per-work matrix

| Option       | Phenotype score (real-tests delta)         | Mass-gap closed | Unblocks                    | Effort | Hard prereqs |
|--------------|--------------------------------------------|-----------------|-----------------------------|--------|--------------|
| **A — D.2**  | 0 immediate; enables A.next + C.next + B   | +25 %           | M5 (replisome), v2 counts   | medium | none         |
| **B — M5**   | +1 (cell-cycle); partial p10               | +15 %           | division (deferred anyway)  | high   | D.2 (replisome) |
| **C — v2**   | +4 (p5–p8 circular → real)                 | 0 %             | publication-quality preds   | medium | none (constants ok) |

Score-per-effort, weighted toward downstream unblocks:
- A: high — small immediate phenotype delta but is on the critical path of
  both other options.
- C: high — biggest immediate count of "real-test" upgrades; closed-loop
  recalibration is the only real risk.
- B: low — needs A first, doesn't help #5–#8, division deferred.

## Recommendation

**Sequence: D.2 → v2 chassis swap → M5.**

Reasoning:

1. **D.2 first.** It is a hard prerequisite for both other options. With
   complexes live, M2v2/M3v2 can read RNAP/ribosome counts as actual
   chassis state instead of constants — that's the difference between
   "real prediction" and "real prediction with one fewer asterisk". And
   M5 cannot be done without replisome.

2. **v2 chassis swap second.** Highest immediate yield (4 circular tests
   → real). Recalibration cost is a known shape (Phase C.4 set the
   pattern). Best moment is right after D.2 lands so RNAP/ribosome state
   is wired in the same pass.

3. **M5 third.** Best done once D.2 + v2 are live and the chassis is the
   richest possible. Cell-cycle phenotypes also benefit from the fully
   real M2/M3 underneath.

If the user wants a single highest-immediate-yield pick instead of a
sequence, the answer is **C (v2 chassis swap)** — 4 phenotypes promoted
from circular to real in one phase. Trade-off: leaves p10 untouched and
defers the prerequisite for M5.

## Tie-breaker / parking-lot items not on critical path

- p10 partition into per-class targets (p10a substrate, p10b RNA, p10c
  protein) — gives finer-grained green/red breakdown without finishing
  D.2/M5. Cheap; consider as a **side task** during D.2.
- M2 per-condition snapshots (in flight as background agent
  `m2-per-condition-snapshots`) — closes one xfail unrelated to A/B/C.
- Karr full-mat catalog (in flight as background agent
  `karr-mat-catalog`) — discoverability infra, does not affect the
  decision.
