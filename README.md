# OpenCell 🧬

**Open-source whole-cell computational simulation**

> *"A hallucinating agent and a biology noob walked into a cell..."*

## What is this?

OpenCell is an open-source, GPU-accelerated whole-cell simulation framework built in Python/JAX. We're starting with a toy cell (~50 genes) as a coupled-solver benchmark, then scaling to *Mycoplasma genitalium* (~525 genes).

## Status

🚧 **Pre-alpha** — Project scaffolding in progress. No simulation code yet.

## Quick Start

```bash
# Clone
git clone https://github.com/sdrona-ms/opencell.git
cd opencell

# Create virtual environment (Python 3.12 required)
py -3.12 -m venv .venv-opencell
.venv-opencell\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest
```

## Architecture

- **Language**: Python 3.12 + JAX + SciPy
- **Sub-models**: Modular ODE-based (metabolism, transcription, translation)
- **Coupling**: Operator splitting (Strang symmetric) with resource ledger
- **Validation**: Analytical micro-model gate, differential testing vs SciPy/PySCeS
- **Data**: Schema-validated parameters with DOI provenance

## Project Structure

```
opencell/
├── opencell/          # Main package
│   ├── core/          # IR, state, units, engine, guards, sentinels
│   ├── solvers/       # ODE (JAX + SciPy), stochastic (tau-leaping)
│   ├── models/        # Sub-models (metabolism, transcription, translation)
│   ├── data/          # Loaders, schemas, organism data
│   ├── orchestrator/  # AI agent router, expert panel, cost tracker
│   └── analysis/      # Sensitivity, phenotype, observation model
├── tests/             # Unit, integration, property, scientific, gate tests
├── docs/              # Biology specs, architecture docs, blog
├── decisions/         # Structured decision registry
└── notebooks/         # Jupyter tutorials
```

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Blog

Follow our journey: [docs/blog/](docs/blog/)

## Citation

If you use OpenCell in your research, please cite:

```bibtex
@software{opencell2026,
  title = {OpenCell: Open-Source Whole-Cell Simulation},
  author = {Drona, Srinivas},
  year = {2026},
  url = {https://github.com/sdrona-ms/opencell}
}
```
