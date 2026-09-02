<#
.SYNOPSIS
  Quote-safe, slot-coordinated MATLAB batch job launcher.

.DESCRIPTION
  Self-contained (no dependency on any tool outside this repo) replacement
  for the ad-hoc "PowerShell -> matlab.exe -batch <string>" invocation
  pattern, fixing two independent, previously-hit failure modes:

  1. Quote-stripping: passing a MATLAB command that itself contains
     embedded double-quoted strings (e.g. `jsonencode(struct(...))` or any
     literal JSON) through `-ArgumentList`/`%*`-style forwarding corrupts
     the quote boundaries somewhere in the PowerShell -> matlab.exe argv
     chain -- the embedded quotes are silently stripped or the argument is
     truncated at the first embedded space, and MATLAB either errors or
     (worse) silently runs a truncated command with no error, no diary,
     and no output. This class of bug was independently hit twice this
     project (`run_l22_seed_shards.ps1`'s explicit double-quote guard, and
     the DNADamage genuine-corpus re-extraction's ad-hoc, never-tracked
     workaround). The fix here is structural, not a guard: the caller's
     MATLAB command is ALWAYS written verbatim to a scratch `.m` file
     first, and the actual `-batch` argument passed to matlab.exe is the
     minimal, quote-free `run('<path-to-that-file>')` -- no caller-supplied
     text ever crosses the PowerShell/cmd argv boundary embedded inside an
     already-quoted string.
  2. Uncoordinated concurrent MATLAB launches: this project's MATLAB
     license/host is shared across parallel worktree agents; running more
     than a bounded number of simultaneous `matlab.exe` processes causes
     license checkout contention and host resource exhaustion. This
     script reimplements the same file-lock-based slot-acquisition
     mechanism as the fleet-wide coordination tool (create-new exclusive
     lock files under a slots directory, retry with stale-lock reclamation
     via `Get-Process`), but self-contained under `artifacts/matlab_slots/`
     (already gitignored -- see `.gitignore`) so it works in a fresh clone
     without depending on any path outside this repository.

.PARAMETER Worktree
  Repo root (or worktree root) the MATLAB process should run from
  (its current directory). Defaults to this repo root.

.PARAMETER MatlabCommand
  The full MATLAB statement(s) to execute, exactly as you would write them
  inside MATLAB -- may freely contain double quotes, single quotes,
  parentheses, semicolons, embedded JSON, etc. Never quote-escaped by the
  caller; this script handles the entire escaping/argv problem internally
  by routing the command through a scratch `.m` file rather than the
  command line.

.PARAMETER Tag
  Short label identifying this job (used in the lock-file payload, log
  filename, and scratch script filename) for observability when polling
  `artifacts/matlab_slots/` or tailing the log.

.PARAMETER Slots
  Maximum number of concurrent MATLAB processes sharing this lock pool.
  Default 2 (matches this project's default fleet-wide policy; raise to
  match whatever concurrency the operator has explicitly authorized, e.g.
  `-Slots 4` per `plan.md`'s relaunch-intent notes).

.PARAMETER MatlabExe
  Path to `matlab.exe`. Defaults to `E:\MATLAB\bin\matlab.exe` (this
  machine's install location); override for a different host.

.PARAMETER TimeoutMinutes
  Give up waiting for a free slot after this many minutes (default 720).

.PARAMETER KeepScratchScript
  Do not delete the generated `.m` scratch file after the job finishes
  (useful for debugging a failed job's exact literal command).

.EXAMPLE
  # A command containing embedded JSON double quotes -- would corrupt via
  # naive -batch string passing; safe here because it never touches argv.
  scripts\tools\run_matlab_slot.ps1 -Tag "dnadamage_seed2000" -Slots 4 `
    -MatlabCommand "addpath('scripts/matlab'); karr_bootstrap.ensure_dnadamage_signed_zero_overlay(struct('seed',2000,'note','uvb_mechanism'));"

.NOTES
  This script supersedes the never-tracked, session-local PowerShell
  workaround described in `STATUS_L22_DNADAMAGE_SEPT2.md` item 8
  ("writing each job's command to a temp .m script file and invoking via
  a quote-free -MatlabExpression"); that workaround's logic is what this
  script formalizes as a committed, reusable tool.
#>
[CmdletBinding()]
param(
    [string]$Worktree,

    [Parameter(Mandatory = $true)]
    [string]$MatlabCommand,

    [Parameter(Mandatory = $true)]
    [string]$Tag,

    [int]$Slots = 2,
    [string]$MatlabExe = "E:\MATLAB\bin\matlab.exe",
    [int]$TimeoutMinutes = 720,
    [switch]$KeepScratchScript
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot is not reliably populated inside a [string]$Worktree = (...)
# default-value expression under Windows PowerShell 5.1 -- resolved here in
# the script body instead, where it is always set.
if ([string]::IsNullOrWhiteSpace($Worktree)) {
    $Worktree = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

if (-not (Test-Path $MatlabExe)) {
    throw "MATLAB executable not found at '$MatlabExe'. Pass -MatlabExe to override."
}
if (-not (Test-Path $Worktree)) {
    throw "Worktree path '$Worktree' does not exist."
}

# --- Sanitize the tag for safe use in filenames -----------------------------
$safeTag = ($Tag -replace '[^A-Za-z0-9_\-]', '_')
if ([string]::IsNullOrWhiteSpace($safeTag)) {
    throw "-Tag must contain at least one alphanumeric/underscore/hyphen character."
}

# --- Scratch locations (all under artifacts/, already gitignored) ----------
$scratchRoot = Join-Path $Worktree "artifacts\matlab_jobs"
$lockRoot = Join-Path $Worktree "artifacts\matlab_slots"
New-Item -ItemType Directory -Path $scratchRoot -Force | Out-Null
New-Item -ItemType Directory -Path $lockRoot -Force | Out-Null

$jobId = "{0}_{1}_{2}" -f $safeTag, (Get-Date -Format "yyyyMMdd_HHmmss"), $PID
$scriptPath = Join-Path $scratchRoot "$jobId.m"
$logPath = Join-Path $scratchRoot "$jobId.log"

# Write the caller's literal MATLAB command verbatim to the scratch file.
# UTF8 (no BOM) so raw bytes matter here (see karr_bootstrap.m's own
# raw-byte-hashing rationale) round-trip through MATLAB's file reader
# unmodified -- no shell ever re-tokenizes this content.
[System.IO.File]::WriteAllText($scriptPath, $MatlabCommand, [System.Text.UTF8Encoding]::new($false))

# The ONLY string that ever crosses the PowerShell -> matlab.exe argv
# boundary is this fixed, quote-free template -- the scratch path is
# forward-slashed (MATLAB accepts forward slashes on Windows) and
# single-quoted per MATLAB string-literal syntax; a literal single quote
# inside the path itself is escaped MATLAB-style ('' ), covering the
# (extremely unlikely on this host) case of a quote in the scratch path.
$scriptPathForMatlab = ($scriptPath -replace '\\', '/') -replace "'", "''"
$batchExpression = "run('$scriptPathForMatlab')"

# --- Slot acquisition (self-contained; see .DESCRIPTION) --------------------
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$lockPath = $null
$lockStream = $null

while (-not $lockStream) {
    for ($slot = 1; $slot -le $Slots; $slot++) {
        $candidate = Join-Path $lockRoot "slot-$slot.lock"
        try {
            $lockStream = [System.IO.File]::Open(
                $candidate,
                [System.IO.FileMode]::CreateNew,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None
            )
            $lockPath = $candidate
            $payload = [System.Text.Encoding]::UTF8.GetBytes(
                "$PID`n$Tag`n$Worktree`n$([DateTime]::UtcNow.ToString('O'))`n"
            )
            $lockStream.Write($payload, 0, $payload.Length)
            $lockStream.Flush()
            break
        }
        catch [System.IO.IOException] {
            try {
                $holderPid = [int](Get-Content $candidate -TotalCount 1 -ErrorAction Stop)
                if (-not (Get-Process -Id $holderPid -ErrorAction SilentlyContinue)) {
                    Remove-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue
                }
            }
            catch {
                # Holder may still be mid-write; retry next pass.
            }
        }
    }

    if (-not $lockStream) {
        if ((Get-Date) -ge $deadline) {
            throw "Timed out waiting for a MATLAB slot ($Slots total) after $TimeoutMinutes minutes."
        }
        Start-Sleep -Seconds 10
    }
}

try {
    Write-Output "MATLAB_SLOT_ACQUIRED path=$lockPath tag=$Tag script=$scriptPath"
    Push-Location -LiteralPath $Worktree
    try {
        & $MatlabExe -batch $batchExpression 2>&1 | Tee-Object -FilePath $logPath
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($lockStream) { $lockStream.Dispose() }
    if ($lockPath) { Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue }
    if (-not $KeepScratchScript) {
        Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue
    }
}

if ($exitCode -ne 0) {
    throw "MATLAB exited with code $exitCode. See $logPath (and, if -KeepScratchScript, $scriptPath)."
}
