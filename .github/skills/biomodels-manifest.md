# biomodels-manifest skill

Generates a DRAFT parameter manifest YAML from a BioModels SBML file.
The manifest is the input contract for the `biology-curator` skill,
which then invokes `param-extractor` per entry.

## When to invoke

When the user wants to bulk-bootstrap parameter cards for a published
model that has an SBML representation in BioModels (e.g. Chassagnole
2002 = BIOMD0000000051).

Do NOT invoke when:
- The paper has no SBML in BioModels — hand-write the manifest instead.
- A polished manifest already exists — only re-run if the SBML changed.

## How to get the SBML (CRITICAL)

The BioModels web/API endpoints (`ebi.ac.uk/biomodels/...`) are commonly
WAF-blocked from cloud, CI, and CLI environments (HTTP 403). Try these
in order:

```bash
# 1. GitHub mirror (RECOMMENDED — no WAF, no auth):
git clone --depth 1 https://github.com/biomodels/<BIOMD_ID>.git
cp <BIOMD_ID>/<BIOMD_ID>/<BIOMD_ID>.xml .paper_cache/

# 2. EBI FTP:
wget https://ftp.ebi.ac.uk/biomodels/releases/<release>/<BIOMD_ID>.xml.gz

# 3. JWS Online (Stellenbosch / VU Amsterdam mirror):
# Browse https://jjj.bio.vu.nl/models/

# 4. Wayback Machine:
# https://web.archive.org/web/*/ebi.ac.uk/biomodels/<BIOMD_ID>*

# 5. Author / Zenodo / journal supplementary materials.
```

Always copy a clean reference into `.paper_cache/` and commit a
documentation note pointing at the source — never re-download to a
rolling location.

## Invocation

```
python tools/biomodels_manifest.py \
  --sbml-path .paper_cache/<BIOMD_ID>.xml \
  --model-slug <model-slug> \
  --output manifests/<model-slug>.draft.yaml
```

`--paper-doi`, `--biomodels-id`, `--organism` are optional and overridden
by SBML MIRIAM annotations when omitted (see *Auto-fill* below).

## Auto-fill from SBML annotations

The tool extracts these from `<model><annotation><rdf:RDF>` blocks:
- `bqmodel:is` → BioModels ID
- `bqmodel:isDescribedBy` → PubMed ID (DOI is rare here)
- `bqbiol:hasTaxon` → NCBI taxonomy ID → mapped to organism name via
  a small static table (E. coli, S. cerevisiae, human, mouse, rat,
  Drosophila, C. elegans, Arabidopsis, M. tuberculosis, M. genitalium)

Disable with `--no-auto-metadata` if the SBML annotations are wrong.
CLI flags always win over auto-fill.

## Outputs

A YAML manifest with:
- `paper:` block (header — DOI, biomodels_id, organism, condition, notes)
- `parameters:` list — one entry per global parameter, local kinetic
  parameter, and species initial (suppress species with `--no-species`)

Each entry carries `parameter_id`, `symbol` (defaults to SBML id),
`target_unit` (resolved from custom unitDefinitions), and the original
`sbml_value` for cross-checking.

## Hard constraints

- Never invents values; emits only what's literally in the SBML.
- Disambiguates colliding `parameter_id`s by appending the parent
  reaction id (so two `kcat_local` entries in different reactions don't
  collapse).
- Output is DRAFT — humans MUST prune, fix SBML-id-vs-paper-symbol
  mismatches, and add `gene_or_enzyme` annotations before handing to
  `biology-curator`.

## Hand-off

After human pruning:
```
python tools/curate_params.py --manifest manifests/<model>.yaml \
  --output-cards data/params/<model>.yaml \
  --output-dir data/curation/<model>/
```

## Shell exit-code gotcha

Exit codes (0 OK, 2 missing input, 3 download failed) are silently
masked by bash pipes and PowerShell-to-WSL invocations. See
`docs/architecture/shell-exit-codes.md` for safe patterns.

## Reference test

`tests/unit/test_manifest.py` exercises the full pipeline on a synthetic
SBML fixture mimicking BioModels structure (custom unit definitions,
local kineticLaw params, species initials, parameter_id collisions).
The Chassagnole 2002 SBML has been validated end-to-end as well: 160
entries (7 global + 135 local + 18 species, 5 unit definitions).
