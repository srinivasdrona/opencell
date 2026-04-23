# DEC-002: Identifier Crosswalk Deferred to Phase 2

**Status:** Active
**Date:** 2026-04-23
**Decision:** Do not build the KEGG↔BioCyc↔UniProt↔GenBank identifier crosswalk in Phase 0/1. Defer to Phase 2 when real M. genitalium parameters are needed.

## Context
An external reviewer flagged identifier reconciliation as a "data engineering sub-project" that should be Phase 0, arguing that databases disagree not just on IDs but on reaction definitions (e.g., glycolysis as 10-step vs 12-step).

## Why We Agree It's Important
- The reviewer is correct that BRENDA/KEGG/BioCyc disagree on reaction topology, not just identifiers
- This will be a multi-week effort when we build real sub-models
- Getting it wrong means sub-models "talk past each other" with mismatched species

## Why We Defer (Not Ignore)
- **Toy cell uses synthetic IDs.** We define our own species, reactions, and parameters. No crosswalk needed.
- **We don't know which reactions yet.** Until we pick M. genitalium's metabolic network, we don't know which identifiers to reconcile.
- **Premature effort.** Building crosswalk tooling for reactions we haven't selected wastes time.

## What We Will Do in Phase 2
- Build crosswalk as a versioned data artifact (content-hashed via `data/versioning.py`)
- Use the Data Engineer skill profile for systematic extraction
- Start with Karr 2012's 1,900 parameters as the primary source (single-source, no reconciliation needed)
- Add BRENDA/BioCyc only where Karr data is missing or suspect

## Revisit Triggers
- Toy cell needs real biological parameters from multiple databases
- Phase 2 kickoff — crosswalk becomes a prerequisite task
