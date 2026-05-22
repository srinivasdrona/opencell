A3.3 Turn 1 completed at 2026-05-22 21:09:35 +05:30

Summary
- Implemented M2v3 + M3v3 delta-emit conversion by addition (v2 files untouched).
- Added 4 new files:
  1) opencell/vivarium/karr_m2_v3.py (121 LOC)
  2) opencell/vivarium/karr_m3_v3.py (122 LOC)
  3) tests/vivarium/test_karr_m2_v3.py (105 LOC)
  4) tests/vivarium/test_karr_m3_v3.py (107 LOC)
- New tests added: 8 total (4 in each new test module).

Environment note
- Windows Python lacked `vivarium`; verification was run through WSL venv:
  - /mnt/e/opencell/.venv-wsl/bin/python
  - /mnt/e/opencell/.venv-wsl/bin/pytest
- During full-suite run, worktree lacked `data/m1_sources/karr_flat`; created a local junction to existing dataset at `E:\opencell\data\m1_sources\karr_flat` so the required command could run successfully.

Verification step 1
Command:
python -c "from opencell.vivarium.karr_m2_v3 import KarrTranscriptionV3Process; KarrTranscriptionV3Process({}).ports_schema()"
Executed as:
wsl bash -lc 'cd /mnt/e/opencell-worktrees/a33-m2m3-v3 && PYTHONPATH=/mnt/e/opencell-worktrees/a33-m2m3-v3 /mnt/e/opencell/.venv-wsl/bin/python -c "from opencell.vivarium.karr_m2_v3 import KarrTranscriptionV3Process; KarrTranscriptionV3Process({}).ports_schema(); print(\"m2v3 ports_schema ok\")"'
Output:
m2v3 ports_schema ok

Verification step 2
Command:
python -c "from opencell.vivarium.karr_m3_v3 import KarrTranslationV3Process; KarrTranslationV3Process({}).ports_schema()"
Executed as:
wsl bash -lc 'cd /mnt/e/opencell-worktrees/a33-m2m3-v3 && PYTHONPATH=/mnt/e/opencell-worktrees/a33-m2m3-v3 /mnt/e/opencell/.venv-wsl/bin/python -c "from opencell.vivarium.karr_m3_v3 import KarrTranslationV3Process; KarrTranslationV3Process({}).ports_schema(); print(\"m3v3 ports_schema ok\")"'
Output:
m3v3 ports_schema ok

Verification step 3
Command:
pytest tests/vivarium/test_karr_m2_v3.py tests/vivarium/test_karr_m3_v3.py -v
Executed as:
wsl bash -lc 'cd /mnt/e/opencell-worktrees/a33-m2m3-v3 && PYTHONPATH=/mnt/e/opencell-worktrees/a33-m2m3-v3 /mnt/e/opencell/.venv-wsl/bin/pytest tests/vivarium/test_karr_m2_v3.py tests/vivarium/test_karr_m3_v3.py -v'
Full output:
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0 -- /mnt/e/opencell/.venv-wsl/bin/python3.12
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: /mnt/e/opencell-worktrees/a33-m2m3-v3
configfile: pyproject.toml
plugins: anyio-4.13.0, hypothesis-6.152.1, jaxtyping-0.3.9, cov-7.1.0
collecting ... collected 8 items

tests/vivarium/test_karr_m2_v3.py::test_delta_equals_v2_absolute PASSED  [ 12%]
tests/vivarium/test_karr_m2_v3.py::test_schema_only_accumulate PASSED    [ 25%]
tests/vivarium/test_karr_m2_v3.py::test_order_insensitivity PASSED       [ 37%]
tests/vivarium/test_karr_m2_v3.py::test_substrate_delta_unchanged PASSED [ 50%]
tests/vivarium/test_karr_m3_v3.py::test_delta_equals_v2_absolute PASSED  [ 62%]
tests/vivarium/test_karr_m3_v3.py::test_schema_only_accumulate PASSED    [ 75%]
tests/vivarium/test_karr_m3_v3.py::test_order_insensitivity PASSED       [ 87%]
tests/vivarium/test_karr_m3_v3.py::test_substrate_delta_unchanged PASSED [100%]

============================== 8 passed in 31.78s ==============================

Verification step 4
Command:
pytest tests/ -x --ignore=tests/probes -q
Executed as:
wsl bash -lc 'cd /mnt/e/opencell-worktrees/a33-m2m3-v3 && PYTHONPATH=/mnt/e/opencell-worktrees/a33-m2m3-v3 /mnt/e/opencell/.venv-wsl/bin/pytest tests/ -x --ignore=tests/probes -q'
Full output:
........................................................................ [ 11%]
........................................................................ [ 22%]
.......................x.....xx.x....................................... [ 34%]
.........................sss............................................ [ 45%]
..............ssssssss.................................................. [ 57%]
........................................................................ [ 68%]
........................................................................ [ 80%]
........................................................................ [ 91%]
...................................................                      [100%]
=============================== warnings summary ===============================
tests/gates/test_g17_pysces_oracle.py::TestGateG17PyscesOracle::test_pysces_recovers_analytical_steady_state
  /mnt/e/opencell/.venv-wsl/lib/python3.12/site-packages/pysces/PyscesModel.py:4051: ODEintWarning: Integration successful.
    sim_res, infodict = scipy.integrate.odeint(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
612 passed, 11 skipped, 4 xfailed, 1 warning in 853.01s (0:14:13)

Verification step 5
Command:
git diff --stat HEAD -- opencell/vivarium/karr_m2_v2.py opencell/vivarium/karr_m3_v2.py
Output:
(no output)

Acceptance gate check
- [x] Verification steps passed
- [x] Added two new source files + two new test files
- [x] v2 files unchanged
- [x] Commit message used: a33-t1: M2v3 + M3v3 delta-emit (accumulate updater)
