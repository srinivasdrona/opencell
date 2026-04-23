# Shell exit-code gotchas

The CLIs in `tools/` (`extract_param.py`, `biomodels_manifest.py`,
`curate_params.py`) use **meaningful exit codes**:

| Code | Meaning |
|---|---|
| 0 | Success — RECOMMEND or all SKIPPED |
| 1 | At least one AMBIGUOUS — human arbitration needed |
| 2 | At least one NOT_FOUND / ALL_REJECTED |

If you wrap a CLI in a script (CI gate, batch runner, etc.) **and pipe
its output**, you must defend against two well-known traps that silently
discard the real exit code.

## Trap 1 — bash pipes mask exit codes

```bash
python tools/curate_params.py ... | tail -25
echo $?     # ❌ this is tail's exit code (always 0), NOT the CLI's
```

Fix — pick one:

```bash
# A. global pipefail (recommended for new scripts)
set -o pipefail
python tools/curate_params.py ... | tail -25
echo "rc=$?"

# B. PIPESTATUS array (no global setting)
python tools/curate_params.py ... | tail -25
echo "rc=${PIPESTATUS[0]}"     # exit of the first command in the pipe

# C. avoid the pipe entirely
out=$(python tools/curate_params.py ...); rc=$?
echo "$out" | tail -25
exit $rc
```

## Trap 2 — PowerShell intercepts `$?` and other shell variables

When invoking bash *from PowerShell* with single-quoted strings:

```powershell
wsl bash -lc 'python tools/curate_params.py ...; echo "rc=$?"'
# ❌ PowerShell expands $? as its own automatic variable BEFORE
#    handing the string to bash. You'll see "rc=" or "rc=True".
```

PowerShell treats `$?` (boolean), `$_`, `$args`, `$LASTEXITCODE`, and
any other `$name` it recognizes as its own. Single quotes prevent
PowerShell variable expansion in *most* contexts, but the externalized
arg-pass to `wsl.exe` is special.

Fix — pick one:

```powershell
# A. escape with PowerShell backtick (safe everywhere)
wsl bash -lc 'python ...; echo "rc=`$?"'

# B. capture in Python via subprocess (most reliable)
wsl python -c "
import subprocess
r = subprocess.run(['python', 'tools/curate_params.py', '...'])
print('rc=', r.returncode)
"

# C. write a real .sh file and invoke it instead of inline -lc
wsl bash /mnt/e/opencell/scripts/run_curator.sh
```

## Recommendation for CI

Use option (A) `set -o pipefail` at the top of every shell script that
chains a CLI through `tee`, `tail`, or any pipe. Both `extract_param.py`
and `curate_params.py` rely on the exit code to gate downstream steps —
silently dropping it produces "all-green CI" runs that hide real misses.
