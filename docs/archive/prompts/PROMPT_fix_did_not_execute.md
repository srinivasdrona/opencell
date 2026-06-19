# Fix-Did-Not-Execute Validation (C1/C2/C3)

## Context

`substrate-cascade-fix` v3 landed cleanly. All targeted tests pass. But the 100-tick canary produced **identical** numbers to pre-fix (ATP=-43750, exactly -437.5/tick × 100). This suggests the fix did not actually execute at runtime. Three candidate explanations — your job is to validate or refute each empirically.

## Token budget

100k ceiling. Hand off cleanly if you hit it. You should fit comfortably in 30-40k.

## Hypotheses to validate

### C1: Canary imports from main `/mnt/e/opencell/`, not the worktree

The diagnostic script `scripts/diagnose_substrate_leak.py` lives in `/mnt/e/opencell-worktrees/substrate-cascade-fix/`. But Python imports may resolve to:
- The worktree path (correct), OR
- `/mnt/e/opencell/` (main, has the pre-fix code), OR
- An editable install (`pip install -e .`) pointing at main

**Method**:
1. Read `head -50 /mnt/e/opencell-worktrees/substrate-cascade-fix/scripts/diagnose_substrate_leak.py` — look for `sys.path.insert`, `os.chdir`, repo-root resolution
2. Run this from the worktree:
   ```
   source /mnt/e/opencell/.venv-wsl/bin/activate
   cd /mnt/e/opencell-worktrees/substrate-cascade-fix
   python -c "import opencell.vivarium.karr_composite as m; print(m.__file__)"
   python -c "import opencell.vivarium.karr_transcription_v3 as m; print(m.__file__)"
   ```
3. If the printed paths include `/mnt/e/opencell/` (not the worktree), C1 is **CONFIRMED**

### C2: write_substrate_deltas override didn't take effect

The fix in `karr_composite.py:1875` does:
```python
proc.parameters["write_substrate_deltas"] = False
```

This fails if vivarium's `Process.parameters` is a frozen MappingProxy, OR if the process caches the value at `__init__` into an instance attr.

**Method**:
1. Read `karr_transcription_v3.py` `__init__` and `next_update` (just the function bodies, ~30 lines each)
   - Is `write_substrate_deltas` cached as `self._write_substrate_deltas` (or similar)?
   - Or read fresh as `self.parameters["write_substrate_deltas"]` each tick?
2. Test the override empirically:
   ```python
   # scripts/verify_param_override.py
   from opencell.vivarium.karr_composite import build_karr_chassis_v6
   composite = build_karr_chassis_v6()
   for key in ("karr_transcription", "karr_translation"):
       proc = composite.processes[key]
       print(key, "write_substrate_deltas =", proc.parameters.get("write_substrate_deltas"))
   ```
3. If both print `False`, parameter override works. If `True` or KeyError, **C2 CONFIRMED**.

### C3: Old `_v3` key survives or process runs twice

The chassis_v6 builder does `processes[new_key] = processes.pop(old_key)`. If `flow` or `topology` still references the old key, the engine may run the process twice.

**Method**:
1. Extend the script from C2:
   ```python
   import re
   keys = list(composite.processes.keys())
   print("Process count:", len(keys))
   v3_keys = [k for k in keys if "_v3" in k]
   print("v3 keys remaining:", v3_keys)
   print("Topology keys:", sorted(composite.topology.keys()))
   flow_dict = composite.flow if hasattr(composite, "flow") else {}
   print("Flow keys:", sorted(flow_dict.keys()) if flow_dict else "no flow attr")
   ```
2. If count > 28, OR `_v3` keys present, OR topology/flow has stale `_v3` references: **C3 CONFIRMED**

### C4 (bonus, cheap): allocation runs in wrong order

If allocation happens AFTER consumers in the flow, consumers always see zero allocation.

**Method**:
1. Print `composite.flow.get("karr_allocation_step")` — its dependencies (predecessors)
2. Print which processes have `("karr_allocation_step",)` as a flow dep — those run AFTER allocation
3. `karr_transcription` and `karr_translation` should depend on allocation; if they don't, **C4 CONFIRMED**

## Deliverable

Write `docs/hypotheses/fix_did_not_execute.md` with sections per hypothesis:

```
## C1: Canary imports wrong package
**Status**: CONFIRMED / REFUTED
**Evidence**: <paste import paths>
**Strategy implication**: <1 line>

## C2: ...
## C3: ...
## C4: ...
```

Then write `STATUS.md` at root summarizing.

## Commit cadence

Commit after each hypothesis (`C1 validation: <verdict>`).

## Read-only

Do not modify any source code. Helper scripts in `scripts/` are OK to create.
