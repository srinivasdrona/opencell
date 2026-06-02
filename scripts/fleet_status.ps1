# Aggregate health snapshot across all in-flight Codex worktrees
$root = "E:\opencell-worktrees"
$tasks = Get-ChildItem $root -Directory | Where-Object { $_.Name -match '^(pc-|pd-|pe-)' }

"{0,-34} {1,-9} {2,-8} {3,-9} {4,-9} {5,-9} {6}" -f "task","alive","status","stdout","stderr","commits","head_age" | Write-Output
"-" * 110 | Write-Output

foreach ($t in $tasks) {
    $wt = $t.FullName
    $name = $t.Name
    $pidPath = Join-Path $wt ".codex_pid"
    $alive = "?"
    if (Test-Path $pidPath) {
        $pid_v = (Get-Content $pidPath).Trim()
        try { $null = Get-Process -Id $pid_v -ErrorAction Stop; $alive = "RUN" } catch { $alive = "exit" }
    }
    $statusSize = if (Test-Path "$wt\STATUS.md") { (Get-Item "$wt\STATUS.md").Length } else { 0 }
    $outSize = if (Test-Path "$wt\.codex_stdout.log") { (Get-Item "$wt\.codex_stdout.log").Length } else { 0 }
    $errSize = if (Test-Path "$wt\.codex_stderr.log") { (Get-Item "$wt\.codex_stderr.log").Length } else { 0 }
    $commits = (& git -C $wt rev-list --count HEAD '^main' 2>$null)
    if (-not $commits) { $commits = "0" }
    $headTime = (& git -C $wt log -1 --format=%ct 2>$null)
    $age = if ($headTime) { [math]::Round(([DateTimeOffset]::Now.ToUnixTimeSeconds() - [int]$headTime)/60, 1) } else { "?" }
    "{0,-34} {1,-9} {2,-8} {3,-9} {4,-9} {5,-9} {6}min" -f $name, $alive, $statusSize, $outSize, $errSize, $commits, $age | Write-Output
}
