<overview>
Building OpenCell, an open-source whole-cell simulation in Python/JAX. This session continued the AI-skill-based deterministic parameter pipeline: built `biology-curator` agent, fixed shell exit-code documentation, then sourced the Chassagnole 2002 SBML via GitHub mirror (since BioModels API returns HTTP 403). Currently adding MIRIAM-annotation auto-fill to `biomodels-manifest`; one creator-extraction test fails and needs fixing.
</overview>

<history>
1. **User: "How to fix the bash's tail exit code issue?"**
   - Explained 3 fixes: `set -o pipefail`, `${PIPESTATUS[0]}`, capture via subprocess
   - Tried to verify with WSL but exit code looked wrong (returned 0)
   - Discovered the issue was actually **PowerShell intercepting `$?` and `$rc`** before bash saw them — the curator was correctly returning 2 all along (verified via `subprocess.run(...).returncode`)

2. **User: "yeah, don't want to keep running into the same issue"**
   - Created `docs/architecture/shell-exit-codes.md` with both traps (bash pipes + PowerShell interception) and 3 fixes each
   - Added short warning + link from `param-extractor.md` and `biology-curator.md` skill specs
   - Committed as `38e8673`

3. **User: "Biomodels site is down, returns 403 error from multiple machines. Any other way to get actual data?"**
   - Listed alternatives: GitHub mirror (`github.com/biomodels/<id>`), EBI FTP, JWS Online, Wayback, Zenodo
   - Tested GitHub mirror — `git clone https://github.com/biomodels/BIOMD0000000051.git` worked instantly
   - Copied 137KB SBML to `.paper_cache/`, ran `tools/biomodels_manifest.py` end-to-end
   - Successfully generated 160-entry manifest (7 global + 135 local + 18 species, 5 unit definitions) for Chassagnole 2002

4. **User: "do 1 and 2, also save a copy of the file locally for reference"**
   - (1) Add MIRIAM annotation auto-fill, (2) Update skill spec with GitHub mirror trick
   - Inspected SBML annotations: found `bqmodel:is`, `bqmodel:isDescribedBy`, `bqbiol:hasTaxon`
   - Added `SbmlModelMetadata` dataclass + `extract_metadata()` to `opencell/manifest/sbml.py` with static taxonomy table (E. coli=562, etc.)
   - Updated `opencell/manifest/__init__.py` to export new symbols
   - Rewrote `tools/biomodels_manifest.py` with `--no-auto-metadata` flag, auto-fill logic, GitHub-mirror fallback message in error path and docstring
   - Created `.github/skills/biomodels-manifest.md` (new skill doc, 3936 chars)
   - Saved reference copy to `data/biomodels_reference/BIOMD0000000051_chassagnole2002.xml` + README
   - Added `TestModelMetadata` class with 10 tests to `tests/unit/test_manifest.py`
   - Ran tests: **35 pass, 1 fails** — `test_creators_extracted` expects "Jacky Snoep" but `_collect_creators()` only got "Snoep" (lost the Given name)
   - **Compaction occurred here, before bug fixed or commit made**
</history>

<work_done>
Files created/modified this session (continuation segment):

**Earlier in this segment (committed 38e8673):**
- `docs/architecture/shell-exit-codes.md` (NEW) — bash pipe + PowerShell `$?` traps
- `.github/skills/param-extractor.md` (MODIFIED) — added shell exit-code section
- `.github/skills/biology-curator.md` (MODIFIED) — added shell exit-code section

**Current uncommitted work (this turn):**
- `opencell/manifest/sbml.py` (MODIFIED): added `SbmlModelMetadata` dataclass after `SbmlEntity`; added `_TAXONOMY_NAMES` dict; appended `extract_metadata()` and helpers (`_collect_resource_uris`, `_collect_creators`, `_extract_notes_excerpt`, regex constants `_BIOMODELS_RX`, `_PUBMED_RX`, `_DOI_RX`, `_TAXONOMY_RX`)
- `opencell/manifest/__init__.py` (MODIFIED): exported `SbmlModelMetadata`, `extract_metadata`
- `tools/biomodels_manifest.py` (FULLY REWRITTEN): added `--no-auto-metadata` flag, auto-fill from MIRIAM with `_pick()` helper, GitHub-mirror fallback in error path + epilog, runtime "auto-filled from SBML" report
- `.github/skills/biomodels-manifest.md` (NEW): full skill spec with prominent GitHub-mirror section as the recommended SBML source
- `data/biomodels_reference/BIOMD0000000051_chassagnole2002.xml` (NEW, 137KB): permanent reference copy of Chassagnole SBML
- `data/biomodels_reference/README.md` (NEW): explains why this directory exists, lists files, how to add more
- `tests/unit/test_manifest.py` (MODIFIED): added `ANNOTATED_SBML` fixture and `TestModelMetadata` class with 10 tests
- `.paper_cache/BIOMD0000000051.xml` (NEW, gitignored): working cache of same SBML

Test status:
- **35 of 36 manifest tests pass; 1 fails**: `test_creators_extracted` — `_collect_creators()` produces `['Snoep']` instead of `['Jacky Snoep']`. The Given/Family iteration logic doesn't capture both before resetting.
- Full suite NOT yet re-run since the metadata changes
- NOT yet committed

Earlier in session (committed da186b1, 2ee9284):
- `biology-curator` agent: `opencell/curation/{__init__.py, manifest.py, runner.py, emitter.py}`, `tools/curate_params.py`, `.github/skills/biology-curator.md`, `tests/unit/test_curation.py` (23 tests including Thattai 2001 replay)
- `biomodels-manifest`: `opencell/manifest/{__init__.py, sbml.py, emitter.py}`, `tools/biomodels_manifest.py`, `tests/unit/test_manifest.py` (26 tests)

Test counts:
- Before this session segment: 277 passing
- After biology-curator: 300 passing
- After metadata work: should be ~310 once creator bug is fixed
</work_done>

<technical_details>

### Bug to fix in `_collect_creators()` — sbml.py
Current logic iterates every element setting `given`/`family` and only emits when both seen. But `vCard:Given` element is encountered before `vCard:Family` in iteration; when `Family` is set, code emits and resets. Looking at output `['Snoep']` — only the family got captured. The Given assignment is being overwritten or its `elem.text` is None during iteration. **Likely issue**: `vCard:Given` element has child `<vCard:Given>Jacky</vCard:Given>` directly inside `<vCard:N>`, but my logic uses `_localname(elem.tag)` which strips namespace. Need to debug — possibly the Given text is whitespace or being missed because iteration order differs from XML order. Quick fix: collect text from BOTH children of any `<vCard:N>` parent, then emit "Given Family" together.

### MIRIAM annotation patterns confirmed in Chassagnole SBML:
- `<bqmodel:is>` → biomodels.db identifier (BIOMD0000000051)
- `<bqmodel:isDescribedBy>` → pubmed identifier (17590932 for Chassagnole 2002)
  - Note: PubMed ID does NOT directly give DOI; DOI URLs are RARE in BioModels annotations
- `<bqbiol:hasTaxon>` → taxonomy/562 (E. coli)
- DOIs not present → user must look up manually after metadata extraction; CLI prints helpful note

### GitHub mirror confirmed working
- `https://github.com/biomodels/<BIOMD_ID>.git` → repo with `<BIOMD_ID>/<BIOMD_ID>.xml`
- No WAF/Cloudflare; no auth; instant clone
- This is now the canonical primary source documented across all relevant places

### Shell exit-code traps (definitive answer)
1. **bash pipe**: `cmd | tail` → `$?` is tail's, not cmd's. Fix: `set -o pipefail` OR `${PIPESTATUS[0]}` OR avoid pipe.
2. **PowerShell-to-WSL**: `$?`, `$_`, `$args`, `$LASTEXITCODE`, `$rc` all intercepted by PowerShell before reaching bash even inside single quotes (when going through `wsl.exe`). Fix: PowerShell backtick escape `` `$? `` OR run from real `.sh` file OR use `subprocess.run(...).returncode` from Python.

### Auto-fill semantics (CLI design decision)
- CLI flags WIN over auto-fill (explicit > implicit)
- `--no-auto-metadata` to disable when SBML annotations are wrong
- Tool prints "auto-filled from SBML: doi=..., organism=..." so user can see what happened
- Special note when only PubMed but no DOI: tells user to look up DOI and rerun

### Reference file separation
- `.paper_cache/` → gitignored, working scratch
- `data/biomodels_reference/` → committed, permanent SHA-256-stable references
- This split needed so SHA-256s recorded by extractor are reproducible across machines

### Test status / commits
- Last commit: `38e8673` (shell exit-code docs)
- Pending uncommitted changes: all the metadata work + Chassagnole reference copy
- Need to: fix `_collect_creators` bug, verify all 36 manifest tests pass, run full suite, regenerate Chassagnole manifest with new metadata-aware CLI to verify auto-fill in action, commit
</technical_details>

<important_files>

- **`E:\opencell\opencell\manifest\sbml.py`** (MODIFIED, uncommitted)
  - Core SBML walker; now also holds metadata extractor
  - Added `SbmlModelMetadata` dataclass (~line 50 area)
  - Added `_TAXONOMY_NAMES` static dict (E.coli=562, S.cerevisiae=4932, human=9606, etc.)
  - Appended at end (after `parse_sbml`): regex constants, `_collect_resource_uris`, `_collect_creators` (BUGGY), `_extract_notes_excerpt`, `extract_metadata`
  - **Bug**: `_collect_creators` produces `['Snoep']` instead of `['Jacky Snoep']` — fix needed

- **`E:\opencell\tools\biomodels_manifest.py`** (REWRITTEN, uncommitted)
  - CLI now auto-fills from MIRIAM when CLI flags absent
  - `--no-auto-metadata` to disable
  - GitHub-mirror fallback printed on download failure + in epilog
  - `_pick(cli_value, sbml_value, label)` helper for the precedence rule

- **`E:\opencell\opencell\manifest\__init__.py`** (MODIFIED, uncommitted)
  - Exports `SbmlModelMetadata`, `extract_metadata` alongside existing symbols

- **`E:\opencell\tests\unit\test_manifest.py`** (MODIFIED, uncommitted)
  - Added `ANNOTATED_SBML` fixture (mimics Chassagnole annotation block)
  - Added `TestModelMetadata` class — 10 tests, 9 pass, 1 fails (`test_creators_extracted`)

- **`E:\opencell\.github\skills\biomodels-manifest.md`** (NEW, uncommitted)
  - Skill spec for biomodels-manifest tool
  - Prominent "How to get the SBML" section with GitHub mirror as #1
  - Auto-fill semantics, hard constraints, hand-off to curator

- **`E:\opencell\data\biomodels_reference\BIOMD0000000051_chassagnole2002.xml`** (NEW, uncommitted)
  - Reference copy of Chassagnole SBML, 137KB, SBML L2v1
  - Source: github.com/biomodels/BIOMD0000000051

- **`E:\opencell\data\biomodels_reference\README.md`** (NEW, uncommitted)
  - Explains directory purpose, lists files, GitHub-mirror recipe

- **`E:\opencell\.paper_cache\BIOMD0000000051.xml`** (NEW, gitignored)
  - Working cache; same content as reference copy

- **`E:\opencell\manifests\chassagnole2002.draft.yaml`** (NEW, may need regenerate)
  - 160-entry manifest generated BEFORE auto-fill was added
  - `paper.doi`, `biomodels_id`, `organism` empty because flags not passed
  - Should regenerate after fix to demonstrate auto-fill working

- **`E:\opencell\docs\architecture\shell-exit-codes.md`** (committed `38e8673`)
  - Reference doc for both bash pipe and PowerShell exit-code traps

- **`C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`**
  - Was updated this session with biology-curator + biomodels-manifest entries
  - May want to add biomodels-reference + auto-fill note when committing
</important_files>

<next_steps>

**Immediate (resume point — small bug):**
1. **Fix `_collect_creators()` in `opencell/manifest/sbml.py`** — change logic to find each `<vCard:N>` element and pull both Given+Family from its children, instead of streaming Given/Family separately. Likely simplest:
   ```python
   def _collect_creators(model_elem):
       out = []
       for elem in model_elem.iter():
           if _localname(elem.tag) == "N":
               given = family = ""
               for child in elem:
                   ln = _localname(child.tag)
                   if ln == "Given":
                       given = (child.text or "").strip()
                   elif ln == "Family":
                       family = (child.text or "").strip()
               name = " ".join(x for x in (given, family) if x)
               if name:
                   out.append(name)
       return out
   ```
2. **Re-run `pytest tests/unit/test_manifest.py`** — expect 36/36 pass
3. **Re-run full test suite** — expect ~310 passing (was 300 before metadata tests)
4. **Regenerate Chassagnole manifest with new CLI** to verify auto-fill in action:
   ```bash
   set -o pipefail
   python tools/biomodels_manifest.py \
     --sbml-path data/biomodels_reference/BIOMD0000000051_chassagnole2002.xml \
     --model-slug chassagnole2002 \
     --output manifests/chassagnole2002.draft.yaml
   ```
   Should print "auto-filled from SBML: biomodels_id='BIOMD0000000051', organism='Escherichia coli'"
5. **Commit** all uncommitted changes — single commit covering: metadata extraction, Chassagnole reference copy, biomodels-manifest skill spec, GitHub-mirror documentation, regenerated manifest

**SQL todo updates needed at commit time:**
- Mark `biomodels-github-mirror-noted` done
- Keep `chassagnole-manifest-pruned` pending (waits for human pruning)

**After this:**
- User to manually prune the 160-entry Chassagnole manifest, fill DOI (10.1002/bit.10288 — Chassagnole 2002 Biotech Bioeng), add gene_or_enzyme annotations
- Then run `tools/curate_params.py` on it for end-to-end pilot
- Update plan.md Phase 2 sections per `phase2-replan-chassagnole` todo

**Plan.md update (already done in last segment):**
- Already has biomodels-manifest + biology-curator entries; minor update may add the GitHub-mirror discovery
</next_steps>