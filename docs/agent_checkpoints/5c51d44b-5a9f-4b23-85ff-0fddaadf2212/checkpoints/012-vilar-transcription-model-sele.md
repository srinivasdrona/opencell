<overview>
Building OpenCell, an open-source whole-cell simulation in Python/JAX. This session segment closed Phase 1 (all 8 quality gates), then built and validated the first real biology sub-model (`metabolism.py` wrapping Chassagnole 2002 / BIOMD0000000051) against libroadrunner to ~5×10⁻⁸ relative agreement across smooth + glucose-spike scenarios. Currently mid-implementation of the SECOND sub-model: Vilar 2002 genetic oscillator (BIOMD0000000035) as the transcription module. The blocker: Vilar uses `hasOnlySubstanceUnits=true` species, which the Chassagnole-tuned engine currently rejects with NotImplementedError.
</overview>

<history>
1. User asked "why is our model so much slower than the oracle?"
   - Built `_bench_oc_vs_rr.py` diagnostic. Found OC: 427ms vs RR: 14ms = **31× slowdown** on 300s sim. Hot spots: `sbml_model.fluxes` 52% (Python loop over 48 reactions), `list.append` 18% (6.5M calls), `_build_env` 11%.
   - Recommended: not yet a bottleneck (0.4s for 5min sim); future fix tiers = vectorized lambdify → cached env → JAX/diffrax.

2. User asked "what does that script do? why do we have it?"
   - Explained it was throwaway diagnostic. Deleted `scripts/_bench_oc_vs_rr.py`.
   - Spurious git diff revealed: `scripts/spike_chassagnole.py` had a leftover diagnostic block in HEAD. Removed it cleanly.

3. User asked "what have we achieved so far and what next?"
   - Reviewed via SQL ready-todos query. Summarized Phase 1 closure + metabolism sub-model + 7 unblocked todos. Recommended building transcription sub-model next on a curated BioModels entry, then coupling via resource ledger.

4. User noted plan.md not updated with biology sub-model
   - Found plan.md DOES have updated top section but Phase 2 row + Honest Status were stale.
   - Edited 3 spots in `~/.copilot/session-state/<id>/plan.md`: replaced "~1e-6 over 60s" with full numbers (60s=2.5e-8, 300s=3.3e-8, spike=5.2e-8); updated Phase 2 roadmap row; refined Honest Status; added perf baseline.

5. User noted E:\opencell\plan.md not synced with session plan.md
   - `Copy-Item` from session-state to E drive (`94539` bytes vs old `89313`). Committed as `4f568e0` (+202/-105 lines).

6. User asked "what about the todo DB in E drive?"
   - Found `E:\opencell\opencell_tasks.db` was 2 days stale: 3 done / 98 pending vs session 74 done / 52 pending / 1 blocked.
   - Wrote `_tmp_db_compare.py`: zero todo IDs unique to E drive (safe to overwrite). 22 stale deps in E referenced renamed/obsolete IDs.
   - Wrote `_tmp_db_sync.py`: backed up old DB, transactionally replaced todos+todo_deps from session JSON dump. Verified 127 todos / 112 deps loaded, status counts match session.

7. User asked "how will you remember to always update plan.md and todo DB?"
   - Found existing `.github/copilot-instructions.md`. Added new "State Sync Protocol" section as a mandatory rule. Documents canonical-vs-scratch artifacts, sync triggers, how-to, and what NOT to sync (review_findings).
   - `.gitignore`'d `opencell_tasks.db.bak.*`. Cleaned all `_tmp_*` files. Committed as `addab48`.

8. User asked for review + blog post + next steps
   - Reviewed today's 21 commits across 3 waves: Phase 1 closure (morning), curation tooling (midday), first biology sub-model (afternoon).
   - Wrote blog post `docs/blog/2026-04-23-the-day-the-cell-twitched.md` matching established Tehol/Bugg dialogue voice from prior posts (1248 words). Committed as `fda8302`.

9. User said "let's get some candidates lined up" for transcription sub-model
   - BioModels REST API (ebi.ac.uk) returns 403/CloudFront blocked. Switched to `github.com/biomodels/<BIOMD_ID>` git mirror (already documented as primary source).
   - Web-searched + checked README.md for: BIOMD0000000012 (Elowitz 2000 Repressilator), BIOMD0000000035 (Vilar 2002 Oscillator), BIOMD0000000091 (turned out to be Proctor 2005 Hsp90, not NF-κB — skipped), BIOMD0000000231 (Valero 2006 adenine cycle — flagged as future coupling target), BIOMD0000000016 (Goldbeter 1995 — minimal README), BIOMD0000000017 (Hoefnagel 2002 metabolism — wrong topic).
   - Downloaded Elowitz + Vilar SBML to /tmp via curl + raw URLs (after PowerShell quote-escaping issues forced me to use shell scripts on disk). Audited via `_tmp_audit_cands.py` using libsbml.
   - Found: BOTH candidates use `hasOnlySubstanceUnits=true` for ALL species — trips engine's loud-failure blocker. This is normal for stochastic-friendly gene expression models (molecule counts, not concentrations).
   - Recommended Vilar 2002 over Elowitz: absolute units (transcripts/min) vs Elowitz's dimensionless rescaled equations; designed-for-stochastic per the paper; clean structure (0 assignment rules, 0 global params, 16 mass-action reactions); 2 genes (activator+repressor) with explicit DNA states (DA, DAp, DR, DRp).

10. User said "let's go ahead with Vilar"
    - Inserted 6 todos via SQL with deps: `vilar-engine-substance-units` → `vilar-data-download` → `vilar-paper-pairing` → `vilar-transcription-wrapper` → `vilar-oracle-validation` → `vilar-comparison-artifact`.
    - Marked first 2 todos `in_progress`.
    - Downloaded Vilar SBML to `data/biomodels_reference/BIOMD0000000035_vilar2002.xml` (38322 bytes).
    - **Computed SHA-256: `c90ce4978a154f8b40eec291f1c076bdfac173efde2560771214a2d8a5b04a5e`**
    - **This is where the segment was paused for compaction.** Engine extension not yet started.
</history>

<work_done>
Files created this segment:
- `docs/blog/2026-04-23-the-day-the-cell-twitched.md` (committed `fda8302`, 1248 words, Tehol/Bugg dialogue covering today's Phase 1 closure + metabolism sub-model)
- `data/biomodels_reference/BIOMD0000000035_vilar2002.xml` (38322 bytes, SHA-256 `c90ce4978a154f8b40eec291f1c076bdfac173efde2560771214a2d8a5b04a5e`, NOT yet committed)
- `_tmp_get_vilar.sh` (still on disk, can be cleaned up)

Files modified:
- `.github/copilot-instructions.md`: added "State Sync Protocol" section (committed `addab48`)
- `.gitignore`: added `opencell_tasks.db.bak.*` (committed `addab48`)
- `opencell_tasks.db`: synced from session DB, 127 todos / 112 deps (committed `addab48`)
- `scripts/spike_chassagnole.py`: removed leftover diagnostic block (committed `addab48`)
- `plan.md` (BOTH session-state copy AND `E:\opencell\plan.md`): metabolism sub-model section updated with full validation numbers, Phase 2 roadmap row updated, Honest Status refined (committed `4f568e0`)
- Session SQL: added 6 vilar-* todos with deps, marked 2 in_progress

Today's commits (most recent first):
- `fda8302` blog: Day 2 - The Day the Cell Twitched
- `addab48` Codify state-sync protocol; sync tasks DB; remove ad-hoc diagnostic
- `4f568e0` Sync plan.md: metabolism sub-model complete, validated against libroadrunner
- `5e1453d` Add glucose-spike perturbation comparison (OC vs libroadrunner)
- `7b3ade7` compare_chassagnole.py: parameterize duration; add 60s + 300s artifacts
- `8c3fab8` chore: remove stale .git-commit-msg.tmp
- `8ef06e8` scripts/compare_chassagnole.py: visual + numeric oracle comparison
- `4f6ccf5` models/metabolism.py + sbml_model.py: SBML to ODE simulation
- (older Phase 1 closure commits earlier today)

Tests: 378 passing.

Work in progress (Vilar sub-model):
- [x] Vilar SBML downloaded + sha256 computed (uncommitted)
- [ ] Add Vilar XML to `data/biomodels_reference/README.md` and commit
- [ ] **Extend `sbml_model.py` to support `hasOnlySubstanceUnits=true`** (current blocker)
- [ ] Add unit test for substance-units handling on synthetic SBML
- [ ] Generate `manifests/vilar2002.draft.yaml` via paper-pairing verifier (PMID 12060652, DOI 10.1073/pnas.092133899)
- [ ] Build `opencell/models/transcription.py` wrapper
- [ ] Validate Vilar vs libroadrunner (smooth + perturbation)
- [ ] `scripts/compare_vilar.py` artifacts
</work_done>

<technical_details>

### Engine extension required for Vilar (the immediate next task)
Current `sbml_model.py` (line 262-267) raises `NotImplementedError` for any species with `hasOnlySubstanceUnits=true`. Needs replacing with proper per-species handling:

**SBML semantics:**
- Concentration-mode species (`hasOnlySubstanceUnits=false`, the default): kinetic laws return amount/time. Stored y is concentration. `dy/dt = stoich @ fluxes / volume`. References to species in kinetic law expressions evaluate to concentration.
- Amount-mode species (`hasOnlySubstanceUnits=true`): kinetic laws still return amount/time. Stored y is **amount** (molecule count). `dy/dt = stoich @ fluxes` (no volume divide). References to species in kinetic law expressions evaluate to **amount**.

**Required code changes** (estimated ~20 lines):
1. Add `species_substance_units: dict[str, bool]` to `SbmlOdeModel` dataclass.
2. In `from_file` (around line 253-278): track per-species substance-units flag; **fix initial value handling** (currently buggy for concentration-mode + initialAmount-only case):
   - amount-mode + initialAmount → store amount directly
   - amount-mode + initialConcentration → multiply by volume to get amount
   - concentration-mode + initialConcentration → store concentration directly  
   - concentration-mode + initialAmount → divide by volume to get concentration
3. In `rhs` (line 404-417): per-species, divide by volume only if NOT substance-units.
4. `_build_env` (line 367-380): no change needed — `env[sid] = float(y[k])` correctly puts amount-for-amount and concentration-for-concentration since y stores per-mode value.
5. Update docstring (lines 8-23) to remove the "loud failure on hasOnlySubstanceUnits" claim.

### Vilar 2002 model topology (verified via libsbml audit)
- SBML L2V3, 38322 bytes
- 1 compartment, 10 species (1 boundary "EmptySet"), 16 reactions, 0 global parameters
- 0 assignment rules, 0 rate rules, 0 algebraic rules, 0 initial assignments, 0 function defs, 0 events
- ALL 10 species have `hasOnlySubstanceUnits=true`
- Species: A (activator protein), C (complex), DA (gene-activator unbound), DAp (gene-activator bound), DR (gene-repressor unbound), DRp (gene-repressor bound), MA (mRNA activator), MR (mRNA repressor), R (repressor protein), EmptySet (boundary)
- 16 reactions all mass-action; rate constants in transcripts/min, proteins/min etc. (absolute units)

### Paper provenance for Vilar
- PMID: 12060652
- DOI: 10.1073/pnas.092133899
- Title: "Mechanisms of noise resistance in genetic oscillators"
- Authors: Vilar, Kueh, Barkai, Leibler (Rockefeller)
- Journal: PNAS 99(9):5988-5992, 2002
- Need to use existing `tools/verify_paper_pairing.py` (eutils + response_sha256) as for Chassagnole.

### Performance baseline (from this session's diagnostic)
- OC 300s sim: 427 ms; RR 300s sim: 14 ms = **31× slowdown**
- Per RHS call: 46µs (bare) vs 54µs (in solver)
- 7959 RHS evals over 300s sim
- Hot spot: `sbml_model.fluxes` (52%) — Python loop over 48 compiled-but-called-individually flux functions
- Future fix tiers: (1) vectorized single-lambdify flux evaluator → 3-5×, (2) cached array-indexed env → 2×, (3) JAX/diffrax → close most of gap to RR + GPU + autodiff for fitting

### Reusable patterns from metabolism sub-model
The Vilar sub-model should follow exactly the metabolism.py pattern:
- `transcription.py` ~140 lines: thin wrapper with `TranscriptionModel.load()` pinning BIOMD0000000035, recording DOI + PMID in `provenance()`
- `tests/integration/test_transcription_vilar.py` modeled on `test_metabolism_chassagnole.py`: 4 tests with libroadrunner oracle, rtol=1e-3, all species, multiple sample times
- `scripts/compare_vilar.py` modeled on `compare_chassagnole.py`: produces 3 PNGs (OC, RR, overlay+residual log) + per-species residuals JSON, parameterized `--seconds`

### State Sync Protocol (codified in `.github/copilot-instructions.md`)
- Canonical state lives in repo (`E:\opencell\plan.md`, `E:\opencell\opencell_tasks.db`), NOT in agent memory or session-state scratch
- Sync triggers: end of every checkpoint, after any todo status change, before answering "where are we", after >3 status changes
- Sync mechanics: Copy-Item plan.md, transactional DB merge with backup + diff check
- Don't sync `review_findings` (project-wide, may have other writers)
- Build `scripts/sync_tasks_db.py` on first need to make it one command

### Recurring environment quirks
- **PowerShell + WSL + bash heredoc**: f-strings with `{rr['[cglcex]']:.4f}` or quotes inside `wsl -- bash -c "..."` cause PS parse errors. Workaround: write Python/bash to file via `create`, then `bash /mnt/e/opencell/_tmp_*.sh`. Used multiple times.
- **CRLF line endings**: files created via `create` get CRLF on Windows; bash chokes with `'set: -\r' invalid option`. Fix: `sed -i "s/\r$//"` before running.
- **Windows ↔ WSL fs sync delay**: file may not be visible from WSL for 1-5s after `create` from Windows. Workaround: `sleep 3-8 &&` prefix.
- **Git over WSL pipe**: `git commit -m "long message"` HANGS over `wsl.exe`. Fix: heredoc to `/tmp/cm.msg`, then `git commit -F /tmp/cm.msg`.
- **BioModels REST API at ebi.ac.uk**: redirects to biomodels.org which returns CloudFront 403. Use `github.com/biomodels/<BIOMD_ID>` git mirror or raw URL `https://raw.githubusercontent.com/biomodels/<id>/master/<id>/<id>.xml` instead.
- **GitHub MCP `get_file_contents` for biomodels org**: returns directory listing fine, returns README content fine, but I don't yet have a working pattern to fetch the SBML XML through the MCP tool — fell back to curl.

### Open assumptions / questions
- Will Vilar agree with libroadrunner at ~1e-8 like Chassagnole did? Mass-action models with no assignment rules should agree even tighter, but oscillator dynamics (long-time integration of limit cycles) might accumulate phase error. **Verify after first run.**
- Should we also add a perturbation test for Vilar (e.g., transient pulse on `alphaA` to phase-shift the oscillator)? Probably yes, mirrors the spike_chassagnole pattern.
- The "EmptySet" boundary species — current engine should handle it as boundary fine, but verify.
</technical_details>

<important_files>

- **`E:\opencell\opencell\models\sbml_model.py`** (NEEDS EDITING NEXT)
  - Lines 8-23: docstring claiming hasOnlySubstanceUnits is unsupported — UPDATE
  - Lines 162-178: `SbmlOdeModel` dataclass — ADD `species_substance_units` field
  - Lines 253-278: species iteration in `from_file` — REPLACE NotImplementedError with per-species tracking + fixed initial-value handling
  - Lines 367-380: `_build_env` — likely no change needed
  - Lines 404-417: `rhs` — make volume divide conditional on NOT substance-units

- **`E:\opencell\opencell\models\metabolism.py`** (REFERENCE PATTERN)
  - Template for the new `transcription.py` wrapper
  - Pattern: `TranscriptionModel.load()` pins BIOMD ID, `provenance()` extends sbml_model.provenance with biomodels_id + paper_doi + paper_pubmed_id

- **`E:\opencell\data\biomodels_reference\BIOMD0000000035_vilar2002.xml`** (DOWNLOADED, UNCOMMITTED)
  - 38322 bytes, SHA-256 `c90ce4978a154f8b40eec291f1c076bdfac173efde2560771214a2d8a5b04a5e`
  - 10 species (all amount-mode), 16 reactions, 1 boundary species ("EmptySet")
  - Needs entry in `data/biomodels_reference/README.md` (mirror Chassagnole's row)

- **`E:\opencell\data\biomodels_reference\README.md`**
  - Has Chassagnole entry as template — add Vilar 2002 row with git-clone command and date

- **`E:\opencell\manifests\chassagnole2002.draft.yaml`** (REFERENCE)
  - Template for `manifests/vilar2002.draft.yaml` — eutils-verified paper-pairing block

- **`E:\opencell\tests\unit\test_sbml_model.py`** (NEEDS NEW TEST)
  - Add `test_substance_units_species_handled` — synthetic SBML with mixed amount/concentration species, check rhs matches manual computation

- **`E:\opencell\tests\integration\test_metabolism_chassagnole.py`** (REFERENCE PATTERN)
  - Template for `tests/integration/test_transcription_vilar.py`
  - 4 tests against libroadrunner oracle, rtol=1e-3 atol=1e-6, all species at multiple sample times

- **`E:\opencell\scripts\compare_chassagnole.py`** (REFERENCE PATTERN)
  - Template for `scripts/compare_vilar.py`
  - Produces 3 PNGs + JSON, parameterized `--seconds`

- **`E:\opencell\.github\copilot-instructions.md`** (UPDATED THIS SEGMENT)
  - New "State Sync Protocol" section is now in force for all future sessions in this repo

- **`C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`**
  - Top section reflects metabolism sub-model complete, perf baseline, all validation numbers
  - Phase 2 roadmap row + Honest Status updated
  - Lower Phase 2 detail section (lines ~482+) is STILL stale "design ~50 toy genes" — flagged for `phase2-replan-chassagnole` todo, intentionally not rewritten yet
  - **Synced to `E:\opencell\plan.md` per State Sync Protocol**

- **`E:\opencell\opencell_tasks.db`**
  - Synced this segment to match session DB (127 todos, 112 deps)
  - 6 new vilar-* todos added with dep chain
</important_files>

<next_steps>

**Immediate (resume here after compaction):**

1. **Commit the Vilar SBML download** with README update:
   ```bash
   # Add row to data/biomodels_reference/README.md mirroring Chassagnole entry:
   # | BIOMD0000000035_vilar2002.xml | git clone https://github.com/biomodels/BIOMD0000000035.git | 2026-04-23 |
   git add data/biomodels_reference/BIOMD0000000035_vilar2002.xml data/biomodels_reference/README.md
   git commit -m "Add Vilar 2002 SBML (BIOMD0000000035) for transcription sub-model"
   ```
   Update todo: `vilar-data-download` → done.

2. **Extend `opencell/models/sbml_model.py` for hasOnlySubstanceUnits** (the engine work). See "Engine extension required" in technical_details. Then add unit test on synthetic SBML with mixed amount/concentration species. Run full test suite to ensure no Chassagnole regression. Update todo: `vilar-engine-substance-units` → done.

3. **Generate `manifests/vilar2002.draft.yaml`** via existing paper-pairing verifier:
   - PMID 12060652, DOI 10.1073/pnas.092133899
   - Use `tools/verify_paper_pairing.py` pattern from Chassagnole
   Update todo: `vilar-paper-pairing` → done.

4. **Build `opencell/models/transcription.py`** following metabolism.py pattern. Thin wrapper, ~140 lines.

5. **Build `tests/integration/test_transcription_vilar.py`** modeled on Chassagnole oracle test. 4 tests, libroadrunner agreement.

6. **Build `scripts/compare_vilar.py`** modeled on compare_chassagnole.py. Produce overlay + residuals artifacts.

7. **State sync at end**: update plan.md (both copies), sync tasks DB to E drive.

**After Vilar lands, future work (already in todo DB):**
- Wire metabolism + transcription via resource ledger (shared ATP) — first multi-module coupled integration
- Build `solvers/hybrid.py` for ODE+SSA operator splitting (transcription bursts)
- Replan Phase 2 detail section of plan.md (per `phase2-replan-chassagnole` todo)

**Cleanup remaining:**
- Delete `_tmp_get_vilar.sh` (on disk in E:\opencell\)
</next_steps>