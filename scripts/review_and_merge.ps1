# Review-and-merge helper for completed Codex sessions.
# Usage: pwsh -File scripts\review_and_merge.ps1 -Task pc-t3-supercoiling [-DryRun]
param(
    [Parameter(Mandatory=$true)][string]$Task,
    [switch]$DryRun
)

$wt = "E:\opencell-worktrees\$Task"
$branch = "agent/$Task"
$repo = "E:\opencell"

if (-not (Test-Path "$wt\STATUS.md")) { Write-Error "no STATUS.md for $Task"; exit 2 }

Write-Output "=== STATUS.md ===" 
Get-Content "$wt\STATUS.md" -Raw
Write-Output "`n=== commits on branch (vs main) ==="
& git -C $wt log --oneline main..HEAD

Write-Output "`n=== files changed ==="
& git -C $wt diff --stat main..HEAD

Write-Output "`n=== running targeted tests in worktree ==="
$testResult = wsl -e bash -lc "cd $($wt -replace '^E:','/mnt/e' -replace '\\','/') && /mnt/e/opencell/.venv-wsl/bin/pytest tests/vivarium -x -q 2>&1 | tail -20"
Write-Output $testResult

if ($DryRun) { Write-Output "`n[DryRun] skipping merge"; exit 0 }

Write-Output "`n=== running full suite in worktree (final gate) ==="
$full = wsl -e bash -lc "cd $($wt -replace '^E:','/mnt/e' -replace '\\','/') && /mnt/e/opencell/.venv-wsl/bin/pytest -x -q 2>&1 | tail -5"
Write-Output $full
if ($full -notmatch 'passed' -or $full -match 'failed') {
    Write-Error "Full suite did NOT pass clean; refusing to merge."
    exit 3
}

Write-Output "`n=== merging $branch into main ==="
Push-Location $repo
git fetch . "$branch`:$branch" 2>&1 | Out-Null
git merge --no-ff $branch -m "Merge $branch"
$mergeRc = $LASTEXITCODE
Pop-Location
if ($mergeRc -ne 0) { Write-Error "Merge failed (conflicts likely)"; exit 4 }
Write-Output "MERGED $Task -> main"
