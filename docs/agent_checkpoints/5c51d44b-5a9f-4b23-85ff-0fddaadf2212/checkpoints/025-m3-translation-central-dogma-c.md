<overview>
OpenCell — open-source whole-cell simulation of *M. genitalium* in Python, built on Karr's WCM data and the vivarium-core chassis. This session shipped **M3 translation** as a Karr-prescribed-rates module mirroring the M2 pattern, then composed M1 (FBA metabolism) + M2 (transcription) + M3 (translation) into a single ticking Engine — completing the central-dogma chassis. Approach: extract per-protein arrays from `sim.state.ProteinMonomer` via MATLAB, ingest to a committed JSON+NPZ fixture, integrate dN/dt = s − k·N analytically per 1s tick, and validate via round-trip + chassis composition tests.
</overview>

<history>

1. **User: "let's go with m3"** (after M1+M2 composition shipped, 465 tests green)
   - Probed Karr KB for protein/translation data. Found `Process_Translation.parameters.{ribosomeElongationRate, tmRNABindingProbability}` and 482 `kb.proteinMonomers` stubs — but stubs are unusable: their `gene`, `compartment`, `halfLife`, `sequence` properties return cell `{className, idxUint32}` reference placeholders (Karr's serialization of handle cycles), not real values.
   - Probed deeper: discovered `sim.state.State_ProteinMonomer` is the goldmine — has `lengths(4820)`, `halfLives(4820)`, `decayRates(4820)`, `counts(4820,6)`, `molecularWeights(4820)`, `baseCounts(4820,722)`, `compartments(4820)`, plus `matureIndexs(482)` etc., where 4820 = 482 species × 10 maturation forms. The "mature" slice is what we want.
   - Extended `scripts/matlab/extract_karr_targeted.m` with a "section 9" that dumps the full 4820-vec state arrays plus walks the 482 KB stubs to grab `wholeCellModelID`, gene reference (via `g{2}` index → `kb.genes(idx).wholeCellModelID`), and compartment WCM ID. Re-ran MATLAB extractor → produced `data/m1_sources/karr_flat/proteins_targeted.mat`.
   - Built `scripts/karr_native_ingest_m3.py` → produced `data/karr_fixtures/karr_native_m3.{json,npz}` (482 proteins, 16 aa/s elongation rate, 16,177 total mature counts, 119 immortal proteins).
   - **Pre-created M3 directories** (`opencell/m3/`, `tests/m3/`) in their own response to avoid the parallel-tool race that bit M2.
   - Built `opencell/m3/translation.py` (KarrTranslationModel + load_default + step_analytical + aa_consumption_per_s), `opencell/m3/__init__.py`, `opencell/vivarium/karr_m3.py` (KarrTranslationProcess + build_karr_m3_engine), 6 unit tests + 3 chassis tests. **9/9 passed (143s).**
   - Extended `opencell/vivarium/karr_composite.py` with `build_karr_m1_m2_m3_engine` (3-process composition; M3 contributes a single `AA_total` placeholder substrate key in addition to M2's NTP keys, all sharing the M1 substrates store).
   - Added 4 central-dogma chassis tests in `tests/vivarium/test_karr_central_dogma_chassis.py`: build, all-flat-at-SS (M1 growth + M2 RNAs + M3 proteins), shared-substrate consumption (NTP from M2 + AA_total from M3), dimensionality (645/525/482). **4/4 passed (26s).**
   - Updated `opencell/vivarium/__init__.py` to export M3 + 3-way composer.
   - Cleaned up 11 temporary probe scripts.
   - Full suite: **478/478 green (752s / 12m32s)**. (465 + 9 m3 + 4 central-dogma = 478.)
   - **NOT YET COMMITTED** when the conversation was compacted. Files staged: M3 module, fixture, vivarium wrapper, composer extension, tests.

</history>

<work_done>

**Files created (NOT yet committed):**
- `opencell/m3/translation.py` — KarrTranslationModel dataclass + `load_default` + `step_analytical(model, protein_counts, dt_s)` (closed-form for k>0 + linear branch for k=0 immortals) + `aa_consumption_per_s` (returns total + per-metabolite over 722 vocab).
- `opencell/m3/__init__.py` — re-exports.
- `opencell/vivarium/karr_m3.py` — KarrTranslationProcess (1s tick, writes `protein.counts` 482-dict + `substrates.AA_total` placeholder) + `build_karr_m3_engine`. Has `substrate_default` parameter (mirroring M2 pattern).
- `scripts/karr_native_ingest_m3.py` — extractor reading `proteins_targeted.mat` → `karr_native_m3.{json,npz}`.
- `data/karr_fixtures/karr_native_m3.json` (~26 KB) and `karr_native_m3.npz` (~45 KB).
- `tests/m3/__init__.py`, `tests/m3/test_translation.py` (6 tests).
- `tests/vivarium/test_karr_m3_chassis.py` (3 tests).
- `tests/vivarium/test_karr_central_dogma_chassis.py` (4 tests).

**Files modified (NOT yet committed):**
- `scripts/matlab/extract_karr_targeted.m` — added section 9: protein-monomer state dump + KB stub walk for IDs.
- `opencell/vivarium/karr_composite.py` — added `build_karr_m1_m2_m3_engine` (3-process composer); preserved `build_karr_m1_m2_engine`.
- `opencell/vivarium/__init__.py` — exports KarrTranslationProcess + build_karr_m3_engine + build_karr_m1_m2_m3_engine.

**Tasks completed:**
- [x] Probe Karr MAT for translation/protein data
- [x] Extend MATLAB extractor for protein state arrays
- [x] Re-extract proteins_targeted.mat
- [x] Build M3 ingest + module + chassis wrapper
- [x] Write 9 M3 tests (6 unit + 3 chassis)
- [x] Compose M1+M2+M3 into single engine
- [x] Write 4 central-dogma chassis tests
- [x] Update vivarium __init__ exports
- [x] Clean up 11 temp probe scripts
- [x] Full suite passes 478/478 (12m32s)

**Tasks NOT yet done:**
- [ ] Git commit (work staged but not yet committed when conversation compacted)
- [ ] Update plan.md / SQL todos for M3 completion

</work_done>

<technical_details>

**Karr KB serialization quirk (CRITICAL):** When `data/knowledgeBase.mat` is loaded fresh, `kb.proteinMonomers(i).gene` returns a 1×2 cell `{'edu.stanford.covert.cell.kb.Gene', uint32(idx)}` — NOT the actual Gene object. Same for `compartment`. Worse: `kb.proteinMonomers(i).halfLife`, `.sequence`, `.molecularWeight` ALL fail with "Dot indexing is not supported for variables of type cell" — they're not loaded as direct values. The protein stubs are essentially ID/name/density/dnaFootprint only. **Solution:** Use `sim.state.State_ProteinMonomer` instead — it has fully populated arrays. Use `kb.genes(idx)` (works) for gene WCM lookup, `kb.compartments(idx)` for compartment WCM.

**State_ProteinMonomer layout:** 4820-element vectors = 482 species × 10 maturation forms (nascent, processedI, processedII, signalSequence, folded, mature, inactivated, bound, misfolded, damaged). The `matureIndexs(482,1)` (1-based MATLAB indices) maps species → mature row. We slice everything to mature. Counts column 0 = mature initial; col 2-5 are other forms (col 1 was zero in the snapshot).

**Karr unit conventions for proteins (DIFFERENT from M2):**
- Protein `halfLife` is in **SECONDS** (median ~7.2e4 ≈ 20 hr). Compare M2 RNA halfLife in **MINUTES**.
- `decayRates` is per-second.
- 119 essential proteins have `halfLife = inf` → `decayRate = 0` → integrator linear branch.
- `synth_rate_per_s = counts_mature * decayRate_per_s` (Karr's fitting convention: dN/dt = s − k·N = 0 at SS). Immortals have synth = 0 trivially.

**Implied throughput:** total mature count = 16,177; total synth ≈ 0.156 monomers/s; total AA polymerization at SS = ~38.9 aa/s. Lower than full-cell synthesis (~10^4 aa/s peak) because this is the snapshot's decay-balancing rate, not the dividing-cell rate. Acceptable for v1 prescribed-rates module.

**Vivarium schema-merge alignment:** When multiple processes register on the same store path, defaults must agree. M3 adds an `AA_total` key NOT in M1's 585 substrate WCM IDs — so the composer adds `AA_total: 1.0` to the initial_state explicitly. M3's `substrate_default` parameter (added like M2's) lets the composer set 1.0 to match M1.

**MATLAB extractor section 9 pattern:**
```matlab
for nm = {'matureIndexs', ...}, protOut.(nm{1}) = pmstate.(nm{1}); end
% Then iterate KB stubs to grab IDs:
for i = 1:nP
    p = pms(i);
    g = p.gene;  % returns {className, idx}
    geneIdx(i) = double(g{2});
    geneWcm{i} = kbobj.genes(double(g{2})).wholeCellModelID;
end
```

**Tool-ordering quirk reaffirmed:** `New-Item -ItemType Directory` in same response as `create` calls races. Always do `New-Item` in a SEPARATE response, verify with `Test-Path`, then issue `create` calls.

**Test runtimes:** M3 unit + chassis = 143s (M3 chassis tests use `5/k_min` for relaxation duration which is ~519,000s sim time; the analytical step still computes fast but vivarium emit overhead scales). Full suite = 752s (12m32s).

**M3 v1 / v2 staging mirrors M2:**
- v1 (shipped): Karr-prescribed s_i and k_i. dN/dt = s − k·N analytically. Round-trip oracle is tautological by construction (Karr fit s = N_ss·k).
- v2 (deferred): derive s_i from ribosome counts × mRNA_i × elongation / length_i; compare against Karr's fitted s_i as independent oracle.

</technical_details>

<important_files>

- `opencell/m3/translation.py` ✅ NEW
   - Core M3 module. KarrTranslationModel dataclass, load_default, step_analytical, aa_consumption_per_s.
   - Mirrors `opencell/m2/transcription.py` API exactly.

- `opencell/m3/__init__.py` ✅ NEW
   - Re-exports.

- `opencell/vivarium/karr_m3.py` ✅ NEW
   - KarrTranslationProcess (1s tick, ports: protein.counts 482-dict 'set', substrates.AA_total 'accumulate').
   - `substrate_default` parameter for composer alignment.

- `opencell/vivarium/karr_composite.py` ✅ MODIFIED
   - Added `build_karr_m1_m2_m3_engine` (~lines 110+); kept `build_karr_m1_m2_engine`.
   - Topology: M1↔metabolic_reaction+substrates, M2↔rna+substrates, M3↔protein+substrates.
   - Initial_state explicitly seeds `substrates['AA_total'] = 1.0`.

- `opencell/vivarium/__init__.py` ✅ MODIFIED
   - Exports KarrTranslationProcess, build_karr_m3_engine, build_karr_m1_m2_m3_engine.

- `scripts/matlab/extract_karr_targeted.m` ✅ MODIFIED
   - Section 9 (~lines 213+ within the KB block): pulls full 4820-vec arrays from State_ProteinMonomer + walks 482 KB stubs for IDs.

- `scripts/karr_native_ingest_m3.py` ✅ NEW
   - Slices 4820 → 482 mature, computes synth_rate_per_s = counts*decay, writes JSON+NPZ.

- `data/karr_fixtures/karr_native_m3.{json,npz}` ✅ NEW
   - Committed fixture (26 KB + 45 KB). Sole runtime dependency of `opencell.m3.translation`.

- `tests/m3/test_translation.py` ✅ NEW (6 tests)
   - fixture_counts, arrays_finite, steady_state_round_trip, step_preserves_ss, step_relaxes_to_ss, aa_consumption_positive.

- `tests/m3/__init__.py` ✅ NEW (empty)

- `tests/vivarium/test_karr_m3_chassis.py` ✅ NEW (3 tests)
   - process_builds, engine_runs_without_drift_at_ss, engine_starting_perturbed_relaxes.

- `tests/vivarium/test_karr_central_dogma_chassis.py` ✅ NEW (4 tests)
   - engine_builds_and_runs, central_dogma_states_stable_at_ss, shared_substrates_carry_m2_and_m3_consumption, dimensionality.

- `data/m1_sources/karr_flat/proteins_targeted.mat` ✅ NEW (gitignored — under WholeCell/karr_flat which is gitignored)
   - Re-generated by extended MATLAB extractor.

</important_files>

<next_steps>

**Immediate (resume point):**

1. **Commit the M3 work:**
   ```
   git add -A
   git commit -m "M3 v1 translation + central-dogma chassis composition" \
     -m "Adds opencell/m3/translation.py + opencell/vivarium/karr_m3.py mirroring the M2 prescribed-rates pattern. 482 mature protein monomers from sim.state.ProteinMonomer (matureIndexs slice of 4820-vec); halfLife in seconds; 119 immortal proteins (k=0 linear branch). synth_rate = counts*decay by Karr's fitting convention. Extended extract_karr_targeted.m section 9 to dump State_ProteinMonomer arrays + walk KB stubs for IDs (KB stubs are unusable for properties; use state arrays instead). Composer extended with build_karr_m1_m2_m3_engine sharing the substrates store across all three processes (M3 adds an AA_total placeholder key in addition to M2's NTP keys). Tests: 6 unit + 3 m3-chassis + 4 central-dogma = 13 new. Full suite 465 -> 478 (12m32s)." \
     -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
   ```

2. **Update plan.md + session-state mirror** with M3 v1 entry and central-dogma composition.

3. **Update SQL todos** if any `m3-translation` or similar exists.

**After M3 v1 commit, decision tree for next:**
- **M4 protein folding/maturation** (mirror pattern; closes the post-translation pipeline)
- **M3 v2 ribosome mechanics** (independent oracle on synth_rate_per_s)
- **M2 v2 polymerase mechanics** (independent oracle on M2 synth)
- **Substrate writeback / Karr's `calcFluxBounds()` port** — closes the real cross-process flux loop; needs the 585→1686 metabolite×compartment count vector mapping. The slowest and most critical next step for biology fidelity (currently M1 ignores M2/M3 substrate writebacks).

**Open questions / blockers:**
- `m1-extract-per-process-fixtures` SQL todo still pending (would batch ship M4-M7 fixtures while we have MATLAB warm).
- The 1686-element metabolite×compartment count vector mapping is needed before substrate-coupled FBA. Not blocking M4-M7 prescribed-rates modules but blocks "real biology" claim.
- `import import` typo fix in `WholeCell/.../FtsZPolymerization.m:134` still not upstreamed.

</next_steps>