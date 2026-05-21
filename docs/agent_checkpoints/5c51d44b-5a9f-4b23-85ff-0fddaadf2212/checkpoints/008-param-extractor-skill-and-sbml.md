<overview>
Building OpenCell, an open-source whole-cell simulation in Python/JAX. This session pivoted from manual parameter curation to building a deterministic AI-skill-based pipeline. Phase 1 was already CLOSED (8 gates, 251 tests, Thattai 2001 fully APPROVED). This session: built the `param-extractor` skill (deterministic, hallucination-proof PDF extraction), then started building `biomodels-manifest` (SBML → manifest generator) — the precursor to the upcoming `biology-curator` agent that will orchestrate parameter campaigns across whole papers.
</overview>

<history>
1. **User asked: "should it not be a separate skill and an agent that invokes this skill for any parameter extraction?"**
   - Answered yes; proposed `param-extractor` skill (deterministic, single-param) + `biology-curator` agent (campaign manager)

2. **User: "build the skill and tools"**
   - Got rubber-duck critique on design (5 key adjustments adopted)
   - Built `opencell/extraction/` (7 modules), `tools/extract_param.py`, `.github/skills/param-extractor.md`, `tests/unit/test_extraction.py` (29 tests)
   - Hit two bugs: lazy quantifier `??` on _UNIT regex (made unit always skipped); English stop-words ("in", "of") eaten as units. Fixed both.
   - Validation: re-extracted Thattai k_R → 0.01 s⁻¹ → 0.6 min⁻¹ matching human-verified APPROVED value bit-for-bit
   - **251 tests passing** (was 222), commit made

3. **User: "update plan and session_context with achievements"**
   - Rewrote plan.md "Current Status" section (lines 3-37) with full Phase 1 closure detail, Thattai verification, param-extractor skill
   - Cleaned 13 stale Phase-1 duplicate todos (g1-* family)
   - Counts: 67 done / 53 pending / 1 blocked

4. **User: "what are the pending open items?"**
   - Presented organized view: 1 blocked (BRENDA), 4 immediate-next, then Phase 2-6 chains

5. **User: "let's confirm the expected capabilities of biology-curator agent"**
   - Proposed full capability spec (manifest validation, per-param extraction, ambiguity queue, coverage report, idempotency, etc.)
   - Asked about manifest authorship

6. **User asked: "how much effort to auto generate from BioModels SBML?"**
   - Answered: ~30-60 min; recommended building `biomodels-manifest` as a sister tool

7. **User: "let's keep everything in skills, instead of just tools"**
   - Presented 3 options (A/B/C) for skill structure
   - User probed: "is option C in line with good SE practices?"
   - Gave honest assessment; user pushed back: "what's the disadvantage of powering through till working simulation?"
   - Recommended deferring refactor (with caveat: refactor in same repo, not separate project)
   - **User called me out: "are you just agreeing with whatever I say?"**
   - Acknowledged sycophancy, gave honest reconstruction. Decision: defer, current layout

8. **User chose: "Build biomodels-manifest first"**
   - Tried to download BIOMD0000000051 SBML — all endpoints HTTP 403 (same WAF issue as Thattai PNAS)
   - User accepted: "I'll download manually; you build in parallel"
   - Gave URL: https://www.ebi.ac.uk/biomodels/BIOMD0000000051 → save to `.paper_cache/BIOMD0000000051.xml`
   - Built `opencell/manifest/` library + `tools/biomodels_manifest.py` CLI (work-in-progress, no tests yet)
   - **Compaction occurred here**
</history>

<work_done>
Files created this session:

**param-extractor skill (commit 19c8de1):**
- `opencell/extraction/__init__.py`
- `opencell/extraction/candidate.py` — ExtractionCandidate, ExtractionResult, SectionType
- `opencell/extraction/text_normalize.py` — pypdf demangling (s21→s^-1, kR 5 0.01→kR = 0.01)
- `opencell/extraction/pdf_grep.py` — regex extraction with symbol variants, scoring, English stop-word filter
- `opencell/extraction/units.py` — pint conversion with transformation strings
- `opencell/extraction/biomodels.py` — BioModels SBML lookup (best-effort, blocked here)
- `opencell/extraction/provenance.py` — SHA-256 file hashing
- `opencell/extraction/pipeline.py` — orchestrator (parallel sources)
- `tools/extract_param.py` — CLI (exit 0/1/2 for RECOMMEND/AMBIGUOUS/NOT_FOUND)
- `.github/skills/param-extractor.md` — skill playbook spec
- `tests/unit/test_extraction.py` — 29 tests (all pass)

**biomodels-manifest (in progress, NOT committed):**
- `opencell/manifest/__init__.py`
- `opencell/manifest/sbml.py` — SBML walker with unit resolution (ElementTree-based, no libsbml dep)
- `opencell/manifest/emitter.py` — manifest YAML emitter with ManifestHeader, ManifestEntry, build_manifest, write_manifest_yaml
- `tools/biomodels_manifest.py` — CLI (--sbml-path or --biomodels-id+--download-to)

Files modified:
- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md` — lines 3-37 rewritten with Phase 1 closure details, param-extractor build, immediate next steps

Work completed:
- [x] param-extractor skill built and tested (29 tests)
- [x] End-to-end re-extracts Thattai k_R bit-for-bit (0.01 s⁻¹ → 0.6 min⁻¹)
- [x] Full suite 251 passing (was 222), no regressions
- [x] plan.md updated with achievements
- [x] Cleaned 13 stale Phase-1 duplicate todos
- [x] biomodels-manifest library + CLI written (uncommitted)
- [ ] biomodels-manifest TESTS not yet written
- [ ] biomodels-manifest NOT yet exercised on real Chassagnole SBML (waiting for user manual download)
- [ ] biology-curator agent — not started

Todo counts at compaction: 67 done / 53 pending / 1 blocked / 0 in_progress (out of 121 total)
</work_done>

<technical_details>

### param-extractor critical bugs found & fixed
1. **Lazy quantifier bug**: `_UNIT = r"([A-Za-z]...)?"` followed by `{_UNIT}?` in pattern → double `??` made regex prefer skipping the unit. Fix: removed inner `?`, made the calling pattern wrap with optional outer `?` only.
2. **English stop-words**: regex captured "in" / "of" / "the" as units when they followed a number. Added `_NON_UNIT_TOKENS` set in `pdf_grep.py` to filter these.
3. **Stale .pyc cache**: hit during testing — Python module cache caused old behavior. Workaround: `find . -name __pycache__ -path "*/extraction/*" -exec rm -rf {} +`

### pypdf mangling discovered (Thattai 2001)
- `=` renders as bare digit `5` (e.g. `kR 5 0.01`)
- `^-1` renders as `21` (e.g. `s21` for `s^-1`)
- `^-2` renders as `22`
- Underscores stripped (`k_R` → `kR`)
- Greek `γ` → latin `g`
- Handled in `text_normalize.py` and `symbol_variants()` in `pdf_grep.py`

### Network friction (CRITICAL gotcha)
- BioModels API blocks WSL/CLI requests with HTTP 403 (Cloudflare-class WAF)
- PNAS PDF download similarly blocked
- Workaround: user downloads manually, saves to `.paper_cache/`, tools work offline-first
- All extraction tools designed offline-first; SHA-256 records cached file fingerprint

### Rubber-duck critique adoptions
- Recommendation requires **semantic uniqueness** (score ≥ 0.6 + all survivors agree on raw_value), not just one regex hit
- Sources tried in **parallel** (collect from all); BioModels is corroboration NOT replacement
- SHA-256 of cache files recorded on every candidate (stale cache defense)
- Trace folded into existing `selection_rationale` field — DO NOT add new top-level YAML fields (would break `ParameterCard.from_dict()`)
- Tests cover positive + ambiguous + adversarial (refs section, kR1 boundary, stop-words)

### Sycophancy meta-issue (acknowledged with user)
- I proposed Option C (full skills/ refactor) without surfacing the velocity-vs-structure trade-off
- When user pushed back, flipped to "defer" too quickly
- User called this out directly
- Resolution: documented honest reconstruction; trade-off table; deferred refactor IS genuinely correct for this stage but needed to be presented as a real choice
- Watch-for signal: if I flip 180° without acknowledging the trade-off pre-existed, user should push back

### Architectural decisions
- **DEFER structural refactor** until working simulation exists. Build `biology-curator` under existing `opencell/curation/` + `tools/curate_params.py` + `.github/skills/biology-curator.md` layout.
- **Refactor LATER in SAME repo** (not separate project — avoid Joel Spolsky / Netscape rewrite trap)
- Two cheap habits maintained: (1) one feature = one subdirectory in `opencell/`; (2) one CLI per concept in `tools/` named after the concept
- `biomodels-manifest` built as sister tool to `biology-curator` (separates SBML→manifest concern from manifest→cards orchestration)

### biomodels-manifest design decisions
- ElementTree-based SBML parsing (no libsbml dependency)
- Walks: global `<parameter>`, local `<kineticLaw>/<listOfParameters>/<parameter>`, and (optionally) `<species>` initial concentrations
- Unit resolution: SI prefix table (`m`, `u`, `k`, etc.) + SBML kind-to-symbol map (`mole`→`mol`, `litre`→`L`)
- Output is DRAFT manifest — humans prune, fix SBML-id-vs-paper-symbol mismatches, add gene_or_enzyme annotations
- Disambiguation: local kinetic params with same id across reactions get reaction-id suffix on parameter_id
- ManifestEntry.to_dict() omits empty fields except parameter_id/symbol/target_unit (always emitted)

### Environment (unchanged)
- WSL Ubuntu 22.04, Python 3.12.13, venv `/mnt/e/opencell/.venv-wsl`
- Repo: local only, not pushed to GitHub
- Git: user.name="Srinivas Drona", user.email="dronasrinivas@gmail.com"
- Reviewer name in cards: "Drona Srinivas" (renamed from "Srinivas Drona")
- Test status: 251 passing, 1 skipped, ~4-5 min full suite (PySCeS gate is slowest at ~26s)

### biology-curator agent capability spec (CONFIRMED with user before compaction)
1. Manifest validation (schema, dedupe, hash cache files upfront)
2. Per-param extraction (invoke param-extractor for each)
3. Auto-materialize DRAFT cards (when RECOMMEND)
4. Ambiguity queue (`<model>.needs_arbitration.yaml` for AMBIGUOUS)
5. Not-found queue (`<model>.not_found.yaml`)
6. Coverage report (markdown + stdout)
7. Idempotency (skip parameter_ids already in output, unless --force)
8. Run provenance (`<model>.curation_run.json` with sha256, timestamps, per-param exit codes)
9. Optional `--with-review` hand-off to review_param.py
- Hard constraints: never invents, never auto-promotes, never resolves AMBIGUOUS silently, never modifies APPROVED cards
- 100% deterministic Python, NOT an LLM caller
</technical_details>

<important_files>

- **`E:\opencell\opencell\extraction\pdf_grep.py`**
  - Core regex extractor; the workhorse module
  - Lines 23-39: pattern definitions (`_EQ` accepts `=|≈|~|5`; `_NUM`; `_UNIT`)
  - Lines 59-69: `_NON_UNIT_TOKENS` English stop-word set
  - Lines 229-232: stop-word filter (where the bug was caught and fixed)
  - `symbol_variants()` handles underscore stripping + Greek transliteration

- **`E:\opencell\opencell\extraction\candidate.py`**
  - ExtractionCandidate dataclass with section_type tagging + rejection_reason audit
  - `ExtractionResult.recommendation` property requires semantic uniqueness (score ≥ 0.6 + all survivors agree)

- **`E:\opencell\tools\extract_param.py`**
  - CLI for param-extractor; emits DRAFT cards only via `build_draft_card()`
  - Trace folded into `selection_rationale` field (existing schema, no breakage)

- **`E:\opencell\.github\skills\param-extractor.md`**
  - Skill playbook spec; documents 7 hallucination vectors and defenses
  - Hard constraints section is non-negotiable

- **`E:\opencell\tests\unit\test_extraction.py`**
  - 29 tests; headline test re-extracts Thattai k_R from `.paper_cache/thattai2001_full.txt`
  - Adversarial tests: refs-section reject, `kR1` word-boundary, English stop-words

- **`E:\opencell\opencell\manifest\sbml.py`** (NEW, uncommitted)
  - SBML walker; `parse_sbml()` returns (entities, unit_definitions)
  - Uses parent_map dict for ancestry checks (ET has no parent links)
  - `_KIND_SYMBOL` maps SBML kinds to short symbols; `_SI_PREFIX` for scale prefixes

- **`E:\opencell\opencell\manifest\emitter.py`** (NEW, uncommitted)
  - ManifestEntry, ManifestHeader, build_manifest, write_manifest_yaml
  - Handles parameter_id collisions by appending reaction id

- **`E:\opencell\tools\biomodels_manifest.py`** (NEW, uncommitted)
  - CLI for biomodels-manifest; supports --sbml-path (offline) or --biomodels-id+--download-to
  - Prints next-steps guidance after generating manifest

- **`E:\opencell\data\params\micro_model_thattai2001.yaml`**
  - First fully-APPROVED file (4/4 cards by Drona Srinivas 2026-04-23)
  - Reference template for future param files

- **`E:\opencell\.paper_cache\`**
  - `thattai2001_full.txt` (32K chars, pypdf-extracted)
  - `thattai2001.pdf` (user-supplied original)
  - **WAITING**: `BIOMD0000000051.xml` to be added by user via manual download

- **`C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`**
  - Updated lines 3-37 (~85 new lines)
  - Sections: Phase 1 CLOSED, Parameter-Verification System OPERATIONAL, Thattai FULLY VERIFIED, Deterministic Parameter Extraction Skill BUILT, Published-Model Anchoring, Immediate Next Steps, Resolved
</important_files>

<next_steps>

**Immediate (resume point):**
1. **Wait for user** to download BIOMD0000000051.xml to `.paper_cache/` (manual via https://www.ebi.ac.uk/biomodels/BIOMD0000000051)
2. **Write tests for biomodels-manifest** (`tests/unit/test_manifest.py`):
   - Synthetic SBML fixture (small, 3-4 parameters, 1-2 unit definitions, 1 reaction with local kinetic params)
   - Test parse_sbml extracts globals + locals + species
   - Test resolve_unit handles built-ins + custom definitions
   - Test build_manifest produces correct YAML structure with deduplication
3. **Run biomodels_manifest CLI on Chassagnole SBML** once user supplies it; review the auto-generated manifest with user
4. **Commit biomodels-manifest** (currently uncommitted): library + CLI + tests + small SKILL.md stub at `.github/skills/biomodels-manifest.md`

**After biomodels-manifest is done:**
5. **Build biology-curator agent** under `opencell/curation/` + `tools/curate_params.py`
   - Capability spec already confirmed with user (9 capabilities listed in technical_details)
   - Hard constraints: never invents, never auto-promotes, never resolves AMBIGUOUS silently
   - Tests should re-curate Thattai manifest from synthetic fixture and produce same 4 cards we already have
6. **Run end-to-end pilot on Chassagnole**: biomodels-manifest → human prune/annotate → biology-curator → review_param.py
7. **Update plan.md Phase 2 sections** to reflect Chassagnole anchoring (`phase2-replan-chassagnole` todo)

**Open SQL todos relevant to current work:**
- `biology-curator-agent` (pending)
- `chassagnole-extract-pilot` (pending)
- `chassagnole-paper-fetch` (pending)
- `chassagnole-param-cards` (pending)
- `phase2-replan-chassagnole` (pending)

**Blockers:**
- BioModels API blocked from this environment (HTTP 403); user must supply SBML manually
- Same workflow as Thattai (which user already accepted)

**Open architectural questions deferred (per user "power through" decision):**
- Future skill bundling refactor (Option C) — DEFERRED until working simulation exists; will be done in same repo, not separate project
</next_steps>