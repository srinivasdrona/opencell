# Checkpoint 010: Correctness guardrails + pivot to direct SBML simulation

## Overview
This checkpoint adds two audit-grade correctness guardrails (paper-pairing
verifier via NCBI eutils, PDF↔SBML digit-level cross-check), reconciles the
manifest schema between emitter/loader, and **pivots strategy** for
BioModels-curated entries: skip PDF extraction and the parameter-cards
layer entirely; let `models/metabolism.py` consume the SBML directly. The
cards machinery remains for non-deposited papers.

## History (this segment)
1. **User: "how do I do these?"** (re: prune 160 entries + add DOI + run curator)
   - I gave the literal recipe (manual prune of YAML, fill DOI, run curator)

2. **User: "I don't know any biology, what should I even look for?"**
   - Realized manual prune is a process smell. Proposed `--auto-annotate` from
     SBML names + `--sbml-as-truth` curator mode where SBML is authoritative
     and PDF is cross-check (~5–15 mismatches need human eyes, not 160 entries).

3. **User: "how are you ensuring there are no mistakes in reading the data?"**
   - Honest breakdown: SBML side deterministic + hashed (trustworthy);
     PDF side LLM-with-guardrails (quote-required, quote-verified-in-PDF,
     value-parsed-from-quote not LLM-claim); defense-in-depth via independent
     cross-check; what's still on faith (BioModels curators, pdfplumber
     fidelity, reference SBML matches what BioModels currently serves).

4. **User: "do that. but, are you sure you got the right SBML and PDF combination?"**
   - Suspicious of own claim — pubmed:17590932 is a 17xxxxxx PMID but Chassagnole
     was 2002. Called eutils → confirmed: PMID 17590932 IS Chassagnole 2002,
     DOI 10.1002/bit.10288 (PubMed indexed it 5 years late). The MIRIAM annotation
     pipeline already verified this for us. Used this as motivation for the
     dedicated verification tool.

5. **User: "yeah, add it"**
   - Got rubber-duck critique on plan; key findings adopted:
     a) Compare structured candidate value, not free-text quote
     b) DISAGREE must be BLOCKING (downgrade RECOMMEND→AMBIGUOUS), not just logging
     c) Structured `paper.pubmed_id` field, not regex over notes
     d) Schema reconciliation between emitter/loader needed FIRST
     e) Skip cross-check when candidate.method == biomodels_sbml (no tautology)
     f) Multi-PMID = fail closed, never silent first-pick
     g) Use existing convertible_to_target/converted_value, not string-compare units
   - Built `opencell/manifest/pairing.py` + `tools/verify_paper_pairing.py`
     (29 tests). Built `opencell/curation/value_match.py` + runner integration
     (13 + 5 tests). Reconciled schema. Tests: 357 pass (was 310). Verified
     end-to-end: Chassagnole manifest had blank DOI → verifier auto-filled
     10.1002/bit.10288, response_sha256 0127209c… pinned. Committed `6f75e83`.
     (Note: git commit -F via stdin hung the shell once; switched to absolute
     path to .git-commit-msg.tmp file successfully; deleted the tmp.)

6. **User: "now we have everything for the simulation? any blockers?"**
   - Honest answer: NO, we have parameter sourcing, not the simulation itself.
     Listed 8 blockers (curated Chassagnole params, sub-models, coupling,
     hybrid solver, environment, gene set, ID crosswalk, first-run).

7. **User: "update the plan first, if we run into any issues, we will lose context"**
   - Updated plan.md top sections: 357 tests, two new "COMPLETE" entries
     (correctness guardrails, schema reconciliation, GitHub mirror), explicit
     "Honest Status" section with what we have vs 8 blockers, rewritten
     "Immediate Next Steps" as 5-step ordered list anchored on Chassagnole
     curator pilot.

8. **User: "what are we going to try next? what does success look like and
   what will failure look like?"**
   - Laid out the Chassagnole curator pilot with success criteria
     (≥60% AGREE, ≤15 DISAGREE, ≤30min run, deterministic, no auto-promoted
     DISAGREEs) and 7 specific failure modes with diagnostic implications.

9. **User: "why do we need the pdf? SBML already contains the values, right?
   Do you oppose me?"**
   - **STRATEGIC PIVOT.** User is correct. For curated BioModels entries:
     SBML IS the authoritative encoding (curators read paper, encoded values).
     Pairing verifier proves SBML claims the right paper. PDF cross-check
     adds noise: pypdf mangles symbols; ~150 of 160 params would be
     NO_PDF_VALUE anyway (local kinetic constants not in paper text).
   - I was honest, did not oppose for opposition's sake. Proposed:
     for curated SBML, mark all entries Approved with provenance
     biomodels:BIOMD…(verified pairing); use cross-check for non-deposited
     papers + spot-checks. Suggested `tools/sbml_to_cards.py` + `--source=biomodels-curated` flag.

10. **User: "Not needed, use the SBML directly"**
    - Even sharper: skip the cards layer entirely for curated SBML. Models
      read SBML directly. Cards only for unverified extractions.
    - I agreed and proposed direct-SBML simulation path:
      `models/metabolism.py` reads BIOMD0000000051 → `solvers/ode.py`
      integrates → trajectory matches PySCeS oracle (G1.7 already proves this).
      Real work: MathML <kineticLaw> → JAX rate laws.

11. **User: "compact first, then let's start"** (this checkpoint)

## Work Done

### Files modified/created (committed `6f75e83`)
**New modules:**
- `opencell/manifest/pairing.py` (NEW, 9.8K) — eutils verifier, normalize_doi,
  extract_pubmed_ids (structured > notes regex), fetch_eutils with caching,
  parse_eutils_payload, verify_paper_pairing (top-level), PairingVerification
  dataclass, VerifyResult, PairingError. Multi-PMID fails closed.
- `opencell/curation/value_match.py` (NEW, 5.1K) — cross_check() returns one of
  AGREE/DISAGREE/NO_SBML/NO_PDF_VALUE/NO_UNIT_MATCH/SKIPPED_SAME_SOURCE.
  Compares candidate.converted_value vs sbml_value with rel_tol+abs_tol.
- `tools/verify_paper_pairing.py` (NEW, 5.0K) — CLI with --offline/--refresh/--update,
  exit codes 0/2/3/4 for ok/schema-error/network/MISMATCH.

**Modified:**
- `opencell/manifest/__init__.py` — export pairing symbols
- `opencell/manifest/emitter.py` — added `pubmed_id` to ManifestHeader; emits it
- `opencell/curation/manifest.py` — accept empty paper.doi (warn, not fail);
  read paper.pdf_cache as fallback for cache_files; load sbml_value/sbml_id/sbml_kind/
  pubmed_id/biomodels_id/verification per loader
- `opencell/curation/runner.py` — refuse to extract when manifest.doi empty;
  call cross_check on every recommendation; downgrade RECOMMEND→AMBIGUOUS
  on DISAGREE; persist cross_check to CurationOutcome and card.selection_rationale
- `tools/biomodels_manifest.py` — pass md.pubmed_id to ManifestHeader
- `tests/unit/test_curation.py` — added TestCrossCheckGuardrail (5 tests);
  fixed test_missing_doi to assert load OK + run_curation fails

**New tests:**
- `tests/unit/test_value_match.py` (NEW, 13 tests) — agree/disagree, edge cases
  (no_sbml, no_pdf, no_unit_match, skipped_same_source, zero/tiny values),
  serialization, custom tolerance.
- `tests/unit/test_pairing.py` (NEW, 29 tests) — normalize_doi (5),
  extract_pubmed_ids (8), parse_eutils_payload (3), fetch_eutils cache (3),
  verify_paper_pairing top-level (10).

### Test results
- Before this checkpoint: 310 passing
- After: **357 passing** (+47)
- Full suite runtime: 4m32s

### Manifest pivot decision (NOT yet implemented in code)
After completing the cross-check guardrail, user steered the project to a
*direct-SBML* path for curated BioModels entries. The cards/curator layer
remains valid but is now reserved for non-deposited papers. The next code
work is `opencell/models/metabolism.py` reading SBML directly.

## Technical Details

### eutils verifier API contract
```python
verify_paper_pairing(manifest_dict, *, cache_dir, refresh=False, offline=False)
  -> VerifyResult(ok, message, verification, auto_filled_doi, pubmed_ids_found)
```
Cache key: `.paper_cache/eutils-pubmed-{PMID}.json`. response_sha256 is over
the raw bytes (not parsed JSON) for byte-exact reproducibility.

### Cross-check semantics
- Only meaningful when both PDF candidate AND sbml_value present.
- `candidate.method == "biomodels_sbml"` → SKIPPED_SAME_SOURCE (no tautology).
- `candidate.converted_value is None` → NO_UNIT_MATCH (don't guess).
- Otherwise math.isclose(pdf, sbml, rel_tol, abs_tol).
- DISAGREE downgrades outcome.status from RECOMMEND to AMBIGUOUS, drops the
  draft card. The note records old/new values + rel_diff for human triage.

### Schema (current, post-reconciliation)
```yaml
manifest_version: '0.1'
generated_on: '2026-04-23'
generator: opencell.manifest/0.1
model_slug: chassagnole2002
paper:
  doi: 10.1002/bit.10288         # may be empty in DRAFT; verifier fills
  biomodels_id: BIOMD0000000051
  pubmed_id: '17590932'           # NEW: structured (was regex over notes)
  pdf_cache: []                    # used as cache_files fallback
  organism: Escherichia coli
  condition: ''
  notes: 'Auto-generated...; pubmed:17590932'
  verification:                    # NEW: written by verifier
    source: ncbi-eutils
    verified_at: '2026-04-23T10:16:18+00:00'
    pubmed_id: '17590932'
    doi: 10.1002/bit.10288
    title: 'Dynamic modeling of...'
    first_author: Chassagnole C
    year: '2002'
    journal: Biotechnol Bioeng
    response_sha256: 0127209cff9e44dddb8023261dc9328b91c34cd350395010655d6ac0a99cc018
    cache_path: .paper_cache/eutils-pubmed-17590932.json
parameters:
- parameter_id: chassagnole2002-catp
  symbol: catp
  target_unit: mmol/L
  sbml_id: catp                    # NEW: loader reads
  sbml_value: 4.27                 # NEW: loader reads
  sbml_kind: global_parameter      # NEW: loader reads
```

### MathML→JAX (next-step prep)
The SBML `<kineticLaw>` blocks contain MathML expressions. We have NOT
written this yet but the path is:
1. Use libsbml (NEW dependency) to parse `<kineticLaw>` → libsbml.ASTNode tree
2. libsbml has `ASTNode.toFormula()` → returns infix string (e.g.
   `(rmaxPTS * cglc * cpep) / (KPTSa1 + KPTSa2*cpep + ...)`)
3. Use sympy.parse_expr on the infix string → SymPy expression
4. sympy.lambdify(symbols, expr, modules='jax.numpy') → JAX-compilable function
5. Per-reaction validation: pick a state vector, evaluate via PySCeS reading
   same SBML, evaluate via our JAX function, assert equal.

Alternative if libsbml dependency causes issues on Windows: parse MathML
directly with ElementTree (we already do XML parsing without libsbml in
opencell/manifest/sbml.py); MathML is just XML. But libsbml's toFormula
is well-tested and saves a lot of edge-case work.

### Shell exit-code traps (committed `38e8673`)
Documented in `docs/architecture/shell-exit-codes.md`:
- bash: `cmd | tail` makes `$?` tail's; fix with `set -o pipefail`
- PowerShell intercepts `$?`/`$rc`/`$LASTEXITCODE` before bash sees them;
  fix with backtick escape `` `$? `` or use `subprocess.run(...).returncode`
Linked from `param-extractor.md` and `biology-curator.md` skill specs.

### Git workflow note
`git commit -m "long multi-line message"` over wsl pipes can hang. Use
`git commit -F /absolute/path/to/.git-commit-msg.tmp` instead, then delete
the tmp file. Confirmed working.

## Important Files

**For resuming the next session:**
- `E:\opencell\opencell\models\base.py` — abstract base class for sub-models
- `E:\opencell\opencell\models\micro_model.py` — Thattai 2001 reference impl (only existing real sub-model)
- `E:\opencell\opencell\manifest\sbml.py` — has `parse_sbml()` already; will need `parse_kinetic_law()` added
- `E:\opencell\data\biomodels_reference\BIOMD0000000051_chassagnole2002.xml` — the SBML to read directly
- `E:\opencell\manifests\chassagnole2002.draft.yaml` — has all 160 entries with sbml_value populated; usable as initial-condition + parameter source
- `E:\opencell\opencell\solvers\ode.py` — JAX-based ODE solver, already exists
- `E:\opencell\opencell\solvers\ode_scipy.py` — SciPy fallback, already exists
- `E:\opencell\tests\unit\test_pysces_oracle.py` (or similar — G1.7 gate test) — proves PySCeS reads same SBML and gives reference trajectory; reuse pattern for Chassagnole validation

**Plan + checkpoints:**
- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md` — updated this session, top sections current as of 357 tests + guardrails
- `data/biomodels_reference/README.md` — explains why we keep reference SBML in-repo
- `.github/skills/biomodels-manifest.md` — current skill spec with GitHub mirror as #1 source

## Next Steps

User has approved starting `models/metabolism.py` for Chassagnole that reads SBML directly. Don't need cards or curator for this path.

**Immediate plan:**
1. **Decide libsbml vs ElementTree** for `<kineticLaw>` parsing
   - libsbml: well-tested toFormula(), but adds C-extension dependency
     (might be tricky on Windows; check `pip install python-libsbml` works in WSL)
   - ElementTree: pure Python, we already use it, but MathML→infix is custom code
   - Recommendation: try libsbml first since we have WSL-Linux env
2. **Build `opencell/models/metabolism.py`** — class `MetabolismModel`:
   - `__init__(sbml_path)` parses SBML
   - Builds species vector (initial conditions from `<species>`)
   - Builds parameter dict from global + local `<parameter>` blocks
   - Builds rate-law functions from `<kineticLaw>` (MathML → JAX)
   - Method `dydt(t, y, params)` → JAX-compatible RHS
   - Records provenance: biomodels_id + pubmed verification block
3. **Wire to existing `solvers/ode.py`** for JAX integration
4. **Validate against PySCeS** reading the same SBML — must agree to 1e-3 rtol on glucose, G6P, F6P, PEP, pyruvate over 60s simulated time
5. **First-run script** `scripts/run_chassagnole.py` — produces PNG of glycolytic intermediates over 1 min
6. **Tests** — at minimum: SBML loads, dydt has correct shape, single-step matches PySCeS, full trajectory matches PySCeS

**If MathML→JAX gets stuck:** fallback is ODE in pure NumPy first (no JIT), validate against PySCeS, then JIT-ify. This decouples correctness from performance.

**Open question for user when work begins:**
Should `MetabolismModel` consume the SBML file directly, OR consume the
`chassagnole2002.draft.yaml` manifest (which already has sbml_value extracted)?
Manifest is convenient (already validated); direct SBML preserves rate-law
structure. Probably: SBML for rate laws + manifest for the verification
audit trail. Will propose this when starting.
