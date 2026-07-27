<#
.SYNOPSIS
  Bounded-parallel MATLAB launcher for the L2.2 full multi-seed Karr oracle
  extraction (production process set derived mechanically by
  scripts/l22_extraction/derive_scope.py).

.DESCRIPTION
  Thin PowerShell driver around scripts/l22_extraction/launcher.py ("plan"
  mode, which does validate-before-skip file planning and seed-sharding) and
  E:\MATLAB\bin\matlab.exe (the actual extraction, via the existing,
  unmodified scripts/matlab/extract_per_process_traces_v2.m). No new MATLAB
  code is introduced here; this only bounds parallelism, assigns disjoint
  per-seed output directories to each worker, and records per-job logs +
  a resumable run-state file.

  Seeds are sharded round-robin across -Workers MATLAB batch processes, one
  process per worker, each running its assigned seeds sequentially inside a
  single MATLAB session (amortizing startup cost) with diary()-wrapped
  try/catch per seed so one seed's failure does not abort the rest of that
  worker's shard. Never touches seed 0 (canonical/unsuffixed; enforced by
  the Python planner's SeedZeroForbiddenError).

.PARAMETER Processes
  Comma-separated process names (e.g. "RNADecay,ProteinDecay"). No default:
  callers must pass the exact scope (see derive_scope.py for the mechanical
  production-set derivation) rather than relying on an implicit "everything".

.PARAMETER Seeds
  Explicit seed spec, e.g. "1" or "2-49" or "1,2,5-10". Seed 0 is rejected.

.PARAMETER Workers
  Bounded parallel MATLAB worker count. Default 2 per task policy (start
  with 2; only raise to 3-4 after a small shard proves stable/license-safe).

.PARAMETER DryRun
  Build and print the plan without launching any MATLAB process.

.PARAMETER NoWait
  Launch workers detached and return immediately (prints PIDs/log paths).
  Use this for the long seeds-2-49 production run; poll run-state JSON or
  the per-seed logs to check progress later. Without -NoWait, the script
  blocks until every worker process exits.

.EXAMPLE
  # Phase 2 preflight: seed 1 only, 2 workers, block until done.
  scripts\matlab\run_l22_seed_shards.ps1 -Processes (Get-Content processes.txt -Raw) -Seeds "1" -Workers 2

.EXAMPLE
  # Phase 3 production run: seeds 2-49, detached.
  scripts\matlab\run_l22_seed_shards.ps1 -Processes $prodList -Seeds "2-49" -Workers 2 -NoWait
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Processes,
    [Parameter(Mandatory = $true)][string]$Seeds,
    [int]$Workers = 2,
    [int]$NTicks = 100,
    [string]$MatlabExe = "E:\MATLAB\bin\matlab.exe",
    [switch]$DryRun,
    [switch]$NoWait,
    [switch]$NoValidate,
    [string]$PlanOut,
    [string]$RunTag
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$OcPy = Join-Path $RepoRoot "bin\oc-py.cmd"
if (-not (Test-Path $OcPy)) {
    throw "Cannot find bin\oc-py.cmd under repo root '$RepoRoot'. Run this script from the target worktree."
}
if (-not (Test-Path $MatlabExe)) {
    throw "MATLAB executable not found at '$MatlabExe'."
}

if (-not $RunTag) {
    $RunTag = Get-Date -Format "yyyyMMdd_HHmmss"
}
$ArtifactsDir = Join-Path $RepoRoot "artifacts\l22_full_extraction"
$LogDir = Join-Path $ArtifactsDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not $PlanOut) {
    $PlanOut = Join-Path $ArtifactsDir "plan_$RunTag.json"
}
$PlanOutRel = "artifacts/l22_full_extraction/plan_$RunTag.json"

Push-Location $RepoRoot
try {
    $planArgs = @(
        "scripts/l22_extraction/launcher.py", "plan",
        "--processes", $Processes,
        "--seeds", $Seeds,
        "--n-ticks", $NTicks,
        "--workers", $Workers,
        "--apply-invalidation",
        "--out", $PlanOutRel
    )
    if ($NoValidate) { $planArgs += "--no-validate" }

    Write-Host "[run_l22_seed_shards] building plan via bin\oc-py.cmd $($planArgs -join ' ')"
    & $OcPy @planArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Planner failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$Plan = Get-Content $PlanOut -Raw | ConvertFrom-Json
$TotalJobs = ($Plan.workers | ForEach-Object { $_.jobs.Count } | Measure-Object -Sum).Sum
$TotalSkipped = ($Plan.decisions | Where-Object { $_.action -eq "skip_valid" }).Count
$TotalRegen = ($Plan.decisions | Where-Object { $_.action -eq "regenerate_invalid" }).Count
$TotalMissing = ($Plan.decisions | Where-Object { $_.action -eq "generate_missing" }).Count

Write-Host "[run_l22_seed_shards] plan: $($Plan.processes.Count) processes x $($Plan.seeds.Count) seeds"
Write-Host "[run_l22_seed_shards]   skip_valid=$TotalSkipped generate_missing=$TotalMissing regenerate_invalid=$TotalRegen"
Write-Host "[run_l22_seed_shards]   $TotalJobs seed-jobs across $($Plan.workers.Count) workers"

if ($DryRun) {
    foreach ($w in $Plan.workers) {
        Write-Host "  worker $($w.worker_id): seeds = $(($w.jobs | ForEach-Object { $_.seed }) -join ',')"
    }
    Write-Host "[run_l22_seed_shards] -DryRun: no MATLAB process launched."
    return
}

if ($TotalJobs -eq 0) {
    Write-Host "[run_l22_seed_shards] nothing to do (every requested file already valid)."
    return
}

$RunState = [ordered]@{
    run_tag           = $RunTag
    started_at        = (Get-Date).ToUniversalTime().ToString("o")
    plan_path         = $PlanOutRel
    matlab_exe        = $MatlabExe
    n_workers         = $Workers
    processes         = $Plan.processes
    seeds             = $Plan.seeds
    n_ticks           = $NTicks
    workers           = @()
}

$ProcHandles = @()
foreach ($w in $Plan.workers) {
    if ($w.jobs.Count -eq 0) { continue }
    $combined = ($w.jobs | ForEach-Object { $_.matlab_command }) -join " "
    $workerLog = Join-Path $LogDir "worker$($w.worker_id)_$RunTag.stdout.log"
    $workerErr = Join-Path $LogDir "worker$($w.worker_id)_$RunTag.stderr.log"
    $pidFile = Join-Path $RepoRoot ".matlab_l22_${RunTag}_worker$($w.worker_id).pid"

    Write-Host "[run_l22_seed_shards] launching worker $($w.worker_id): seeds=$(($w.jobs | ForEach-Object { $_.seed }) -join ',') -> $workerLog"
    if ($combined -match '"') {
        throw "matlab_command for worker $($w.worker_id) contains a double-quote; the -batch value is wrapped in double quotes below and cannot safely contain one (got: $combined)"
    }
    # Start-Process -ArgumentList as an array does NOT quote elements containing
    # spaces before joining them into the child process's raw command line, so
    # MATLAB silently received only the substring up to the first space (e.g.
    # just "addpath('scripts/matlab');") and exited having done nothing -- no
    # error, no diary, no trace files. Passing one pre-quoted string instead
    # makes PowerShell hand the whole -batch value through as a single argument.
    $argString = "-batch `"$combined`""
    $proc = Start-Process -FilePath $MatlabExe `
        -ArgumentList $argString `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $workerLog `
        -RedirectStandardError $workerErr `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -Path $pidFile -Value $proc.Id
    $ProcHandles += $proc

    $RunState.workers += [ordered]@{
        worker_id   = $w.worker_id
        pid         = $proc.Id
        pid_file    = (Resolve-Path $pidFile -Relative)
        stdout_log  = (Resolve-Path $workerLog -Relative)
        stderr_log  = (Resolve-Path $workerErr -Relative)
        seeds       = @($w.jobs | ForEach-Object { $_.seed })
        per_seed_logs = @($w.jobs | ForEach-Object { @{ seed = $_.seed; log = $_.log_path } })
    }
}

$RunStatePath = Join-Path $ArtifactsDir "run_state_$RunTag.json"
$RunState | ConvertTo-Json -Depth 6 | Set-Content -Path $RunStatePath
Write-Host "[run_l22_seed_shards] run state written to $RunStatePath"

if ($NoWait) {
    Write-Host "[run_l22_seed_shards] -NoWait: workers launched detached. PIDs: $(($ProcHandles | ForEach-Object { $_.Id }) -join ', ')"
    Write-Host "[run_l22_seed_shards] poll with: Get-Process -Id <pid>; tail logs under $LogDir"
    return
}

Write-Host "[run_l22_seed_shards] waiting for $($ProcHandles.Count) worker process(es)..."
$ProcHandles | Wait-Process
$RunState.finished_at = (Get-Date).ToUniversalTime().ToString("o")
foreach ($entry in $RunState.workers) {
    $matching = $ProcHandles | Where-Object { $_.Id -eq $entry.pid } | Select-Object -First 1
    if ($matching) { $entry.exit_code = $matching.ExitCode }
}
$RunState | ConvertTo-Json -Depth 6 | Set-Content -Path $RunStatePath
Write-Host "[run_l22_seed_shards] all workers finished. Updated run state: $RunStatePath"
