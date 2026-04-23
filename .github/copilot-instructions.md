# OpenCell — Copilot Instructions

## Project Context
OpenCell is an open-source whole-cell simulation in Python/JAX.
This file defines agent behavior for all AI-assisted work on this project.

## Skill Profiles
Load the appropriate skill profile from `.github/skills/` based on the task type.
See plan.md "Agent Skill Profiles" section for full definitions.

## Mandatory Rules

### No Naked Biology Numbers
Every biological constant in model code MUST reference a parameter ID from the data layer.
Hardcoded literals allowed ONLY for: 0, 1, tolerances, array shapes.

### Unit Discipline
All values entering the IR must pass through pint unit validation.
Sub-models must declare their reference frame (per-cell, per-volume, per-gDW).

### Evidence Provenance
Every nontrivial biological claim must have:
- DOI citation
- Quoted evidence snippet with page/figure/table location
- Experimental conditions (temperature, pH, strain, medium)
- Uncertainty distribution

### Temperature Policy
- Temperature 0: code generation, parameter extraction, data formatting
- Temperature 0.3-0.5: literature search, hypothesis generation
- Never above 0.5 for any task

### Decision Registry
All biology/model decisions go in `decisions/` as structured YAML.
CI enforces: changing behavior tied to a decision must reference or supersede it.

### PR Checklist (Biology/Model PRs)
1. Which assumptions changed?
2. Which parameters changed?
3. Which modules/species affected?
4. Which invariants re-run?
5. Did estimated parameter count increase?

## Credibility Policy
- Mark all estimates as VERIFIED or UNVERIFIED
- Say "I don't know" rather than fabricate
- Benchmark before claiming performance numbers
- Cite sources for all biological facts
