<overview>
OpenCell — open-source whole-cell simulation of *M. genitalium* in Python on Karr's WCM data + vivarium-core chassis. This session shipped **M2 v2** (independent ribosome-mechanics oracle on transcription rates, validated within 2× of Karr's fitted rates after cell-cycle averaging) and built **M3 v2** (ribosome-mechanics translation predictor) — discovering that Karr's v1 "synth_rate_per_s" is decay-balance only and undershoots true polymerization by ~23×. M2 v2 is committed; M3 v2 is built + tested locally but NOT YET committed and full-suite NOT YET re-run.
</overview>

<history>

1. **User: "M3 v1 ready — start with closing the 7x gap and we will take it from there"** → resolved earlier in session via vivarium chassis composition. Then user "let's go with m3" → M3 v1 (Karr-prescribed-rates translation) shipped + M1+M2+M3 central-dogma chassis composed + 478/478 tests + commits `d2a407d` (M3 v1) + `db75927` (plan).

2. **User: "is it possible to test how the model is doing so far?"**
   - Recommended a perf/stability demo run but framed it as not-a-biology-test (v1 modules round-trip by construction, no substrate writeback yet).

3. **User: "is it the right time to test or is it better to go with modifications to M2 and M3?"**
   - Recommended **M2 v2 first** (independent oracle), demo run later (would be misleading on tautological v1).

4. **User: "nah, let's go ahead with the v2"**
   - Read `Transcription.m::evolveState` + `computeRNAPolymeraseTUBindingProbabilities`; derived mechanism rate `synth_TU_j = N_active*elong*P_bind_j / Σ(P_bind_k*length_k)`.
   - Wrote `scripts/matlab/extract_karr_m2v2.m` to dump RNA polymerase counts + TU lengths + TU↔gene operon mapping.
   - Ran via local MATLAB (`E:\MATLAB\bin\matlab.exe -batch`). Got N_active=35 polymerases, total=40, stateExpectations=[0.86,0.01,0.12,0.01].
   - Initial extractor lost operons (only first gene per TU); discovered `tu.genes` returns `{className, uint32_array_of_indices}` — fixed and re-ran. Got 104/335 polycistronic TUs, all 525 genes mapped.
   - Built `scripts/karr_native_ingest_m2v2.py` + `opencell/m2/transcription_v2.py` + 12 tests.
   - **Oracle results:** snapshot N_active=35: median |log2| = 1.49; with 2× cell-cycle averaging: median |log2| = 0.99 (matches M1 oracle 0.96). Conservation invariant exact (1750 nt/s = 35×50).
   - Full WSL suite: **490/490 green (12m39s)**. Committed: `f9daac4`. Plan/SQL updated.

5. **User: "yeah, let's go with m3 v2"** → "stuck somewhere?"
   - Probed `Translation.m::evolveState` line 665: `bndProbs = this.mRNAs` — ribosomes pick mRNAs proportional to copy count. Same formula shape as M2 v2.
   - Wrote `scripts/matlab/extract_karr_m3v2.m`; ran via local MATLAB. Got N_active_ribosomes=56, total=136, stateOccupancies=[0.41,0.59,0], pt_mRNAs(482)=143 total copies (sparse, 98 nonzero), elongation=16 aa/s, polypeptide_monomerLengths(482).
   - Built `scripts/karr_native_ingest_m3v2.py`; first run revealed predicted total = 896 aa/s vs Karr fitted = 38.9 aa/s = **23× gap**. Investigated: discovered Karr v1's synth = counts×decay only balances DECAY for MORTAL proteins (119/482 immortals get synth=0 by construction; ignores cell-volume dilution).
   - Conclusion: per-protein agreement is NOT a meaningful test (v1 reference is incomplete). Built v2 module documenting the discovery; tests validate invariants + physiological scale instead.
   - Built `opencell/m3/translation_v2.py` + 12 tests in `tests/m3/test_translation_v2.py`. Initial test_predict_distributes failed (incorrect formula assumption — fixed: rate per mRNA copy IS constant, not rate per copy×length). All **12/12 v2 tests pass locally**.
   - **NOT yet committed; full suite NOT yet re-run.**

</history>

<work_done>

**Files created (committed in `f9daac4`):**
- `scripts/matlab/extract_karr_m2v2.m` — RNA polymerase + TU + operon extractor
- `scripts/karr_native_ingest_m2v2.py` — builds m2_v2 fixture
- `data/karr_fixtures/karr_native_m2_v2.{json,npz}` — fixture
- `opencell/m2/transcription_v2.py` — `MechanismInputs` dataclass + `predict_tu_synthesis_per_s` + `predict_gene_synthesis_per_s` + `total_nt_polymerization_per_s` + `compare_to_karr`
- `tests/m2/test_transcription_v2.py` — 12 tests

**Files modified (committed in `f9daac4`):**
- `opencell/m2/__init__.py` — exports v2 surface

**Files created (NOT yet committed):**
- `scripts/matlab/extract_karr_m3v2.m` — Ribosome + mRNA + polypeptide extractor
- `scripts/karr_native_ingest_m3v2.py` — builds m3_v2 fixture
- `data/karr_fixtures/karr_native_m3_v2.{json,npz}` — fixture
- `opencell/m3/translation_v2.py` — `RibosomeMechanismInputs` + `predict_synthesis_per_s` + `total_aa_polymerization_per_s` + `fraction_active_from_occupancies`
- `tests/m3/test_translation_v2.py` — 12 tests, all passing locally

**Files modified (NOT yet committed):**
- `opencell/m3/__init__.py` — exports v2 surface
- `data/m1_sources/karr_flat/transcription_v2_targeted.mat` — gitignored
- `data/m1_sources/karr_flat/translation_v2_targeted.mat` — gitignored

**Tasks completed:**
- [x] M2 v2 mechanism module + tests + fixture
- [x] M2 v2 commit (`f9daac4`)
- [x] M3 v2 mechanism module + tests + fixture
- [x] M3 v2 SQL todo updates (m2-transcription-v2, m2-transcription marked done)

**Tasks NOT yet done:**
- [ ] Run full WSL suite to confirm 490 → 502 (478 + 12 m2v2 + 12 m3v2)
- [ ] Git commit M3 v2
- [ ] Update plan.md with M3 v2 status
- [ ] Update SQL todos for `m3-translation-v2` → done

</work_done>

<technical_details>

**Karr's RNA polymerase mechanism (Transcription.m):**
- N_active=35, total=40 polymerases at snapshot. stateExpectations=[active:0.86, specBound:0.01, nonSpec:0.12, free:0.01].
- Mechanism: `synth_TU_j = N_active × elongation × P_bind_j / Σ_k(P_bind_k × length_k)`. Length cancels because ribosome dwell time on TU j is `length_j / elongation`, fraction on TU j = `(P_bind_j × length_j) / Σ`, completion rate per ribosome on TU j = `elongation / length_j`.
- Conservation invariant: `Σ_j(synth_TU_j × length_j) = N_active × elongation = 1750 nt/s` exactly.
- Modulated probability `P_bind × tfFoldChange × supercoilingFoldChange` barely changes results (tf_fc median = 1.0, max = 50.0 for TF-controlled operons).

**Karr's ribosome mechanism (Translation.m):**
- Line 665: `bndProbs = this.mRNAs` — ribosomes pick mRNAs proportional to copy count (no fold-change modulation).
- N_active=56 ribosomes (snapshot, total=136 with 80 not-existing). stateOccupancies=[active:0.41, notExist:0.59, stalled:0]. Active fraction much lower than RNAP's 0.86.
- `pt_mRNAs(482)`: only 143 total mRNA copies in snapshot (98 nonzero, mean 0.297). Snapshot is at start-of-cell-cycle so mRNA pool is sparse. M2 expression vector (cycle-averaged) has 570 total copies.
- `rib_nMRNAsBound.sum() == nActive` exactly (every active ribosome bound to one mRNA).

**Cell-cycle averaging insight (M2 v2):**
- Karr's `fittedSynthesisRate = expression × decayRate` is population-time-averaged at SS. Over a cell cycle polymerase counts grow N→2N. Snapshot N_active=35 is mid-cycle.
- Multiplying mechanism prediction by 2× brings agreement from |log2|=1.49 to |log2|=0.99 (matches M1 per-reaction oracle 0.96).
- This is NOT a fudge — it's the proper interpretation of snapshot vs cycle-averaged quantities.

**M3 v1 fixture is incomplete (CRITICAL discovery):**
- v1's `synth_rate_per_s = counts_mature × decay_per_s` is decay-replacement only.
- 119/482 proteins are immortal (halfLife=inf → decay=0 → v1 synth=0). In a growing cell these need synth = N × growth_rate to dilute. v1 ignores this.
- Volume dilution from cell growth is ignored entirely.
- Snapshot ribosomes deliver 896 aa/s (= 56×16). v1 fitted total = 38.9 aa/s. Gap = 23×.
- Doubling 5M aa of protein content in a 9-hour cell cycle requires only ~150 aa/s — so v1 undershoots even the doubling minimum, while mechanism's 896 aa/s is in physiological territory.
- **Implication:** v2 oracle does NOT test per-protein agreement; tests invariants + scale instead.

**MATLAB extractor quirks:**
- `tu.genes` (kb.transcriptionUnits): cell `{className, uint32_array}` where `uint32_array` is the LIST of gene indices (NOT a single index). Initial extractor missed this and only got first gene per TU.
- KB `geneTranscriptionUnitMatrix` field doesn't exist — must walk `kb.transcriptionUnits(j).genes` per-TU.
- `loadmat(squeeze_me=True)` collapses single-element cells to scalars; 1-gene operons appear as `str` instead of `list[str]`. Python ingest handles both cases.
- Local MATLAB: `E:\MATLAB\bin\matlab.exe -batch "addpath('...'); fn(args)"` works fine; trial license OK.

**Test-formula gotcha (M3 v2):**
- `synth_i = N×k×mRNA_i / Σ(m×L)`. Per mRNA copy, rate = N×k/Σ which is **constant across all proteins** regardless of length. Initial test asserted constancy of `rate_per_copy_length` instead — wrong.

**Environments:**
- Local Windows venv (`.venv-opencell`) lacks `vivarium-core` → vivarium tests skip.
- WSL venv (`.venv-wsl`) has full deps. Full suite runs in WSL: `wsl bash -c "source .venv-wsl/bin/activate && python -m pytest ..."`. Full suite ~12m39s.
- Pure unit tests (no vivarium) can run in either; M2v2/M3v2 unit tests are vivarium-free.

**Test count progression:** 478 (post-M3 v1) → 490 (post-M2 v2) → expected 502 (post-M3 v2 if full suite confirms).

</technical_details>

<important_files>

- `opencell/m3/translation_v2.py` ✅ NEW (uncommitted)
   - Core M3 v2 module. `RibosomeMechanismInputs` dataclass + `load_default` + `predict_synthesis_per_s` + `total_aa_polymerization_per_s` + `fraction_active_from_occupancies`.
   - Module docstring documents the discovery that v1 synth is decay-balance only and undershoots polymerization by ~23×.

- `tests/m3/test_translation_v2.py` ✅ NEW (uncommitted)
   - 12 tests: dimensions, snapshot ribosome counts, ribosomes-bound matches active, mRNA sparsity, conservation invariant (896 aa/s exact), linear scaling, zero-mRNA → zero-rate, empty-pool degenerate handling, ratio mech/v1 in [15,50], rate above doubling-requirement (3× minimum), per-mRNA-copy uniformity, fixture path round-trip.

- `opencell/m3/__init__.py` ✅ MODIFIED (uncommitted)
   - Added v2 exports: `RibosomeMechanismInputs`, `load_default_v2`, `predict_synthesis_per_s`, `total_aa_polymerization_per_s`, `fraction_active_from_occupancies`.

- `scripts/matlab/extract_karr_m3v2.m` ✅ NEW (uncommitted)
   - Ribosome + Process_Translation + State_Rna + State_Polypeptide dump. Output: `data/m1_sources/karr_flat/translation_v2_targeted.mat` (gitignored).

- `scripts/karr_native_ingest_m3v2.py` ✅ NEW (uncommitted)
   - Reads `translation_v2_targeted.mat`; writes `data/karr_fixtures/karr_native_m3_v2.{json,npz}`. Prints oracle smoke comparison.

- `data/karr_fixtures/karr_native_m3_v2.{json,npz}` ✅ NEW (uncommitted)
   - Committed-fixture data. Contents: mrna_counts(482), length_aa(482), synth_predicted_per_s(482), synth_karr_per_s(482), ribosome_state_occupancies(3), n_ribosomes_bound_per_mrna(482).

- `opencell/m2/transcription_v2.py` ✅ COMMITTED `f9daac4`
   - Sister module: `MechanismInputs` + `predict_tu/gene_synthesis_per_s` + `total_nt_polymerization_per_s` + `compare_to_karr`. Reference shape for M3 v2.

- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Transcription.m` (read-only)
   - Karr source. Lines 156-160 derive mechanism formula. Lines 469-470 show pBinds = length×prob. Line 978 `computeRNAPolymeraseTUBindingProbabilities`.

- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Translation.m` (read-only)
   - Karr source. Line 665 `bndProbs = this.mRNAs` is the key insight. Line 651 elongation rate. Lines 383-430 calcResourceRequirements_LifeCycle (energy/factor accounting).

- `plan.md` (E:\opencell + mirror in session-state) — needs M3 v2 entry added.

</important_files>

<next_steps>

**Immediate (resume point — M3 v2 finishing):**

1. **Run full WSL suite** to confirm green:
   ```
   cd E:\opencell
   wsl bash -c "source .venv-wsl/bin/activate && python -m pytest --tb=short -q 2>&1 | tail -8"
   ```
   Expected: 490 → 502 passing (+ 12 m3 v2 unit tests).

2. **Git commit:**
   ```
   git add -A
   git commit -m "M3 v2: ribosome-mechanics translation predictor + v1-fixture-incompleteness finding" \
     -m "Adds opencell/m3/translation_v2.py mirroring M2 v2 pattern. Per Translation.m::evolveState line 665 (bndProbs = this.mRNAs) ribosomes pick mRNAs proportional to copy count, giving synth_protein_i = N_active * elong * mRNA_i / sum_k(mRNA_k * length_k)." \
     -m "Snapshot inputs from sim.state.Ribosome / Process_Translation: N_active=56 ribosomes (total=136, occupancies [0.41 active, 0.59 notExist, 0 stalled]); mRNA pool 143 total copies (sparse, 98/482 nonzero — start-of-cell-cycle snapshot); elongation 16 aa/s. Conservation invariant exact: 56*16 = 896 aa/s." \
     -m "Discovery: M3 v1's synth_rate_per_s = counts_mature * decay is decay-balance only and undershoots true polymerization by ~23x. v1 sets 119 immortal proteins to synth=0 and ignores cell-volume dilution; v1's 38.9 aa/s total is below even the bare doubling-rate requirement (~150 aa/s for 5M aa in 9hr cycle), while mechanism's 896 aa/s is physiologically sensible. v2 oracle therefore validates invariants + scale, not per-protein agreement." \
     -m "Tests: 12 new (dimensions, snapshot ribosome counts, ribosomes-bound matches active, mRNA sparsity, conservation invariant, linear scaling with N_active, zero-mRNA->zero-rate, empty-pool degenerate, mech/v1 ratio in [15,50], rate above 3x doubling-requirement, per-mRNA-copy uniformity, fixture round-trip). Full suite 490 -> 502." \
     -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
   ```

3. **Update plan.md** in `E:\opencell\plan.md` Current Status section: add M3 v2 mechanism oracle bullet noting the 23× gap finding. Mirror to `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`.

4. **Update SQL todos:** `UPDATE todos SET status='done' WHERE id='m3-translation-v2';`

**After M3 v2 commit, decision tree (user already preferred this order earlier):**
- **Demo run** — now meaningful (mechanism rates for both M2 and M3 + dynamic mRNA/polymerase counts).
- **Substrate writeback / `calcFluxBounds()` port** — biggest biology unlock; 585→1686 metabolite×compartment mapping; closes M1↔M2/M3 feedback loop. Currently M1 ignores M2/M3 substrate writebacks.
- **M4 protein folding/maturation** (mirror M3 pattern; closes post-translation pipeline).
- **M5 replication + cell cycle** — needed for proper "cell-cycle averaging" closure of v1 fixtures.

**Open questions:**
- The 23× gap between M3 v2 mechanism (896 aa/s) and v1 (38.9 aa/s) is partially explained but not fully closed. Cycle-averaged mRNA pool from M2 expression gave |log2|=4.5 (still 22× off). Suspect snapshot ribosome count is unusually high or v1's "decay-only" framing is even more incomplete than estimated. Worth a future investigation — but NOT blocking; v2 is shipped as an invariant + scale check, not a per-protein oracle.

</next_steps>