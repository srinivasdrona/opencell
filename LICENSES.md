# OpenCell upstream license clearance (Phase 4 / A2)

This file records license status for every package we depend on or plan
to ingest. Updated on every dependency add, every Phase-A/M phase gate.

## Critical-path (Phase 4 / 5 / 6a — must be clean)

| Package | Version | License | Source | Status | Notes |
|---|---|---|---|---|---|
| `vivarium-core` | 1.6.5 | Apache 2.0 | github.com/vivarium-collective/vivarium-core, PyPI | ✅ CLEAR | Permissive; commercial OK; A1 spike installed and used. |
| `libroadrunner` | (pinned) | Apache 2.0 | github.com/sys-bio/roadrunner | ✅ CLEAR | Verified on PyPI metadata; also dual-licensed with LGPL components — using Apache path. |
| `numpy` | (pinned) | BSD-3 | numpy.org | ✅ CLEAR | Standard. |
| `scipy` | (pinned) | BSD-3 | scipy.org | ✅ CLEAR | Standard. |
| `pint` | (pinned) | BSD-3 | github.com/hgrecco/pint | ✅ CLEAR | Standard. |
| `pypdf` | (pinned) | BSD-3 | github.com/py-pdf/pypdf | ✅ CLEAR | Standard. |
| `matplotlib` | (pinned) | PSF-based BSD-style | matplotlib.org | ✅ CLEAR | Standard. |
| `pytest` | (pinned) | MIT | pytest.org | ✅ CLEAR | Test only. |

## Karr 2012 / Mycoplasma genitalium model artefacts (Phase 4 / A4 → Phase 5)

| Artefact | License | Source | Status | Notes |
|---|---|---|---|---|
| `CovertLab/WholeCell` (MATLAB code) | MIT | github.com/CovertLab/WholeCell | ✅ CLEAR for read/port | Permissive; allows derivative Python port with attribution. |
| `CovertLab/WholeCellKB` (Django/Python KB) | MIT | github.com/CovertLab/WholeCellKB | ✅ CLEAR | Preferred Python-friendly access path for parameter ingestion. |
| `iPS189` (Suthers 2009 SBML model) | (BiGG redistribution terms) | bigg.ucsd.edu/models/iPS189 | ⏸ TO VERIFY before A4 | Structural scaffold; FBA only, no kinetics. Verify BiGG redistribution clause before bundling. |

## Deferred (NOT critical path; verified at the gate they're needed)

| Artefact | Status | Gate |
|---|---|---|
| `wcEcoli` (Covert E. coli WCM) | ⏸ defer | Phase 6 / E1 — license listed as "Other" on GitHub; verify before ingestion. |
| `vEcoli` (vivarium-collective port) | ⏸ defer | Phase 6 / E1. |
| `JCVI-syn3A` / Lattice Microbes | ⏸ defer | Phase 6 / Z (likely never; runtime-coupled, license unclear). |
| `COBRApy` | ⛔ AVOID for kinetic engine | GPL-2.0 copyleft — would taint our permissive distribution if linked into the kinetic core. Use only as an *external* tool that produces SBML/JSON we ingest. |

## Our license

OpenCell itself is intended to ship under **Apache 2.0** to match
vivarium-core and to keep the door open for downstream commercial use
(consistent with our reusable-modules goal). Final SPDX header
roll-out is a separate task before first public release.

## Process

* On every new dependency: add a row above with version, SPDX, and
  source URL. PR cannot be merged without this row.
* On every model-artefact ingestion: record license check in the
  provenance store (A3) as part of the `source` record on each
  parameter card.
* If a critical-path dependency changes license (e.g. relicense to
  GPL), it is treated as a P0 incident: pin the last-permissive
  version and triage replacement.
