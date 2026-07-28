@echo off
REM oc-pytest — invoke pytest under the OpenCell WSL venv from any worktree.
REM Usage:  bin\oc-pytest <args>     (from repo or worktree root)
REM See bin\oc-py.cmd for design notes.

setlocal
for /f "delims=" %%i in ('wsl wslpath -u "%CD%"') do set "_WSLCWD=%%i"
wsl -e bash -lc "cd '%_WSLCWD%' && source /mnt/e/opencell/.venv-wsl/bin/activate && pytest %*"
REM Capture the WSL child's exit code before endlocal discards it. A bare
REM `endlocal` as the script's final statement makes cmd.exe report the exit
REM code of `endlocal` itself (always 0), silently swallowing any failure
REM from the wrapped command — this must be preserved explicitly.
set "_RC=%ERRORLEVEL%"
endlocal & exit /b %_RC%
