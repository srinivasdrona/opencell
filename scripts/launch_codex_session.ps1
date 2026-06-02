# scripts/launch_codex_session.ps1 — orchestrator helper
# Creates a worktree on agent/<name>, writes the prompt to <wt>/PROMPT.md,
# launches `codex exec` detached, captures stdout/stderr to <wt>/.codex_stdout.log.
# Each session writes STATUS.md when done.

param(
    [Parameter(Mandatory=$true)][string]$Name,    # e.g. "pc-t2-replication"
    [Parameter(Mandatory=$true)][string]$Prompt,  # full prompt text
    [string]$RepoMain = "E:\opencell",
    [string]$WorktreeRoot = "E:\opencell-worktrees"
)

if (-not $env:AZURE_OPENAI_API_KEY) {
    $env:AZURE_OPENAI_API_KEY = [Environment]::GetEnvironmentVariable('AZURE_OPENAI_API_KEY','User')
}
if (-not $env:AZURE_OPENAI_API_KEY) { throw "AZURE_OPENAI_API_KEY not set" }

$wt = Join-Path $WorktreeRoot $Name
$branch = "agent/$Name"

# Create worktree if it doesn't already exist
if (-not (Test-Path $wt)) {
    Push-Location $RepoMain
    git worktree add -b $branch $wt main 2>&1 | Out-Null
    Pop-Location
}

# Fresh STATUS / PROMPT so we never inherit stale content
Remove-Item "$wt\STATUS.md" -ErrorAction SilentlyContinue
$Prompt | Out-File "$wt\PROMPT.md" -Encoding utf8 -Force

# Launch detached; stdout/stderr → .codex_stdout.log; STATUS.md → -o
$logPath = "$wt\.codex_stdout.log"
Remove-Item $logPath -ErrorAction SilentlyContinue

$pinfo = New-Object System.Diagnostics.ProcessStartInfo
$pinfo.FileName = "codex"
$pinfo.Arguments = "exec --dangerously-bypass-approvals-and-sandbox -C `"$wt`" -o `"$wt\STATUS.md`" `"$(($Prompt -replace '"', '\"'))`""
$pinfo.RedirectStandardOutput = $true
$pinfo.RedirectStandardError = $true
$pinfo.UseShellExecute = $false
$pinfo.CreateNoWindow = $true

# Simpler: read prompt from file via "@PROMPT.md"? codex exec doesn't support file-prompt
# So we pass prompt as one argument. Using stdin would be cleaner but stick with arg for now.
# For robustness, use Start-Process with output redirection instead.
$proc = Start-Process -FilePath "codex" `
    -ArgumentList @("exec","--dangerously-bypass-approvals-and-sandbox","-C",$wt,"-o","$wt\STATUS.md",$Prompt) `
    -NoNewWindow -PassThru -RedirectStandardOutput $logPath -RedirectStandardError "$wt\.codex_stderr.log"

Write-Output "LAUNCHED: $Name | PID=$($proc.Id) | wt=$wt"
"$($proc.Id)" | Out-File "$wt\.codex_pid" -Encoding ascii
