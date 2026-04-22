# Benchmark Charter: What Constitutes Failure

## Purpose
Define what phenotype predictions, if wrong, would **reject** the model.
This prevents optimizing toward easiest-to-match criteria.

## Rejection Criteria (non-negotiable)

### Hard Failures (instant rejection)
1. **Negative concentrations** — any species count < 0 at any time step
2. **Growth without nutrients** — cell mass increases in empty medium
3. **Energy from nothing** — ATP production exceeding thermodynamic limits
4. **Unfalsifiable model** — cannot be rejected by ANY experimental observation

### Soft Failures (trigger investigation)
5. **Mass not conserved** — total mass residual > 1e-6 relative tolerance
6. **Doubling time off by >2x** — outside ±30% of measured value for M. genitalium (~12h)
7. **Gene essentiality < 60%** — below minimum acceptable threshold
8. **>50% parameters unidentifiable** — model "passes" via compensating errors

## Toy Cell Benchmark Targets (v1.0)
The toy cell is a **coupled-solver benchmark**, not a biological cell.
Success means:
- Coupled metabolism + transcription + translation runs stably
- Mass/energy conserved (property-based tests pass)
- Solver coupling demonstrated (FBA+ODE, stochastic+deterministic)
- Reproducible (deterministic golden-run tests pass)
- Checkpoint/restart works

## M. genitalium Targets (v2.0)
- Gene essentiality: ≥75% accuracy (Karr 2012 achieved 79%)
- Growth rate: within ±30% of measured doubling time
- At least 3 observation model assays functional (OD600, qPCR, proteomics)

## What We Do NOT Claim
- We do not claim to simulate every known M. genitalium behavior
- We do not claim quantitative accuracy for all parameters
- We acknowledge parameter estimation uncertainty explicitly
