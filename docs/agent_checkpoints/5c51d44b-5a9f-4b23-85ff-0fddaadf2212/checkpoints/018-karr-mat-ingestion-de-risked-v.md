<overview>
OpenCell — open-source whole-cell simulation in Python. User picked Option C (A4 follow-through: read Karr `.m` source for one state class) to de-risk M-phase ingestion before starting M1. Approach: fetch Karr WholeCell `.m` source files via raw URL, compare against the 3 `.mat` test fixtures we have, recover field-to-biology mapping, and decide if `.mat` ingestion is viable or if we need a different parameter source.
</overview>

<history>
1. **User picked Option C** ("we need to read the .mat files before we start the ingestion")
   - Added DB todo `a4f-karr-m-source` (in_progress)
   - Listed Karr `+state/*.m` files via GitHub tree API — 16 files, smallest are Time.m (2.1KB), Host.m (2.9KB), MetabolicReaction.m (3.0KB)
   - Downloaded 3 `.m` source files + matching Time.mat (1140B) and Host.mat (1074B) fixtures alongside MetabolicReaction.mat already present
   - Read all 3 `.m` files: declared `stateNames` differ — MetabolicReaction has `{growth, fluxs}` (2 fields), Time has `{values}` (1 field), Host has 4 boolean fields
   - Built `scripts/karr_a4f_compare.py` to verify whether `.mat` field structure matches declared state fields
   - **Result: ALL 3 fixtures have invariant `s0/s1/s2/arr` fields regardless of declared state field count.** This is a custom serializer, not direct state save.

2. **Investigated the serializer** (still mid-task at compaction)
   - Found `src_test/+edu/+stanford/+covert/+cell/+sim/CellStateFixture.m` (2822 bytes) — the test fixture builder
   - Read it: uses `save('-v7', filename, 'fixture')` then `editMatFileHeader(filename)` — explains why scipy.io sees top-level key as empty string
   - Confirmed `s0/s1/s2/arr` are properties of `SparseMat` / `CircularSparseMat` (custom MATLAB sparse matrix class, parent at 117KB)
   - **Pivot**: realized `.mat` test fixtures are STATE snapshots of saved MATLAB OBJECTS (not parameter tables). scipy can't reconstruct MATLAB class instances. Need to find Karr's actual PARAMETER source, not state fixtures.
   - Built `scripts/_find_karr_params.py` and discovered THREE huge wins:
     - `data/parameters.json` (5238 bytes) — JSON parameter file, human-readable
     - `data/knowledgeBase.mat` (3.95 MB) — the real knowledge base
     - `src/+edu/+stanford/+covert/+cell/+kb/Parameter.m` (4895 bytes) — Parameter class definition
   - Downloaded `parameters.json` and `Parameter.m` to `data/karr_fixtures/`
   - **Compaction triggered before reading parameters.json content or completing the A4F findings doc.**
</history>

<work_done>
Files created this turn:
- `E:\opencell\scripts\_list_karr_m.py` — list +state .m files
- `E:\opencell\scripts\karr_a4f_compare.py` — compare .mat structure across 3 classes
- `E:\opencell\scripts\_find_serializer.py` — find Karr serializer source
- `E:\opencell\scripts\_find_karr_params.py` — find parameter sources

Files downloaded to `E:\opencell\data\karr_fixtures\`:
- `Time.mat` (1140B), `Host.mat` (1074B) — additional state fixtures
- `parameters.json` (5238B) — **NOT YET READ**, but the breakthrough finding
- `m_source/MetabolicReaction.m` (2966B), `Time.m` (2157B), `Host.m` (2916B) — state class definitions
- `m_source/CellStateFixture.m` (2822B) — explains the .mat opacity (uses save+editMatFileHeader)
- `m_source/CircularSparseMat.m` (8653B) — sparse matrix class (parent SparseMat is 117KB, not downloaded)
- `m_source/Parameter.m` (4895B) — **NOT YET READ**, but useful for parameter schema

Artifacts:
- `E:\opencell\artifacts\karr_a4f_comparison.json` — full structure dump confirming s0/s1/s2/arr invariance

DB state:
- Added `a4f-karr-m-source` (in_progress) — NOT YET marked done
- Phase 5 todos still pending: m0a-persist-lsoda, m1-m7
- Counts: 16 pending, 95 done, 48 blocked (159 total)
</work_done>

<technical_details>
**The A4F breakthrough**: Karr 2012's `.mat` test fixtures are MATLAB OBJECT serializations (CellState class instances saved via `save('-v7', filename, 'fixture')` then with rewritten header via `editMatFileHeader`). scipy.io can read the raw struct shell but cannot reconstruct MATLAB class instances. The `s0/s1/s2/arr` fields seen by scipy are SparseMat object properties, NOT the declared state fields from the .m source.

**Therefore**: `.mat` STATE fixtures are not the right ingestion path for parameters. They are state snapshots of running simulations.

**The parameter path forward**: Karr stores parameters in:
1. `data/parameters.json` (5KB JSON) — likely human-readable config overrides
2. `data/knowledgeBase.mat` (4MB) — the real knowledge base (probably also a serialized object, but possibly extractable)
3. `data/runSingleGeneDeletionSimulations.xml` (245KB) — XML config
4. Hardcoded constants in `src/+edu/+stanford/+covert/+cell/+kb/*.m` — the kb classes
5. `data/singleGeneDeletions.xls` — gene deletion experiment data

**Karr repo top-level data dirs by size**:
- `data/` 21.2 MB / 22 files
- `lib/` 34.1 MB / 492 files
- `src/` 4.0 MB / 210 files
- `src_test/` 60.3 MB / 169 files

**Quirks discovered this turn**:
- PowerShell here-string with `$cmd = '...'` and embedded Python triple-nested quotes is fragile. Better to write Python to a file and `python scripts/x.py`.
- GitHub `/git/trees/master?recursive=1` returns full tree with sizes — works without auth.
- GitHub code search API (`/search/code`) returns 401 without auth even for public repos.
- `urllib.parse.quote(repo_path)` correctly encodes `+` in MATLAB package paths (`+edu/+stanford/...`) for raw.githubusercontent.com URLs.
- `chr(47)` = `/` workaround used in PowerShell-embedded Python to avoid escape hell with paths.

**Open questions / not yet investigated**:
- What does `parameters.json` actually contain? (Downloaded but not read — top priority next.)
- Does `Parameter.m` define a schema we can adopt for the A3 store?
- Can `knowledgeBase.mat` be parsed at all, or is it also a serialized object?
- Does Octave (free MATLAB-compatible) successfully load these fixtures? Could be a viable extraction path.
</technical_details>

<important_files>
- `E:\opencell\data\karr_fixtures\parameters.json`
   - **THE next thing to read** — JSON parameter file from Karr's data dir
   - Downloaded but contents not yet inspected
   - 5238 bytes
- `E:\opencell\data\karr_fixtures\m_source\Parameter.m`
   - Karr's Parameter class definition — useful for A3 store schema design
   - Downloaded but contents not yet inspected
   - 4895 bytes
- `E:\opencell\data\karr_fixtures\m_source\CellStateFixture.m`
   - **Explains the .mat opacity** — lines 24-27 show `save('-v7', ..., 'fixture')` + header rewrite
   - This is the definitive evidence that .mat fixtures are MATLAB object dumps, not state tables
- `E:\opencell\scripts\karr_a4f_compare.py`
   - Working comparison tool that confirmed s0/s1/s2/arr invariance
   - Verdict logic at end correctly outputs the finding
- `E:\opencell\artifacts\karr_a4f_comparison.json`
   - Quantitative evidence for the A4F findings doc
- `E:\opencell\docs\phase4\A4_karr_extraction_spike.md` (existing from previous turn)
   - Original A4 spike doc — A4F findings should EXTEND this, not replace it
- `E:\opencell\opencell\provenance\store.py` (existing)
   - A3 store; whatever schema we discover from Parameter.m + parameters.json should be evaluated against this
- `E:\opencell\plan.md` (existing)
   - Will need a Phase 5 narrative update once A4F is complete to reflect parameters.json as the ingestion path
- `E:\opencell\SESSION_CONTEXT.md` (existing)
   - Should get a new entry when A4F closes
</important_files>

<next_steps>
**Immediate (next 1-2 turns):**
1. **Read `data/karr_fixtures/parameters.json`** — view the file. This is the breakthrough. Confirm it's the parameter source we want.
2. **Read `data/karr_fixtures/m_source/Parameter.m`** — see what schema Karr uses for parameter records (compare to our A3 store schema).
3. **Try parsing `data/knowledgeBase.mat`** with scipy.io — is it also an opaque object dump, or is it readable? If readable, it's the deepest source.
4. **Optionally try Octave** in WSL (`apt install octave`) to actually load one CellState fixture and dump its real properties — this would let us confirm what's in `arr` if we ever need state fixtures (we probably don't for parameter ingestion).

**Write up the A4F findings doc:**
- Path: `E:\opencell\docs\phase4\A4F_karr_m_source_followthrough.md`
- Headlines:
  - `.mat` fixtures are MATLAB object dumps, not parameter tables
  - The actual parameter path is `data/parameters.json` + `data/knowledgeBase.mat` + hardcoded constants in `src/+kb/*.m`
  - M-phase ingestion plan: read `parameters.json` first (JSON, easy), use `Parameter.m` schema as our v0.2 A3 store schema reference, defer `knowledgeBase.mat` until we hit a parameter not in the JSON
- Cite the CellStateFixture.m save+header-rewrite as definitive evidence
- Include quantitative comparison from `artifacts/karr_a4f_comparison.json`

**Then:**
- Mark `a4f-karr-m-source` done in DB
- Update `plan.md` Phase 5 narrative with the parameters.json ingestion path
- Append a new entry to `SESSION_CONTEXT.md` for the A4F checkpoint
- Sync plan.md to session-state mirror
- Call `task_complete` with summary

**Then user can decide:** Option B (M0-A persist-LSODA) or Option A (M1 central carbon) with the ingestion path now de-risked.
</next_steps>