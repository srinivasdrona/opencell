# Contributing to OpenCell

Thank you for your interest in contributing! OpenCell is an open-source whole-cell simulation project.

## Getting Started

1. Fork the repository
2. Create a Python 3.12 virtual environment: `py -3.12 -m venv .venv-opencell`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Run tests: `pytest`
5. Install pre-commit hooks: `pre-commit install`

## PR Requirements

Every PR must include:

- [ ] Tests for new functionality
- [ ] All existing tests pass (`pytest`)
- [ ] Linting passes (`ruff check .`)
- [ ] Type checking passes (`mypy opencell/`)
- [ ] **Assumption delta checklist** (for biology/model PRs):
  - Which assumptions changed?
  - Which parameters changed?
  - Which modules/species affected?
  - Which invariants re-run?
  - Did estimated parameter count increase?

## Biology PRs

All biological parameters must have:
- Value with unit (pint-validated)
- Source DOI
- Uncertainty distribution
- Experimental conditions (temperature, pH, strain, growth medium)

**No naked biology numbers** — every constant must reference a parameter ID.

## Code Style

- Follow ruff/black formatting (enforced by pre-commit)
- Type annotations required (mypy strict mode)
- Line length: 100 characters

## License

By contributing, you agree that your contributions will be licensed under Apache 2.0.
