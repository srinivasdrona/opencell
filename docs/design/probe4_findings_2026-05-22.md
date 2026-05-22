# Probe 4 Findings (2026-05-22): Vivarium `set` + `accumulate` on the same leaf

## Scope

Empirical probe of one-tick merge semantics when multiple Processes write to
the same state leaf (`protein.counts.X`) with mixed updater declarations.

- Initial value: `protein.counts.X = 100`
- Vivarium version: `vivarium-core==1.6.5` (via `importlib.metadata.version`)
- Test file: `tests/probes/test_probe4_set_accumulate_merge.py`

## Observed behavior (empirical)

1. Mixed `set` + `accumulate` is **accepted** (warning only), not rejected.
2. Result is **order-sensitive**.
3. In this version, schema conflicts on `_updater` emit a warning but the new
   assignment still replaces the previous updater on that leaf.
4. Process updates are then applied sequentially in process registration order.
5. Therefore, mixed-updater same-leaf writes do **not** implement stable
   “set first, then accumulates on top” semantics.

### Test outcomes

- `test_set_plus_accumulate_three_way_merge` (A=`set 80`, B=`acc -10`, C=`acc +5`, order A,B,C): final `175`
- `test_process_registration_order_matters` (same writers, reversed C,B,A): final `80` (changed)
- `test_set_only_two_writers` (`set 80`, `set 70`): final `70` (later set wins)
- `test_accumulate_only_two_writers` (`acc -10`, `acc +5`): final `95` (additive baseline)
- `test_set_zero_plus_negative_accumulate` (`set 0`, `acc -10`, order A,B): final `90` (not `-10`)

## Why this happens (source-backed, not speculative)

In `vivarium.core.store.Store._apply_config`, `_updater` assignment is checked
through `_check_schema_support_defaults`. That function warns on incompatible
schema assignment but still returns the new schema, so the updater is replaced
rather than rejected (`store.py`, around lines 689-693 and 526-546 in
`vivarium-core 1.6.5`).

In `vivarium.core.engine.Engine.run_for`, updates ready at the tick boundary
are collected from `self.front` and passed to `_send_updates` in dictionary
iteration order (`engine.py`, around lines 1004-1015). `_send_updates` then
applies each update tuple sequentially (`engine.py`, around lines 857-860),
and each leaf update uses the leaf’s resolved updater (`store.py`, around
lines 1636 and 1651).

Together, these produce the observed order dependence.

## Verdict

**v2 design MUST use separate stores or a topology change.**

Reason: a same-leaf mixed `set`+`accumulate` contract is not robust. It depends
on process registration order and updater conflict resolution behavior rather
than a deterministic “set then delta” merge rule.

## Full command output

Command run:

```bash
pytest tests/probes/test_probe4_set_accumulate_merge.py -v
```

Output:

```text
/mnt/e/opencell/.venv-wsl/bin/pytest
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0 -- /mnt/e/opencell/.venv-wsl/bin/python3.12
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: /mnt/e/opencell-worktrees/probe4-set-accumulate
configfile: pyproject.toml
plugins: anyio-4.13.0, hypothesis-6.152.1, jaxtyping-0.3.9, cov-7.1.0
collecting ... collected 5 items

tests/probes/test_probe4_set_accumulate_merge.py::test_set_plus_accumulate_three_way_merge PASSED [ 20%]
tests/probes/test_probe4_set_accumulate_merge.py::test_process_registration_order_matters PASSED [ 40%]
tests/probes/test_probe4_set_accumulate_merge.py::test_set_only_two_writers PASSED [ 60%]
tests/probes/test_probe4_set_accumulate_merge.py::test_accumulate_only_two_writers PASSED [ 80%]
tests/probes/test_probe4_set_accumulate_merge.py::test_set_zero_plus_negative_accumulate PASSED [100%]

=============================== warnings summary ===============================
tests/probes/test_probe4_set_accumulate_merge.py::test_set_plus_accumulate_three_way_merge
tests/probes/test_probe4_set_accumulate_merge.py::test_process_registration_order_matters
tests/probes/test_probe4_set_accumulate_merge.py::test_set_zero_plus_negative_accumulate
  /mnt/e/opencell/.venv-wsl/lib/python3.12/site-packages/vivarium/core/store.py:542: UserWarning: Incompatible schema assignment at ('protein', 'counts', 'X'). Trying to assign the value <function update_accumulate at 0x7e6409f984a0> to key updater, which already has the value <function update_set at 0x7e6409f98360>.
    warnings.warn(

tests/probes/test_probe4_set_accumulate_merge.py::test_process_registration_order_matters
  /mnt/e/opencell/.venv-wsl/lib/python3.12/site-packages/vivarium/core/store.py:542: UserWarning: Incompatible schema assignment at ('protein', 'counts', 'X'). Trying to assign the value <function update_set at 0x7e6409f98360> to key updater, which already has the value <function update_accumulate at 0x7e6409f984a0>.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 5 passed, 4 warnings in 9.21s =========================
```
