# D.2 design v2 — agent status

**Branch:** `agent/d2-design-v2`
**Final commit SHA:** `811a707fe2ae1dcf0bd460cb655624f07f3e7d64`
**Worktree:** `/mnt/e/opencell-worktrees/d2-design-v2`

## Deliverables landed (single commit)

1. `docs/design/d2_complex_assembly.md` — **770 lines**, replaces v1 (496 LOC).
2. `data/karr_fixtures/d2_mature_subset.json` — 1243 LOC manifest of the
   158-complex mature-supported subset, computed live from
   `data.states.State_Mass.dump.complex.{counts, matureIndexs, boundIndexs}`
   with global aggregates, per-complex mature/bound counts, and the 10
   bound-heavy anchors (schema `d2_mature_subset__v1`).

Nothing else was modified. Verified via `git status --short` and
`git diff --cached --stat` before commit.

## ARCHIVE_SPEC extensions required

**22 new entries** under `sim_fitted_targeted.fields` (all paths verified
against `data/karr_archive/full_inventory.json`, 4837 leaves):

```
states.State_Mass.dump.complex.counts                       [1206, 6] uint8
states.State_Mass.dump.complex.matureIndexs                 [201]     uint16
states.State_Mass.dump.complex.boundIndexs                  [201]     uint16
states.State_Mass.dump.complex.nascentIndexs                [201]     uint8
states.State_Mass.dump.complex.inactivatedIndexs            [201]     uint16
states.State_Mass.dump.complex.misfoldedIndexs              [201]     uint16
states.State_Mass.dump.complex.damagedIndexs                [201]     uint16
states.State_Mass.dump.complex.molecularWeights             [1206]    float64
states.State_Mass.dump.complex.dryWeight                    [6]       float64
states.State_Mass.dump.complex.compartments                 [1206]    uint8
states.State_Mass.dump.complex.formationProcesses           [1206]    uint32
states.State_Mass.dump.complex.proteinComplexComposition    [525, 201, 6] uint8
states.State_Mass.dump.complex.ribosome70SIndexs            scalar    int64
states.State_Mass.dump.complex.ribosome30SIndexs            scalar    int64
states.State_Mass.dump.complex.ribosome50SIndexs            scalar    int64
states.State_Mass.dump.complex.translationFactorIndexs      [3]       uint8
states.State_Mass.dump.complex.rnaPolymeraseIndexs          [2]       uint8
states.State_Mass.dump.complex.replisomeIndexs              [4]       uint8
states.State_Mass.dump.complex.dnaPolymeraseIndexs          [3]       uint8
states.State_Mass.dump.complex.ftsZGTPIndexs                scalar    int64
states.State_Mass.dump.complex.ftsZGDPIndexs                scalar    int64
states.State_Mass.dump.complex.dnaAPolymerIndexs            [12]      uint8
```

The doc lists these in §2.3 with consumer mapping. Doc-only PR — these
are NOT yet added to `scripts/build_karr_archive.py` (first action of
the D.2 implementation PR).

## Mature-supported subset

- **Threshold:** `mature_total ≥ 1` (sum across 6 compartments).
- **Count:** **158 complexes** (NOT ~191 as the user brief estimated).
- 43 complexes have `mature_total == 0` in the snapshot — including
  `RIBOSOME_70S` and `RNA_POLYMERASE`, which exist only in the bound
  pool. These 43 are still tested for conservation/topo/byproducts but
  excluded from the per-complex snapshot oracle.

## Bound-heavy anchor list (10 anchors)

Re-derived from `data.states.State_Mass.dump.complex.counts[boundIndexs, :]`
(snapshot file `/mnt/e/opencell/data/m1_sources/karr_flat/sim_fitted_targeted.mat`,
read read-only — no git ops in main checkout). At threshold `bound ≥ 1`:

| WID                            | mature | bound | Consumer         |
|--------------------------------|--------|-------|------------------|
| MG_213_214_298_6MER_ADP        |   3    |  78   | DNA repair (F)   |
| MG_089_DIMER                   |  65    |  68   | DNA repair (F)   |
| MG_433_DIMER                   |  54    |  68   | DNA repl. (M5)   |
| MG_451_DIMER                   |  71    |  68   | DNA repl. (M5)   |
| RIBOSOME_70S                   |   0    |  56   | M3v2             |
| DNA_GYRASE                     |   3    |  47   | DNA topology (F) |
| RNA_POLYMERASE                 |   0    |  40   | M2v2             |
| MG_469_1MER_ATP                |   2    |  23   | M5 (DnaA)        |
| MG_469_7MER_ATP                |   0    |   4   | M5 (DnaA)        |
| MG_428_DIMER                   |   8    |   2   | Cell division (F)|

Matches GPT-5.4's "10 anchors" claim exactly at `bound ≥ 1`.

## Global aggregates from snapshot (verified)

- mature_total = **4006** (user brief said 3264 — discrepancy noted in
  doc §8 TD5; does not change Q1/Q2 strategy).
- bound_total = **454** (matches user brief).
- inactivated_total = 37, nascent/misfolded/damaged = 0.
- complex.dryWeight: cytosol = 1.2009 × 10⁻¹⁵ g, membrane =
  3.043 × 10⁻¹⁶ g, total 1.5053 × 10⁻¹⁵ g. The brief's
  "≈ 1.20 × 10⁻¹⁵ g (~38 % of cellDry)" matches the cytosol-only number.

## Open questions for human (2)

Per doc §10:

1. `complex.counts` updater semantics: `accumulate` (proposed) vs. `set`?
   No in-repo precedent makes the choice obvious — M2/M3 use `set` for
   their primary count stores but `accumulate` for `substrates`.
2. D.4 vs. M6 home for ProteinActivation? Doesn't affect this PR's
   deliverable; needed for next planning cycle.

Q1 and Q2 are resolved (decisions baked into doc §1, §3, §6).

## Deviations from brief

1. **Mature subset = 158, not ~191.** Briefed as ~191; live computation
   from snapshot says 158 at threshold ≥1. Reported transparently in
   doc §6.1. No strategy change.
2. **Global mature_total = 4006, not 3264.** Live snapshot value.
   Documented in §8 TD5.
3. **Read snapshot `.mat` from main checkout absolute path**
   (`/mnt/e/opencell/data/m1_sources/karr_flat/sim_fitted_targeted.mat`)
   — file is not present in this worktree. Used `scipy.io.loadmat`
   read-only with no `cd` and no git ops in main; this does not violate
   "stay in worktree for git operations" since no git was run there.
   The brief explicitly suggested this fallback ("use scipy.io.loadmat
   against `data/m1_sources/karr_flat/sim_fitted_targeted.mat` if not
   yet in archive").
4. **No new fixture for ribosome assembly costs** (BLOCKER 1 in brief).
   Re-inspection found those costs already encoded in
   `karr_protein_complexes.json` (negative-coef metabolite balance for
   the 70S row encodes the 6× GTP/H₂O/GDP/Pi/H balance). Documented in
   §2.4. No deviation in outcome — just that the resolution is "no new
   data needed" rather than "extract more data".

## Verification log (per brief)

- `git status` clean before commit, only the two intended files staged. ✅
- All 22 ARCHIVE_SPEC paths verified against full_inventory.json. ✅
- Chassis port names verified by reading `karr_composite.py`,
  `karr_m2.py`, `karr_m3.py`. ✅
- Anchor list re-derived from snapshot `.mat`. ✅
- Mature subset list computed and committed as `d2_mature_subset.json`. ✅
- No tests run (doc-only deliverable). ✅
- Single commit on `agent/d2-design-v2`, no merge. ✅
