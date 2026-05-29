@echo off
REM oc-py — invoke the OpenCell WSL venv Python from any worktree.
REM Usage:  bin\oc-py <args>     (from repo or worktree root)
REM Equivalent to:
REM   wsl -e bash -lc "cd <wsl-cwd> && source /mnt/e/opencell/.venv-wsl/bin/activate && python <args>"
REM
REM The wrapper translates the current Windows CWD to a WSL path so that
REM relative arguments (e.g. tests/vivarium/foo.py) resolve correctly in the
REM caller's worktree, while still sourcing the single canonical venv that
REM lives in the main repo. The editable install in .venv-wsl points at
REM /mnt/e/opencell/src, so worktree tests with their own sys.path tweaks
REM (see _REPO_ROOT pattern in test_karr_*_l2_replay.py) still pick up
REM their own copy of `opencell` correctly.
REM
REM Known limitation: `oc-py -c "code"` does NOT preserve the quoted string —
REM cmd.exe `%*` strips outer quotes. For ad-hoc one-liners use either:
REM   - `oc-py script.py` (write the code to a file), or
REM   - the long form `wsl -e bash -lc "source ... && python -c '...'"`.
REM 99% of Codex invocations are `oc-py script.py` or `oc-pytest path -opts`,
REM both of which work correctly.

setlocal
for /f "delims=" %%i in ('wsl wslpath -u "%CD%"') do set "_WSLCWD=%%i"
wsl -e bash -lc "cd '%_WSLCWD%' && source /mnt/e/opencell/.venv-wsl/bin/activate && python %*"
endlocal
