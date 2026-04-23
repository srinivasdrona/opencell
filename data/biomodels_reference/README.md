# BioModels Reference Copies

This directory holds permanent reference copies of SBML files used by
opencell parameter-extraction campaigns. These are *not* the working
caches (those live in `.paper_cache/`, which is gitignored).

| File | Source | Acquired |
|---|---|---|
| `BIOMD0000000051_chassagnole2002.xml` | `git clone https://github.com/biomodels/BIOMD0000000051.git` | 2026-04-23 |
| `BIOMD0000000035_vilar2002.xml` | `git clone https://github.com/biomodels/BIOMD0000000035.git` | 2026-04-23 |

## Why a separate directory?

`.paper_cache/` is gitignored and treated as a scratch area. These
reference copies are committed so:

1. The SHA-256 fingerprints recorded by the param-extractor are
   reproducible across machines.
2. Future agents and humans can see exactly which version of an SBML
   each parameter was extracted from.
3. We have a fallback if BioModels and its mirrors all go offline.

## How to get more

The official BioModels API is commonly WAF-blocked (HTTP 403). Use the
GitHub mirror:

```bash
git clone --depth 1 https://github.com/biomodels/<BIOMD_ID>.git
cp <BIOMD_ID>/<BIOMD_ID>/<BIOMD_ID>.xml \
   data/biomodels_reference/<BIOMD_ID>_<slug>.xml
```

See `.github/skills/biomodels-manifest.md` for the full discussion of
alternative sources (FTP, JWS Online, Wayback).
