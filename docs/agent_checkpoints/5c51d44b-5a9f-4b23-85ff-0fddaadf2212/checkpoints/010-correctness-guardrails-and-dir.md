<overview>
Building OpenCell, an open-source whole-cell simulation in Python/JAX. This session segment added two audit-grade correctness guardrails (NCBI-eutils paper-pairing verifier + PDF↔SBML digit-level cross-check), reconciled the manifest schema between emitter/loader, and—after a strategic pivot driven by user feedback—decided to skip the parameter-cards layer entirely for curated BioModels entries and instead read SBML directly into `models/metabolism.py`. Test count went from 310→357 passing.
</overview>

<history>
1. **User: "how do I do these?"** (re: prune 160-entry Chassagnole manifest, add DOI, run curator)
   - Gave literal recipe (manual YAML prune, fill DOI, drop PDF in cache, run curator)

2. **User: "I don't know any biology, what should I even look for? There has to be a better way"**
   - Realized manual prune is a process smell. Proposed `--auto-annotate` and `--sbml-as-truth` modes where SBML is authoritative, PDF is cross-check, human only sees ~5–15 mismatches.

3. **User: "how are you ensuring there are no mistakes in reading the data?"**
   - Honest breakdown: SBML side deterministic+hashed (trustworthy); PDF side LLM with guardrails (quote-required, quote-verified-in-PDF, value-parsed-from-quote); defense-in-depth via independent cross-check; what's still on faith.

4. **User: "do that. but, are you sure you got the right SBML and PDF combination?"**
   - Was suspicious of own claim (PMID 17590932 looked like 2007 not 2002). Called eutils → confirmed PMID 17590932 IS Chassagnole 2002 (PubMed indexed it 5 years late), DOI 10.1002/bit.10288. Used this as motivation for dedicated verifier.

5. **User: "yeah, add it"**
   - Got rubber-duck critique. Adopted findings: compare structured candidate value not free-text quote; DISAGREE must BLOCK (downgrade RECOMMEND→AMBIGUOUS); structured `paper.pubmed_id` field; reconcile schema first; skip cross-check on biomodels-method candidates; multi-PMID fail closed; use convertible_to_target not unit string compare.
   - Built `opencell/manifest/pairing.py` + `tools/verify_paper_pairing.py` (29 tests), `opencell/curation/value_match.py` + runner integration (13+5 tests). Reconciled schema. Tests 310→357 pass. Verified end-to-end: Chassagnole blank DOI → auto-filled `10.1002/bit.10288`, response_sha256 `0127209c…` pinned.
   - Committed `6f75e83` (had to use `git commit -F /abs/path` after `-m` over WSL hung).

6. **User: "now we have everything for the simulation? any blockers?"**
   - Honest: NO, we have parameter sourcing not simulation. Listed 8 blockers (Chassagnole curated params, 5 sub-models, coupling, hybrid solver, environment, gene set, ID crosswalk, first run).

7. **User: "update the plan first, if we run into any issues, we will lose context"**
   - Updated plan.md top sections: 357 tests, two new "COMPLETE" entries, schema reconciliation, GitHub-mirror documentation, "Honest Status" section listing 8 blockers, rewritten "Immediate Next Steps" as 5-step ordered list.

8. **User: "what are we going to try next? what does success look like and what will failure look like?"**
   - Laid out Chassagnole curator pilot with success criteria (≥60% AGREE, ≤15 DISAGREE, ≤30min, deterministic) and 7 specific failure modes.

9. **User: "why do we need the pdf? SBML already contains the values, right? Do you oppose me?"**
   - **STRATEGIC PIVOT.** Agreed user is correct (didn't oppose for opposition's sake). For curated BIOMD entries: SBML is authoritative (EBI curators encoded values), pairing verifier proves correct paper, PDF adds noise (~150 of 160 would be NO_PDF_VALUE). Proposed `tools/sbml_to_cards.py` with `--source=biomodels-curated` flag.

10. **User: "Not needed, use the SBML directly"**
    - Even sharper: skip cards layer entirely for curated SBML. Models read SBML directly. Cards only for unverified extractions.
    - Agreed and proposed direct-SBML simulation path: `models/metabolism.py` reads BIOMD0000000051 → `solvers/ode.py` → trajectory matches PySCeS oracle (G1.7 already proves PySCeS agrees). Real work: MathML `<kineticLaw>` → JAX rate laws.

11. **User: "compact first, then let's start"** (this checkpoint creation)
    - Wrote `checkpoints/010-correctness-guardrails-and-pivot.md`, updated `checkpoints/index.md`.
</history>

<work_done>
**Files created (committed `6f75e83`):**
- `opencell/manifest/pairing.py` (9.8K) — eutils verifier, normalize_doi, extract_pubmed_ids (structured > notes-regex), fetch_eutils with caching, parse_eutils_payload, verify_paper_pairing, dataclasses (PairingVerification, VerifyResult, PairingError). Multi-PMID fails closed.
- `opencell/curation/value_match.py` (5.1K) — `cross_check()` returns AGREE/DISAGREE/NO_SBML/NO_PDF_VALUE/NO_UNIT_MATCH/SKIPPED_SAME_SOURCE. Compares `candidate.converted_value` vs `sbml_value` with rel_tol=0.01 + abs_tol=1e-12.
- `tools/verify_paper_pairing.py` (5.0K) — CLI with --offline/--refresh/--update; exit codes 0/2/3/4 for ok/schema/network/MISMATCH.
- `tests/unit/test_value_match.py` (13 tests)
- `tests/unit/test_pairing.py` (29 tests)

**Files modified (committed `6f75e83`):**
- `opencell/manifest/__init__.py` — export pairing symbols
- `opencell/manifest/emitter.py` — added `pubmed_id` field to `ManifestHeader`; emits it in YAML
- `opencell/curation/manifest.py` — accept empty `paper.doi` (warn not fail); read `paper.pdf_cache` as fallback for `cache_files`; load `sbml_value`/`sbml_id`/`sbml_kind`/`pubmed_id`/`biomodels_id`/`verification`
- `opencell/curation/runner.py` — refuse extract when `manifest.doi` empty; call `cross_check()` on every recommendation; downgrade RECOMMEND→AMBIGUOUS on DISAGREE; persist `cross_check` to `CurationOutcome` and to `card.selection_rationale`
- `tools/biomodels_manifest.py` — pass `md.pubmed_id` to ManifestHeader
- `tests/unit/test_curation.py` — added `TestCrossCheckGuardrail` class (5 tests including downgrade behavior); fixed `test_missing_doi` semantics

**Files created (planning only, not in git):**
- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\checkpoints\010-correctness-guardrails-and-pivot.md`
- Updated `checkpoints/index.md` with row 10
- Updated `plan.md` top sections (357 tests, guardrails complete, Honest Status, new Next Steps)

**Test results:** 357/357 passing (was 310). Full suite 4m32s. Manifest tests 36/36. Pairing 29/29. Value-match 13/13. Curation 28/28 (including 5 new cross-check tests).

**End-to-end verification:** Chassagnole manifest had blank `paper.doi` → ran `python tools/verify_paper_pairing.py --update` → auto-filled `10.1002/bit.10288` → wrote `paper.verification` block with `verified_at: 2026-04-23T10:16:18+00:00`, `response_sha256: 0127209cff9e44dddb8023261dc9328b91c34cd350395010655d6ac0a99cc018`, `cache_path: .paper_cache/eutils-pubmed-17590932.json`. Re-ran with `--offline` → succeeds from cache.

**Strategic pivot (NOT YET implemented in code):** User decided to skip the cards/curator layer for curated BioModels entries. The next code work is `opencell/models/metabolism.py` consuming SBML directly via `parse_sbml()` + a new MathML→JAX kinetic-law translator.
</work_done>

<technical_details>

### Architecture: cross-check guardrail
- Compare `candidate.converted_value` (NOT free-text from quote — duck flagged false-positive risk from neighboring numbers in quote)
- Skip when `candidate.method == "biomodels_sbml"` to avoid tautology (SKIPPED_SAME_SOURCE)
- DISAGREE is BLOCKING: runner downgrades RECOMMEND→AMBIGUOUS and drops draft card. Note records pdf_value, sbml_value, rel_diff. This was the duck's most important critique — without this it's logging not a guardrail.
- Tolerances: rel_tol=0.01 (1%) and abs_tol=1e-12 (handles zero/tiny values)
- `math.isclose(pdf, sbml, rel_tol, abs_tol)` is the comparison

### Architecture: paper-pairing verifier
- Cache key: `.paper_cache/eutils-pubmed-{PMID}.json`
- `response_sha256` is over RAW BYTES (not parsed JSON) for byte-exact reproducibility
- `paper.pubmed_id` is now STRUCTURED (was regex over notes); `extract_pubmed_ids` falls back to notes regex for back-compat
- Multiple PMIDs fail closed (no silent first-pick — duck critique)
- DOI normalization: lowercase + strip `doi:`/`https://doi.org/` prefixes; case-insensitive compare
- Exit codes: 0 ok / 2 schema-error / 3 network-or-offline-no-cache / 4 MISMATCH
- Auto-fills blank `manifest.paper.doi` only when `--update` flag passed

### Schema reconciliation
Emitter and loader had drifted:
- Emitter wrote `paper.pdf_cache`; loader read top-level `cache_files`. Fix: loader accepts both, prefers top-level.
- Emitter could write empty `paper.doi`; loader required it. Fix: loader allows empty (DRAFT state); runner refuses extraction until filled. Test `test_missing_doi` rewritten to match.
- New per-entry fields loaded: `sbml_value`, `sbml_id`, `sbml_kind`
- New paper-block fields loaded: `pubmed_id`, `biomodels_id`, `verification`

### MIRIAM annotation pipeline (background context)
- `<bqmodel:is>` → biomodels.db ID
- `<bqmodel:isDescribedBy>` → pubmed ID (NOT directly DOI; DOIs rare in BioModels annotations)
- `<bqbiol:hasTaxon>` → NCBI taxonomy ID

### PMID 17590932 quirk
PubMed indexed Chassagnole 2002 in 2007, hence the 17xxxxxx ID despite being a 2002 paper. The eutils call confirms `pubdate: "2002 Jul 5"` and `doi: "10.1002/bit.10288"`. This is the kind of mistake the verifier catches.

### Shell traps (committed `38e8673`, unchanged this segment)
1. bash: `cmd | tail` makes `$?` = tail's exit code. Fix: `set -o pipefail`.
2. PowerShell intercepts `$?`, `$rc`, `$LASTEXITCODE` before bash sees them when going through `wsl.exe`. Fix: backtick escape `` `$? `` or use `subprocess.run(...).returncode`.
3. **NEW finding this session**: `git commit -m "long multi-line message"` over WSL pipe HUNG the shell. Workaround: `git commit -F /absolute/path/to/.git-commit-msg.tmp` works reliably. Always use absolute path.

### MathML → JAX (next step, not yet built)
Path A (preferred): libsbml (C extension; install via `pip install python-libsbml` in WSL) → `ASTNode.toFormula()` → infix string → `sympy.parse_expr` → `sympy.lambdify(symbols, expr, modules='jax.numpy')`.
Path B (fallback): pure ElementTree MathML walker (we already use ET in `opencell/manifest/sbml.py`); more edge cases but no C dependency.
Decoupling: ODE in pure NumPy first → validate against PySCeS → JIT-ify after.

### Open question for next session
Should `MetabolismModel` consume SBML file directly OR consume `chassagnole2002.draft.yaml` manifest (which has `sbml_value` already extracted)?  
Likely answer: SBML for rate laws + manifest for verification audit trail.
</technical_details>

<important_files>

- **`E:\opencell\opencell\manifest\pairing.py`** (NEW)
  - eutils-based paper-pairing verifier; the trust foundation for "is this the right paper?"
  - Functions: `normalize_doi`, `extract_pubmed_ids`, `fetch_eutils`, `parse_eutils_payload`, `verify_paper_pairing`
  - Dataclasses: `PairingVerification`, `VerifyResult`, `PairingError`

- **`E:\opencell\opencell\curation\value_match.py`** (NEW)
  - PDF↔SBML digit-level cross-check guardrail
  - Single function: `cross_check(candidate, sbml_value, *, rel_tol, abs_tol)`
  - Status constants: AGREE, DISAGREE, NO_SBML, NO_PDF_VALUE, NO_UNIT_MATCH, SKIPPED_SAME_SOURCE

- **`E:\opencell\tools\verify_paper_pairing.py`** (NEW)
  - CLI for the verifier; supports `--update`, `--offline`, `--refresh`, `--cache-dir`

- **`E:\opencell\opencell\curation\runner.py`** (MODIFIED)
  - Lines ~110-180: `run_curation()` now refuses doi-empty manifests, calls `cross_check`, downgrades RECOMMEND→AMBIGUOUS on DISAGREE
  - `_build_draft_card()` now records cross-check status in selection_rationale

- **`E:\opencell\opencell\curation\manifest.py`** (MODIFIED)
  - `ManifestParameter` gained `sbml_value`, `sbml_id`, `sbml_kind`
  - `CurationManifest` gained `pubmed_id`, `biomodels_id`, `verification`
  - `load_manifest` accepts empty doi; reads `paper.pdf_cache` fallback

- **`E:\opencell\opencell\manifest\emitter.py`** (MODIFIED)
  - `ManifestHeader` gained `pubmed_id`; emitted in YAML

- **`E:\opencell\manifests\chassagnole2002.draft.yaml`** (MODIFIED)
  - Now has `paper.pubmed_id: '17590932'`, `paper.doi: 10.1002/bit.10288`, full `paper.verification` block. 160 entries, sbml_value populated, ready for direct simulation.

- **`E:\opencell\data\biomodels_reference\BIOMD0000000051_chassagnole2002.xml`** (committed previously)
  - 137KB SBML; this is what `models/metabolism.py` will read directly

- **`E:\opencell\opencell\models\base.py`** + **`micro_model.py`** (existing, not modified)
  - The skeleton + Thattai 2001 reference impl. Pattern to follow for new `metabolism.py`.

- **`E:\opencell\opencell\manifest\sbml.py`** (existing, not modified this segment)
  - Has `parse_sbml()`. Will need a new `parse_kinetic_law()` for MathML→JAX.

- **`E:\opencell\opencell\solvers\ode.py`** + **`ode_scipy.py`** (existing)
  - JAX-based + SciPy fallback ODE solvers. Already exist; will be wired to MetabolismModel.

- **`E:\opencell\.paper_cache\eutils-pubmed-17590932.json`** (NEW, gitignored)
  - Cached eutils response, response_sha256 `0127209c…` pinned in manifest verification block

- **`C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`** (UPDATED top sections)
  - Now documents 357 tests, both new guardrails as COMPLETE, schema reconciliation, GitHub-mirror discovery, Honest Status section with 8 blockers, 5-step Immediate Next Steps

- **`C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\checkpoints\010-correctness-guardrails-and-pivot.md`** (NEW)
  - Detailed checkpoint of this session segment for future-session resume
</important_files>

<next_steps>

**Immediate (user said "compact first, then let's start"):**
The user has approved starting `opencell/models/metabolism.py` reading SBML directly. No PDF, no cards, no curator for Chassagnole.

**Step-by-step plan:**
1. **Decide MathML→JAX approach**:
   - Try `pip install python-libsbml` in WSL first
   - If installs cleanly → use `libsbml.ASTNode.toFormula()` + `sympy.parse_expr` + `sympy.lambdify(modules='jax.numpy')`
   - If fails → fallback to ElementTree MathML walker (we already use ET in sbml.py)
2. **Build `opencell/models/metabolism.py`**:
   - `class MetabolismModel`
   - `__init__(sbml_path)` parses SBML once
   - Builds species vector + initial conditions from `<species>` initialConcentration
   - Builds parameter dict from global + local `<parameter>` blocks
   - Builds rate-law functions from `<kineticLaw>` MathML
   - Method `dydt(t, y, params)` → JAX-compatible RHS
   - Records provenance: biomodels_id + verification block (read from manifest sidecar)
3. **Wire to `solvers/ode.py`** for JAX integration
4. **Validate against PySCeS** reading the same SBML — must agree to 1e-3 rtol on glucose, G6P, F6P, PEP, pyruvate over 60s simulated time. Reuse the G1.7 oracle test pattern.
5. **First-run script** `scripts/run_chassagnole.py` — produces PNG of glycolytic intermediates over 1 min
6. **Tests** — at minimum: SBML loads; `dydt` correct shape; single-step matches PySCeS; full trajectory matches PySCeS

**Open question to confirm with user when starting:**
Should `MetabolismModel` consume SBML file directly OR consume `chassagnole2002.draft.yaml` manifest (which already has sbml_value extracted)?
Suggested answer: SBML for rate laws + manifest for verification audit trail. (Both come from the same source, so no contradiction risk.)

**If MathML→JAX gets stuck:**
Fallback is ODE in pure NumPy first (no JIT) → validate against PySCeS → JIT-ify later. Decouples correctness from performance.

**Blockers:** None known. The user is ready to proceed.
</next_steps>