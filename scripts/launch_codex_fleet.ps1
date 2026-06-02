# Launches all PROMPT.md files in each worktree as detached codex sessions
# (piping prompt via stdin to dodge Windows .cmd arg quoting).
param([string[]]$Only)

$env:AZURE_OPENAI_API_KEY = [Environment]::GetEnvironmentVariable('AZURE_OPENAI_API_KEY','User')
if (-not $env:AZURE_OPENAI_API_KEY) { throw "AZURE_OPENAI_API_KEY missing in User env" }

$codex = "C:\Users\sdrona\AppData\Roaming\npm\codex.cmd"
$root = "E:\opencell-worktrees"

$tasks = @(
    "pc-t2-replication","pc-t3-supercoiling","pc-t4-condensation","pc-t5-segregation",
    "pc-t6-damage","pc-t7-repair","pc-t8-ftsz","pc-t9-cytokinesis",
    "pc-t10-terminal-organelle","pd-t1-host-interaction","pe-1-trajectory-scaffold"
)

foreach ($t in $tasks) {
    if ($Only -and $Only -notcontains $t) { continue }
    $wt = Join-Path $root $t
    if (-not (Test-Path "$wt\PROMPT.md")) { Write-Warning "no PROMPT.md in $t"; continue }
    # Fresh STATUS / logs
    Remove-Item "$wt\STATUS.md","$wt\.codex_stdout.log","$wt\.codex_stderr.log" -ErrorAction SilentlyContinue
    # cmd /c "type PROMPT.md | codex exec ... -  >stdout 2>stderr"
    $inner = "type `"$wt\PROMPT.md`" | `"$codex`" exec --dangerously-bypass-approvals-and-sandbox -C `"$wt`" -o `"$wt\STATUS.md`" - 1> `"$wt\.codex_stdout.log`" 2> `"$wt\.codex_stderr.log`""
    $p = Start-Process -FilePath cmd.exe -ArgumentList "/c", $inner -WindowStyle Hidden -PassThru
    "$($p.Id)" | Out-File "$wt\.codex_pid" -Encoding ascii -Force
    Write-Output ("LAUNCHED {0,-32} pid={1}" -f $t, $p.Id)
}
Write-Output "All sessions dispatched."
