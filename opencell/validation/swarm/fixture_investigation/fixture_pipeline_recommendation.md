# Fixture Pipeline Recommendation

## What’s broken

The replay harness expects tick-indexed channels (`state_before*`, `state_after*`, `input*`, `output*`) plus discoverable `n_ticks` metadata (`opencell/validation/replay.py:120-145`, `:172-207`).  
Current per-process fixtures are flattened snapshots of MCOS fixture objects:
- `_flat.mat` is `data.fixture` (single object) (`scripts/matlab/extract_per_process_fixtures.m:33-34`, `:107-109`)
- companion `.npz/.json` contain many static arrays but no replay channel keys and no `n_ticks` (`scripts/extract_per_process_fixtures.py:271-280`, `:299-326`)
- loader therefore resolves `n_ticks=1`, `inputs=0`, `outputs=0` (replay smoke already xfails on this) (`opencell/validation/replay.py:145`, `tests/integration/test_replay_smoke.py:46-50`).

This is primarily a **fixture-content/schema problem**.

## Confidence level

**MEDIUM-HIGH** that the right rebuild pattern is “new trace extraction + conversion”.

- High confidence on root cause: snapshot fixtures and MCOS packaging are directly evidenced in source and flat probes.
- Medium confidence on full migration details: we still need to finalize a canonical replay fixture schema for all 28 processes and validate process-specific key mappings.

## Estimated rebuild scope

- **A) Small (~50 LOC, 1-2 days): extraction script-only fix**
  - Not sufficient for replay fidelity. There is no hidden tick table already flowing through current extractor path.
- **B) Medium (~200 LOC, ~1 week): re-run Karr simulations + new extraction + light harness alignment**
  - Most realistic. Existing MATLAB trace tooling already captures per-tick `states_before` / `states_after` (`scripts/matlab/extract_per_process_traces.m:4-6`, `:15-20`, `:98-133`).
- **C) Large (~500+ LOC, weeks): full fixture format redesign**
  - Only needed if we want a brand-new versioned spec spanning all modules and legacy back-compat.

## Recommended path

Choose **Option B**.

1. Populate `data/m1_sources/karr_native/per_process_traces/` using existing MATLAB trace extraction (28 processes, deterministic seed) (`scripts/matlab/extract_per_process_traces.m:24-25`, `:86-98`, `:124-133`).
2. Add a Python converter that emits replay-ready companion fixtures with:
   - explicit `manifest.n_ticks`
   - namespaced `state_before/...` and `states_after/...` arrays
   - consistent tick-major axis.
3. Keep `opencell/validation/replay.py` mostly unchanged; only add minor normalization if any process-specific naming inconsistencies appear.
4. Add replay integration tests for representative process classes before scaling to all 28.

Rationale:
- Reuses existing trace-generation work instead of reverse-engineering MCOS internals.
- Aligns directly with current replay harness contract.
- Enables replay-fidelity and t=0/t>0 parity without a full format rewrite.

## Does this block Track-A?

For immediate Track-A fixes (`A1`/`A2`/`A3`/`A4`/`A5`): **No**.

- It does block future replay-fidelity auditing and robust per-tick parity gates.
- It does not block immediate bug-fix and chassis iteration tasks that rely on existing snapshot fixtures and non-replay validations.
