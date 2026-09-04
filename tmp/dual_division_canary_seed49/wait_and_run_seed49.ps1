<#
.SYNOPSIS
  Durable detached waiter for the seed-49 one-pass dual-tap
  Cytokinesis+FtsZPolymerization division-window canary.

.DESCRIPTION
  At launch time (2026-09-03 ~08:15 IST) this host was already running 8
  concurrent real MATLAB engine processes (4 pairs; the stated project
  policy is 4 concurrent MATLAB processes total -- see plan.md's
  "MATLAB concurrency increases from 2 to 4 shared slots" note) across
  several independent extraction lanes (Cytokinesis PID 18600, FtsZ PID
  22568/watchdog 7904, plus the L2.1 active-window five-lane wait
  (wait-l21-active-five)). This script's own worktree
  (E:\opencell-worktrees\fasttrack-division-dual) has an EMPTY, unused
  scripts\tools\run_matlab_slot.ps1 lock pool (artifacts\matlab_slots\) --
  that helper's file-lock mechanism is scoped per-worktree (confirmed by
  reading its source and every other worktree's own invocation, each of
  which passes its OWN -Worktree), so it would grant this canary a "slot"
  immediately even though the host is already oversubscribed relative to
  the stated 4-process policy. This script therefore adds an OUTER,
  host-wide gate in front of that helper: it polls the actual Windows
  process list for `matlab.exe`/`MATLAB.exe` and refuses to proceed until
  the real, host-wide count has dropped to a level that leaves genuine
  headroom under the stated policy -- never relying on this worktree's own
  (structurally blind) empty lock pool as evidence that a slot is free.

  Once that gate clears, this script:
    1. Runs `scripts\tools\run_matlab_slot.ps1` (this worktree's own copy,
       -Worktree pointing at THIS worktree only -- never a shared/foreign
       worktree path, so it cannot race any other queue's lock directory)
       with -Slots 4, invoking
       `extract_dual_division_window_seeds(49, 49)` for seed 49 only.
    2. On successful extraction, runs the combined Python canary validator
       (`scripts/l2_event/validate_dual_division_canary.py --seed 49`)
       via the WSL venv (per this project's execution-environment rule)
       and writes its JSON verdict to CANARY_RESULT.json.
    3. Writes a single-line DONE/FAILED marker to STATUS.txt so a later
       session can check completion without re-reading the full log.

  This script does not stop, edit, or otherwise interact with the live
  Cytokinesis (PID 18600) or FtsZ (PID 22568 / watchdog 7904) processes or
  their worktrees at any point.

.NOTES
  Launched once via:
    powershell -File tmp\dual_division_canary_seed49\wait_and_run_seed49.ps1
  as a detached background process (see STATUS_DUAL_DIVISION_EXTRACTOR.md
  for the recorded PID/log path). Safe to leave running unattended; it
  polls internally rather than requiring any external nudge.
#>

param(
    [string]$Worktree = "E:\opencell-worktrees\fasttrack-division-dual",
    # Each real MATLAB session on this host shows up as TWO OS processes
    # (an image named 'matlab' and a companion 'MATLAB' process, confirmed
    # empirically at launch time: 8 processes == 4 sessions, matching the
    # stated 4-slot project policy). This threshold is expressed in
    # SESSIONS, not raw OS process count -- see the ceiling-divide below.
    # Default 3 leaves genuine headroom for this canary to become the 4th
    # concurrent session under the stated policy, never oversubscribing
    # past it.
    [int]$MaxConcurrentMatlabSessions = 3,
    [int]$PollSeconds = 300,
    [int]$MaxWaitHours = 72
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $Worktree "tmp\dual_division_canary_seed49"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logPath = Join-Path $logDir "wait_and_run_seed49.log"
$statusPath = Join-Path $logDir "STATUS.txt"
$resultPath = Join-Path $logDir "CANARY_RESULT.json"

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $logPath -Value $line
    Write-Output $line
}

"WAITING (started $(Get-Date -Format o))" | Set-Content -LiteralPath $statusPath
Write-Log "wait_and_run_seed49 started. Worktree=$Worktree MaxConcurrentMatlabSessions=$MaxConcurrentMatlabSessions PollSeconds=$PollSeconds"

$deadline = (Get-Date).AddHours($MaxWaitHours)
while ($true) {
    $matlabProcessCount = (Get-Process -Name matlab, MATLAB -ErrorAction SilentlyContinue | Measure-Object).Count
    # Ceiling-divide by 2 (see param docstring) so an odd/unpaired process
    # (a session mid-startup/shutdown) is never under-counted as fewer
    # sessions than actually exist.
    $matlabSessionCount = [Math]::Ceiling($matlabProcessCount / 2.0)
    Write-Log "host-wide matlab/MATLAB process count = $matlabProcessCount (~$matlabSessionCount session(s); threshold < $MaxConcurrentMatlabSessions)"
    if ($matlabSessionCount -lt $MaxConcurrentMatlabSessions) {
        break
    }
    if ((Get-Date) -ge $deadline) {
        "FAILED (timed out waiting for a host-wide MATLAB slot after $MaxWaitHours hours, $(Get-Date -Format o))" | Set-Content -LiteralPath $statusPath
        Write-Log "TIMED OUT waiting for host-wide MATLAB headroom after $MaxWaitHours hours. Exiting without running the canary."
        exit 1
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-Log "host-wide MATLAB headroom detected (~$matlabSessionCount session(s) < $MaxConcurrentMatlabSessions). Acquiring a slot via scripts\tools\run_matlab_slot.ps1 -Slots 4 ..."
"RUNNING (matlab extraction started $(Get-Date -Format o))" | Set-Content -LiteralPath $statusPath

$slotHelper = Join-Path $Worktree "scripts\tools\run_matlab_slot.ps1"
$matlabRoot = ($Worktree -replace '\\', '/').Replace("'", "''")
$matlabCommand = "addpath(genpath('$matlabRoot/scripts/matlab')); extract_dual_division_window_seeds(49, 49)"

try {
    & $slotHelper -Worktree $Worktree -MatlabCommand $matlabCommand -Tag "dual_division_canary_seed49" -Slots 4 -TimeoutMinutes 720 *>> $logPath
    $extractExit = $LASTEXITCODE
}
catch {
    Write-Log "MATLAB extraction FAILED: $($_.Exception.Message)"
    "FAILED (matlab extraction raised: $($_.Exception.Message); $(Get-Date -Format o))" | Set-Content -LiteralPath $statusPath
    exit 1
}

Write-Log "MATLAB extraction finished (exit=$extractExit). Running combined Python canary validator ..."

$wslCmd = "cd /mnt/e/opencell-worktrees/fasttrack-division-dual && source /mnt/e/opencell/.venv-wsl/bin/activate && python scripts/l2_event/validate_dual_division_canary.py --seed 49"
$validatorOutput = & wsl -e bash -lc $wslCmd 2>&1
$validatorExit = $LASTEXITCODE
$validatorOutput | Set-Content -LiteralPath $resultPath
Add-Content -LiteralPath $logPath -Value $validatorOutput

if ($validatorExit -eq 0) {
    "DONE (validator PASS, $(Get-Date -Format o)) -- see CANARY_RESULT.json" | Set-Content -LiteralPath $statusPath
    Write-Log "Combined canary validator PASS."
} else {
    "DONE (validator FAIL, $(Get-Date -Format o)) -- see CANARY_RESULT.json" | Set-Content -LiteralPath $statusPath
    Write-Log "Combined canary validator FAIL (exit=$validatorExit). See CANARY_RESULT.json / log for reasons."
}
