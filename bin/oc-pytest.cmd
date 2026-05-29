@echo off
REM oc-pytest — invoke pytest under the OpenCell WSL venv from any worktree.
REM Usage:  bin\oc-pytest <args>     (from repo or worktree root)
REM See bin\oc-py.cmd for design notes.

setlocal
for /f "delims=" %%i in ('wsl wslpath -u "%CD%"') do set "_WSLCWD=%%i"
wsl -e bash -lc "cd '%_WSLCWD%' && source /mnt/e/opencell/.venv-wsl/bin/activate && pytest %*"
endlocal
