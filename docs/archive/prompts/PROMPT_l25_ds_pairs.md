# Task: Scaffold + run 43 L2.5 deterministic-stochastic pair tests

Read `./SESSION_CONTEXT.md` for project rules. Pay attention to Hard Rule 17
(naming discipline).

## ⚠️ Python interpreter — MANDATORY
Use `bin\oc-pytest.cmd` and `bin\oc-py.cmd`. Do NOT run python directly.

## STATUS file
Write `docs/phase_f/status/STATUS_l25_ds_pairs.md` as you go.
Final message: "done, see STATUS".

## Commit cadence
Commit each beat with prefix `l25-ds-pair:`. Beats:
1. Scaffold helper that generates DS pair tests programmatically
2. Generate all 43 DS pair test files
3. Run all 43; commit results table
4. (Conditional) Investigate any failures, document in STATUS

## Goal

Scaffold and run L2.5 tests for all 43 deterministic-stochastic pairs.
Use the per-side oracle policy: deterministic process uses bit-identity
(rtol=0, atol=0) against L2.1 trace; stochastic process uses the
standard distributional oracle.

The harness fix is already in main (commits `f55c34a`, `c37fdc7` — Bug H5
hint policy alignment + Bug H6 shared-WID overlay preservation). These
new tests verify the harness works for the larger DS surface.

## The 43 DS pairs

Load from `data/schemas/l25_pair_list.toml`:
- Filter to `l25_honest_required == true`
- Filter to `pair_oracle_complexity == "deterministic_stochastic"`
- Should yield exactly 43 pairs

The 6 deterministic processes (one side of every DS pair):
- ChromosomeCondensation, ChromosomeSegregation, HostInteraction,
  ProteinActivation, TerminalOrganelleAssembly, TranscriptionalRegulation

## Approach

### Option A: One test file per pair (43 files)
- Pros: explicit, easy to find failing pair, parallelizable in pytest
- Cons: lots of boilerplate, harder to maintain

### Option B: One parameterized test file with 43 cases
- Pros: less boilerplate, central place for shared logic
- Cons: harder to find individual failures by filename, harder to fix one
  pair without re-running all

**Pick Option B.** Create one file
`tests/vivarium/test_l25_deterministic_stochastic_pairs.py` with
`@pytest.mark.parametrize` over all 43 pairs loaded from
`l25_pair_list.toml`.

Reference patterns:
- `tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py`
  (deterministic-deterministic, already passing)
- `tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py`
  (deterministic-deterministic, already passing)
- `tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py`
  (stochastic-stochastic, the L2.5 first pair)

All three use `run_integrated_replay_v2` with `disable_trace_hints=True`
and the harness handles per-side oracle selection via the catalog (no
need to specify oracle type in the test).

### Implementation outline

```python
import pytest
import tomllib
from pathlib import Path
from l2_2_replay_common_v2 import run_integrated_replay_v2

_PAIR_LIST_PATH = Path(__file__).resolve().parents[2] / "data/schemas/l25_pair_list.toml"

def _load_ds_pairs():
    data = tomllib.loads(_PAIR_LIST_PATH.read_text())
    return [
        (p["process_a"], p["process_b"])
        for p in data["pairs"]
        if p.get("l25_honest_required")
        and p.get("pair_oracle_complexity") == "deterministic_stochastic"
    ]

DS_PAIRS = _load_ds_pairs()

@pytest.mark.parametrize("rng_seed", [0], ids=["seed_0"])
@pytest.mark.parametrize("process_a,process_b", DS_PAIRS, ids=lambda p: f"{p}")
def test_l25_deterministic_stochastic_pair(process_a, process_b, rng_seed):
    """L2.5 honest-mode test for deterministic-stochastic pair.
    
    Per-side oracle: deterministic side uses bit-identity (rtol=0, atol=0),
    stochastic side uses distributional oracle.
    """
    run_integrated_replay_v2(
        under_test_processes=[process_a, process_b],
        rng_seed=rng_seed,
        disable_trace_hints=True,
    )
```

If the existing DD tests need special `oracle_type_by_process` overrides
(e.g., for processes the catalog hasn't classified yet), apply the
minimum needed for DS pairs.

### Beat 3: Run all 43 tests

```powershell
bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v --tb=no
```

Capture full output. Categorize:
- PASSED count
- FAILED count (with CAUSE_X breakdown if possible)
- ERROR count (test infrastructure issues)

Write the result table to STATUS doc, format like:

```
| # | Pair | Result | Cause/Notes |
|---|---|---|---|
| 1 | ChromosomeCondensation + Metabolism | FAILED | CAUSE_2_ORACLE_INJECTION |
| 2 | ChromosomeCondensation + DNASupercoiling | PASSED | — |
| ... | | | |
```

### Beat 4 (conditional, only if there are failures)

DO NOT fix individual process bugs in this turn. Document failures and
group by failure mode for operator review. The operator will decide
whether to:
- Investigate a specific pair (next-turn task)
- Fix a harness issue (operator approval needed for harness changes)
- Accept some failures as known limitations

## Files you may read (read-set)

- `data/schemas/l25_pair_list.toml` (source of pair list)
- `tests/vivarium/l2_2_replay_common_v2.py` (harness)
- `tests/vivarium/l2_replay_common.py` (shared helpers)
- `tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py`
- `tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py`
- `tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py`
- `docs/phase_f/L2_5_ACCEPTANCE_RUBRIC.md`
- `docs/phase_f/L2_5_PAIR_MATRIX.md`
- `docs/phase_f/status/STATUS_cause_4_sweep.md`

## Files you may write (write-set)

- `tests/vivarium/test_l25_deterministic_stochastic_pairs.py` (NEW)
- `docs/phase_f/status/STATUS_l25_ds_pairs.md`

DO NOT modify:
- `l2_2_replay_common_v2.py` (harness — operator approval required)
- Process implementations
- TOML schemas
- PROCESS_CATALOG.yaml
- Existing tests

## Acceptance criteria

1. New parametrized test file created with all 43 DS pair cases
2. Test file runs to completion (every case has a PASS/FAIL/SKIP verdict,
   no errors that prevent the runner from completing)
3. STATUS doc has results table sorted: failures first, then passes
4. Summary: X passed / Y failed / Z skipped out of 43
5. If failures: grouped by failure mode (CAUSE_X) with counts
6. At least 3 commits with `l25-ds-pair:` prefix

## Hard rules

- Do NOT modify the harness
- Do NOT modify process files to make tests pass
- The full run might take 30-60 minutes (43 pairs × ~30s each). If runtime
  exceeds 90 minutes, abort and document in STATUS
- Use a single-seed run (seed_0 only) for this verification pass
- If a specific pair test crashes (uncaught exception preventing other
  tests from running), use `pytest --continue-on-collection-errors` or
  similar; document the crashed pair separately
- If you exceed 100k tokens before Beat 3 completes, stop and write STATUS
