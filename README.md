# OpenCell 🧬

**Open-source whole-cell simulation framework, built on
[Vivarium-core](https://vivarium-core.readthedocs.io/). Pure Python
(NumPy/SciPy), CPU-native. *Mycoplasma genitalium* reference, with
explicit L-ladder validation, anti-laundering detection, and intervention
API. Designed for ML method validation, causal discovery benchmarking,
and reproducible Bio-AI research.**

> *"A hallucinating agent and a biology noob walked into a cell..."*

## What is this?

OpenCell is a modern, modular, reproducible port of the
[Karr 2012 *M. genitalium* whole-cell model](https://www.cell.com/cell/fulltext/S0092-8674(12)00776-3)
from MATLAB to Python, built on the Vivarium-core simulation framework.

**Design goals:**

1. **Validated against Karr's MATLAB** — every Python process is checked
   for bit-identity at L2.1 and distributional fidelity at L2.2 against
   the original MATLAB oracle traces.
2. **Composable** — 28 biological processes + allocator, each a separate
   `Process` class with declared ports. Drop in a DNN surrogate, an ODE
   model, or a different algorithm without touching neighbors.
3. **Reproducible** — every result ties to a `reference_data_manifest`
   capturing MATLAB commit, fixture date, RNG seed, dependency lockfile,
   and hardware fingerprint.
4. **Tested for oracle leakage** — runtime `PRIMARY_CHANNEL_ORACLE_LAUNDERING`
   detector catches benchmarks that secretly read from the ground-truth
   trace instead of computing independently.

## Status (Day 32, 2026-06-18)

**L-ladder validation progress:**

| Gate | Definition | Status |
|---|---|---|
| L1 | "Did it fire?" | ✅ 28/28 processes firing |
| L2.0 | Schema audit | ✅ Complete |
| L2.1 | Bit-identity per process (σ=0) | ✅ 28/28 green |
| L2.2 | Distributional fidelity per process (ensemble) | ✅ 22/22 in-scope green |
| L2.5 | Shared-pool composition (k=2..4 processes) | 🚧 IN PROGRESS — first pair green |
| L3 | Direct coupling (producer→consumer) | ⏳ Not started |
| L4 | Submodule (cluster vs oracle) | ⏳ Not started |
| L5 | Chassis (whole-cell phenotype) | ⏳ Not started |

**L2.5 scope:** 256 honest-required pairs (211 stochastic-stochastic, 43
deterministic-stochastic, 2 deterministic-deterministic) — see
`docs/phase_f/L2_5_PAIR_MATRIX.md`.

## Architecture

- **Engine**: [Vivarium-core](https://github.com/vivarium-collective/vivarium-core)
  (modular simulation framework with declared ports, atomic delta merges,
  multi-timescale support via per-process timesteps)
- **Language**: Python 3.12, NumPy, SciPy (no JAX, no GPU dependencies)
- **State**: schema-driven via per-process TOMLs (`data/schemas/per_process/*.toml`)
- **Processes**: 28 biological + 1 allocator, each a separate
  `vivarium.core.Process` subclass with declared `ports_schema` and
  `next_update(timestep, states) → delta_dict`
- **Validation**: L1-L5 ladder with per-tick fidelity assertion against
  MATLAB oracle traces; runtime anti-laundering detector

## Quick Start

```powershell
# Clone
git clone https://github.com/srinivasdrona/opencell.git
cd opencell

# WSL venv setup (required — pure Windows Python lacks vivarium-core deps)
wsl bash -lc "cd /mnt/e/opencell && python3.12 -m venv .venv-wsl && \
              source .venv-wsl/bin/activate && pip install -e '.[dev]'"

# Run tests (via WSL wrapper)
bin\oc-pytest tests/
```

## Repository structure

```
opencell/
├── opencell/                  # Main package
│   ├── vivarium/              # 28 Karr process implementations (karr_*.py)
│   ├── state/                 # Chromosome sparse-triple store
│   ├── m3/                    # M3 v3 mechanism-based modules
│   ├── analysis/              # Phenotype analysis
│   └── m_gen_constants.py     # Biology-specific constants (centralized)
├── tests/                     # L1-L5 validation tests
│   └── vivarium/              # Per-process L2.1 replay + L2.5 composition
├── data/
│   ├── karr_fixtures/         # MATLAB-derived runtime fixtures (*_flat.mat)
│   ├── m1_sources/            # Karr 2012 MATLAB source + extracted traces
│   └── schemas/per_process/   # Per-process TOML schemas (state_groups, observables)
├── docs/
│   ├── phase_f/               # L2.x validation specs + status
│   ├── specs/                 # Architectural specs (INTERVENTION_API, POST_L5_ROADMAP, etc.)
│   ├── karr_extracts/         # MATLAB docstring extracts
│   └── blog/                  # Dev log series
├── scripts/                   # Extraction + derivation tooling
└── decisions/                 # Architecture Decision Records
```

## Use cases

### Today (pre-L5)

This codebase is most useful right now if you want to:

- Study how a 28-process composable simulator is wired with Vivarium
- Use the L-ladder validation methodology in your own simulation projects
- Use the anti-laundering detector pattern for ML benchmark integrity
- Watch a real port-from-MATLAB project navigate trade-offs honestly

### Post-L5 roadmap

See `docs/specs/POST_L5_ROADMAP.md` for the full plan:

- Reproducible WCM tool (the primary deliverable)
- Bio-AI Hello World benchmark
- OpenAI Gym environment for cellular RL
- Causal discovery benchmark
- Synthetic data factory for surrogate model validation
- Educational / tutorial materials
- Mutagenesis study design

The roadmap explicitly rejects: drug discovery, direct human disease
modeling, GPU-accelerated screens, JAX-based differentiable bio. See
the roadmap doc for why and what to point users to instead.

## Documentation

- **Plan**: `plan.md` — operational handoff, current status
- **L-ladder**: `plan.md` § L-ladder block
- **Process status**: `docs/phase_e/PROCESS_STATUS_ALL_29.md` — per-process L1-L5 tracker
- **L2.5 scope**: `docs/phase_f/L2_5_PAIR_MATRIX.md` — 256 pair test matrix
- **Post-L5 roadmap**: `docs/specs/POST_L5_ROADMAP.md`
- **Architectural specs**: `docs/specs/INTERVENTION_API.md`, `DATA_EMIT_SCHEMA.yaml`, `REFERENCE_DATA_MANIFEST.yaml`, `POST_L5_REFACTOR_PLAN.md`
- **Dev log blog**: `docs/blog/`

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Citation

A formal citation will be available after the biology validation paper
ships (post-L5). Until then, if you reference this work, please link to
the repo and commit:

```bibtex
@software{opencell2026,
  title = {OpenCell: Open-Source Whole-Cell Simulation},
  author = {Drona, Srinivas},
  year = {2026},
  url = {https://github.com/srinivasdrona/opencell}
}
```

## Acknowledgments

This work is a faithful port of the Karr 2012 *M. genitalium*
whole-cell model:

> Karr JR, Sanghvi JC, Macklin DN, Gutschow MV, Jacobs JM, Bolival B Jr,
> Assad-Garcia N, Glass JI, Covert MW. "A whole-cell computational
> model predicts phenotype from genotype." *Cell* 150(2):389-401 (2012).
> DOI: [10.1016/j.cell.2012.05.044](https://doi.org/10.1016/j.cell.2012.05.044)

Built on [Vivarium-core](https://github.com/vivarium-collective/vivarium-core)
by the Vivarium Collective.
