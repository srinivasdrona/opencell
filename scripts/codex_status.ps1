#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Diagnose a running Codex `codex exec` delegation without waiting for STATUS.md.

.DESCRIPTION
  Codex's `codex exec` runs as a black box until it writes STATUS.md at the end.
  This script gives 4 visibility signals:
    1. Output file count in the expected output dir (grows with progress)
    2. stdout log idle time (active vs stuck)
    3. Last 8 lines of stdout (current activity)
    4. STATUS.md existence (task done indicator)

  Usage:
    .\scripts\codex_status.ps1 -Repo <worktree-path>
    .\scripts\codex_status.ps1 -Repo E:\opencell-worktrees\karr-extracts
    .\scripts\codex_status.ps1 -Repo E:\opencell-worktrees\karr-extracts -OutputDir docs/karr_extracts

  Run repeatedly to detect stalled tasks before they waste premium-request budget.

.PARAMETER Repo
  Path to the Codex worktree (must contain .codex_stdout.log).

.PARAMETER OutputDir
  Subdirectory inside the worktree where Codex is writing deliverables.
  Defaults to "docs/" if not specified.

.PARAMETER StuckThresholdSec
  Idle seconds above which the task is flagged as potentially stuck.
  Default 120s. Codex's reasoning-high model can think for ~60s on a single
  step without output, so 120s+ idle is the realistic "something's wrong"
  threshold.
#>
param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [string]$OutputDir = "docs",
    [int]$StuckThresholdSec = 120
)

$log = Join-Path $Repo ".codex_stdout.log"
$status = Join-Path $Repo "STATUS.md"
$out = Join-Path $Repo $OutputDir

Write-Host ""
Write-Host "Codex status — $Repo" -ForegroundColor Cyan
Write-Host ("=" * 70)

# 1. File count
if (Test-Path $out) {
    $files = Get-ChildItem $out -Recurse -File -ErrorAction SilentlyContinue
    Write-Host "Output files written : $($files.Count) in $OutputDir/"
    $newest = $files | Sort-Object LastWriteTime -Descending | Select-Object -First 3
    if ($newest) {
        Write-Host "  newest:" -ForegroundColor DarkGray
        $newest | ForEach-Object {
            $rel = $_.FullName.Replace($Repo + [IO.Path]::DirectorySeparatorChar, "")
            Write-Host ("    " + $_.LastWriteTime.ToString("HH:mm:ss") + "  " + $rel) -ForegroundColor DarkGray
        }
    }
} else {
    Write-Host "Output files written : 0 (output dir not yet created)" -ForegroundColor Yellow
}

# 2. stdout idle
if (Test-Path $log) {
    $logItem = Get-Item $log
    $idleSec = [int]((Get-Date) - $logItem.LastWriteTime).TotalSeconds
    $idleColor = if ($idleSec -gt $StuckThresholdSec) { "Red" } elseif ($idleSec -gt 60) { "Yellow" } else { "Green" }
    Write-Host "stdout idle          : $idleSec seconds (size: $('{0:N0}' -f $logItem.Length) bytes)" -ForegroundColor $idleColor
    if ($idleSec -gt $StuckThresholdSec) {
        Write-Host "  WARNING: idle > ${StuckThresholdSec}s — may be stuck. Consider stopping and re-prompting." -ForegroundColor Red
    }
} else {
    Write-Host "stdout idle          : (no .codex_stdout.log found)" -ForegroundColor Yellow
}

# 3. Recent stdout
if (Test-Path $log) {
    Write-Host ""
    Write-Host "Recent stdout (last 8 lines):" -ForegroundColor Cyan
    Get-Content $log -Tail 8 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
}

# 4. STATUS
Write-Host ""
if (Test-Path $status) {
    $stItem = Get-Item $status
    Write-Host "STATUS.md            : written $($stItem.LastWriteTime) ($('{0:N0}' -f $stItem.Length) bytes) — TASK COMPLETE" -ForegroundColor Green
} else {
    Write-Host "STATUS.md            : not yet written — task in flight" -ForegroundColor Yellow
}

Write-Host ""
Write-Host ("=" * 70)
Write-Host "Next: re-run in 30-60s to compare. File count should grow; idle should stay low."
Write-Host ""
