<#
.SYNOPSIS
  Two-slot launcher for MacromolecularComplexation genuine active-window extraction.

.DESCRIPTION
  Launches one fresh MATLAB batch process per requested seed, with bounded
  parallelism (default 2 workers). Each seed runs the process-local
  `extract_macromol_active_window_seeds(seed, seed, force_seeds)` driver, so
  trigger detection and 100-tick capture happen on the same trajectory and the
  driver's own validation/skip logic remains authoritative.
#>
[CmdletBinding()]
param(
    [string]$Seeds = "0-49",
    [int]$Workers = 2,
    [string]$MatlabExe = "E:\MATLAB\bin\matlab.exe",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $MatlabExe)) {
    throw "MATLAB executable not found at '$MatlabExe'."
}
if ($Workers -lt 1) {
    throw "Workers must be >= 1."
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ArtifactsDir = Join-Path $RepoRoot "artifacts\l22_macromol_active_window"
$LogDir = Join-Path $ArtifactsDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Parse-Seeds([string]$Spec) {
    $set = New-Object System.Collections.Generic.SortedSet[int]
    foreach ($chunk in $Spec.Split(",")) {
        $part = $chunk.Trim()
        if (-not $part) { continue }
        if ($part.Contains("-")) {
            $bounds = $part.Split("-", 2)
            $lo = [int]$bounds[0]
            $hi = [int]$bounds[1]
            foreach ($seed in $lo..$hi) { [void]$set.Add($seed) }
        }
        else {
            [void]$set.Add([int]$part)
        }
    }
    return @($set)
}

function Build-MatlabCommand([int]$Seed, [bool]$ForceSeed, [string]$StdoutLog) {
    $forceVector = if ($ForceSeed) { "[$Seed]" } else { "[]" }
    return (
        "addpath('scripts/matlab'); " +
        "diary('$StdoutLog'); " +
        "try; extract_macromol_active_window_seeds($Seed, $Seed, $forceVector); " +
        "catch err; disp(getReport(err, 'extended', 'hyperlinks', 'off')); rethrow(err); " +
        "end; diary off;"
    )
}

$pendingSeeds = Parse-Seeds $Seeds
$active = @()
$failures = @()

while ($pendingSeeds.Count -gt 0 -or $active.Count -gt 0) {
    while ($pendingSeeds.Count -gt 0 -and $active.Count -lt $Workers) {
        $seed = $pendingSeeds[0]
        if ($pendingSeeds.Count -eq 1) {
            $pendingSeeds = @()
        }
        else {
            $pendingSeeds = $pendingSeeds[1..($pendingSeeds.Count - 1)]
        }

        $stdoutLog = Join-Path $LogDir ("seed{0:D3}.stdout.log" -f $seed)
        $stderrLog = Join-Path $LogDir ("seed{0:D3}.stderr.log" -f $seed)
        $batch = Build-MatlabCommand -Seed $seed -ForceSeed:$Force -StdoutLog ($stdoutLog -replace "\\", "/")
        $argString = "-batch `"$batch`""

        Write-Host "[run_macromol_active_window_seeds] launching seed=$seed -> $stdoutLog"
        $proc = Start-Process -FilePath $MatlabExe `
            -ArgumentList $argString `
            -WorkingDirectory $RepoRoot `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError $stderrLog `
            -WindowStyle Hidden `
            -PassThru
        $active += [pscustomobject]@{
            Seed = $seed
            Process = $proc
            StdoutLog = $stdoutLog
            StderrLog = $stderrLog
        }
    }

    if ($active.Count -eq 0) {
        break
    }

    Start-Sleep -Seconds 2
    $stillActive = @()
    foreach ($entry in $active) {
        if (-not $entry.Process.HasExited) {
            $stillActive += $entry
            continue
        }
        $entry.Process.WaitForExit()
        $entry.Process.Refresh()
        $exitCode = $entry.Process.ExitCode
        if ($null -eq $exitCode -or "$exitCode" -eq "") {
            $stderrText = if (Test-Path $entry.StderrLog) { Get-Content $entry.StderrLog -Raw } else { "" }
            $stdoutText = if (Test-Path $entry.StdoutLog) { Get-Content $entry.StdoutLog -Raw } else { "" }
            if (($stderrText -match "MATLAB error Exit Status") -or ($stdoutText -match "Error using ") -or ($stdoutText -match "FAILED during extraction")) {
                $exitCode = 1
            }
            else {
                $exitCode = 0
            }
        }
        Write-Host "[run_macromol_active_window_seeds] seed=$($entry.Seed) exit=$exitCode"
        if ($exitCode -ne 0) {
            $failures += $entry
        }
    }
    $active = $stillActive
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) {
        Write-Host "[run_macromol_active_window_seeds] FAILED seed=$($failure.Seed) stderr=$($failure.StderrLog)"
    }
    throw "$($failures.Count) seed(s) failed."
}

Write-Host "[run_macromol_active_window_seeds] completed seeds: $Seeds"
