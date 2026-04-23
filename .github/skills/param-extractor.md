# Parameter Extractor

## Role
Deterministically extract one biological parameter value from cached source artifacts (PDF text, BioModels SBML, supplementary tables). **Produce an auditable evidence set, not a best guess.**

## When to invoke
Any time a numeric parameter value is needed for a `ParameterCard`. Replaces the failure-prone pattern of "AI reads paper → reports value" that twice produced fabricated quotes and 2×–15× wrong values during the Thattai 2001 verification campaign.

## Hard constraints (non-negotiable)
1. **Never invent a value.** Every emitted value must trace to a verbatim character span in a SHA-256-hashed cached file.
2. **Never auto-promote.** This skill emits `status: DRAFT` only. Promotion to `REVIEWED`/`APPROVED` is a separate human step via `tools/review_param.py`.
3. **Never resolve ambiguity silently.** If multiple plausible values exist, surface them all with locators and rejection reasons. Exit non-zero. Do not pick.
4. **Never fill biological context by inference.** `organism`, `condition`, `compartment`, `gene_or_enzyme` must come from the caller (CLI args), not from text extraction.
5. **Cache provenance is mandatory.** Every candidate carries `source_path`, `source_sha256`, `extractor_version`.

## Protocol (strict order)

### Inputs
- `doi` — source paper DOI
- `symbol` — parameter symbol *as written in the paper* (e.g. `kR`, `k_R`, `γ_P`)
- `target_unit` — desired output unit (e.g. `min^-1`)
- `pdf_cache` — one or more cached text files (created by `tools/fetch_paper.py`)
- biological context (organism / condition / compartment / gene)

### Steps

1. **Hash every cache file** (`opencell.extraction.provenance.file_sha256`). Record path, sha256, extractor version on every emitted candidate.

2. **Generate symbol variants** to handle pypdf mangling (`opencell.extraction.pdf_grep.symbol_variants`):
   - strip underscores (`k_R` → `kR`)
   - transliterate Greek (`γ_P` → `g_P`, `gP`)

3. **Regex grep each cache file** for `<symbol> <eq> <value> [<unit>]`:
   - `<eq>` = `=`, `≈`, `~`, **or bare `5`** (pypdf mangles `=` to `5`)
   - `<value>` = number, optionally scientific
   - `<unit>` = optional alphanumeric token; demangled afterward (`s21` → `s^-1`, `min21` → `min^-1`, `h22` → `h^-2`)
   - Word-boundary anchors on both sides so `kR` does **not** match `kRi`, `kR1`, `RkR`.

4. **Tag each hit** with section type (`caption` | `body` | `refs` | `table` | `sbml`) using nearby keywords (`Fig.`, `Table`, `References`, `Bibliography`).

5. **Score each hit** (advisory only — never auto-resolves):
   | Component                             | Δscore |
   |---------------------------------------|--------|
   | Definitional language nearby (`fixed at`, `base case`, `we set`, …) | +0.3 |
   | Section is `caption`                  | +0.2 |
   | Section is `table`                    | +0.2 |
   | Section is `sbml` (BioModels)         | +0.4 |
   | Section is `refs`                     | −0.5 (virtual reject) |
   | Unit string non-empty                 | +0.1 |
   | Unit family compatible with target    | +0.3 |
   | Unit string exactly matches target    | +0.1 |

6. **Mark rejections** for hits in `refs` sections, hits with no unit (when `require_unit=True`), or hits below the survival threshold (default 0.3). **Keep them in the result for audit** — never silently drop.

7. **Cross-check with BioModels** (best-effort, network optional): query `/biomodels/search?query=doi:"<DOI>"`, download SBML for each match, parse `<parameter>` elements. BioModels is **corroboration**, never replacement; PDF text remains primary evidence.

8. **Convert units** with `pint`; record full transformation trail (`"0.01 s^-1 × 60 = 0.6 min^-1"`).

9. **Decide recommendation**:
   - Zero survivors → `NOT_FOUND` (exit 2)
   - All survivors agree on `raw_value` AND best score ≥ 0.6 → `RECOMMEND` (exit 0)
   - Otherwise → `AMBIGUOUS` (exit 1) — human must pick

10. **Emit DRAFT `ParameterCard`** when recommendation exists. Pack provenance into `selection_rationale` (existing schema field — do **not** invent new fields). Reviewer must compare to `original_quote` + `original_value` + `original_unit` + `transformation` (not the converted final value).

## Output
- Stdout report listing all candidates (surviving + rejected) with locators and context windows.
- Optional YAML append (`--output-yaml`): one DRAFT `ParameterCard` per successful run.
- Exit code: `0`/`1`/`2` per step 9.

## What this skill does NOT do
- Decide whether a value is biologically *appropriate* for the target model — that's `biology-validator`.
- Promote `DRAFT` → `REVIEWED` — that's `tools/review_param.py` + a human.
- Fetch papers — that's `tools/fetch_paper.py` (run beforehand to populate `.paper_cache/`).
- Extract from figures (image-only data). Use OCR + manual entry instead.

## Implementation
- Library: `opencell/extraction/`
- CLI: `tools/extract_param.py`
- Tests: `tests/unit/test_extraction.py`

## Hallucination failure modes this skill prevents
| Vector                                               | Defence                                                |
|------------------------------------------------------|--------------------------------------------------------|
| Inventing a quote                                    | Verbatim ±150-char context window from hashed cache    |
| Inventing a citation (e.g. fictional Table 1)        | `locator` field is line-number in actual cached text   |
| Picking the wrong hit when several exist             | Multi-survivor disagreement → AMBIGUOUS, no auto-pick |
| Confusing organism / condition                       | Context fields populated only from CLI args            |
| Stale cache silently re-used                         | SHA-256 of source file recorded with every candidate  |
| pypdf mangling (`s^-1` → `s21`, `=` → `5`)          | Demangling in `text_normalize.py`; tested on Thattai   |

## Reference test
`tests/unit/test_extraction.py` re-extracts Thattai 2001 `kR` against the cached PDF text and asserts `raw_value == 0.01` with `raw_unit_normalized == "s^-1"` and locator pointing to the figure-caption region. Recovers the same answer the human-in-the-loop campaign produced.
