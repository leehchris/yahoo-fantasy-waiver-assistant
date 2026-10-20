param(
    [Parameter(Mandatory=$true)][string]$PrivateRepoPath,
    [switch]$SkipRefresh
)
$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
if (!(Test-Path (Join-Path $project ".venv\Scripts\python.exe"))) { throw "Project virtual environment is missing." }
if (!(Test-Path (Join-Path $PrivateRepoPath ".git"))) { throw "PrivateRepoPath must point to a cloned, PRIVATE Git repository." }
$git = (Get-Command git -ErrorAction Stop).Source

# Require an explicit privacy check via GitHub CLI before writing ANY Yahoo data.
if (!(Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "Install free GitHub CLI (gh) and authenticate before using this publisher. This safeguard prevents public exposure."
}
Push-Location $PrivateRepoPath
try {
    $remote = (& $git remote get-url origin 2>&1)
    if ($LASTEXITCODE -ne 0 -or $remote -notmatch '(github\.com[:/])') { throw "Expected a GitHub origin remote." }
    $repo = (& gh repo view --json nameWithOwner,isPrivate | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or !$repo.isPrivate) { throw "Refusing to publish: repository is not confirmed PRIVATE." }
} finally { Pop-Location }

Push-Location $project
try {
    if (!$SkipRefresh) {
        & ".\.venv\Scripts\python.exe" -m yahoo_waiver_assistant refresh
        if ($LASTEXITCODE -ne 0) { throw "Yahoo refresh failed. Nothing published." }
    }
    $dir = Join-Path $project "data\private"
    $files = @(
        @{pattern="fantasy-update-*.md"; dest="latest-report.md"},
        @{pattern="fantasy-update-*.json"; dest="latest-report.json"}
    )
    $snapshot = Get-ChildItem $dir -Filter "snapshot-*.json" -File | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if ($null -eq $snapshot) { throw "No snapshot available" }
    $staging = Join-Path $PrivateRepoPath "yahoo"
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    & ".\.venv\Scripts\python.exe" -m yahoo_waiver_assistant.chatgpt_feed $snapshot.FullName (Join-Path $staging "latest-feed.json")
    if ($LASTEXITCODE -ne 0) { throw "Feed generation failed" }
    & ".\.venv\Scripts\python.exe" -m yahoo_waiver_assistant.chatgpt_shortlist $snapshot.FullName (Join-Path $staging "latest-shortlist.json")
    if ($LASTEXITCODE -ne 0) { throw "Shortlist generation failed" }
    foreach ($item in $files) {
        $latest = Get-ChildItem $dir -Filter $item.pattern -File |
          Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($null -ne $latest) {
            Copy-Item $latest.FullName (Join-Path $staging $item.dest) -Force
        }
    }
} finally { Pop-Location }
Push-Location $PrivateRepoPath
try {
    & $git add -- yahoo/latest-report.md yahoo/latest-report.json yahoo/latest-feed.json yahoo/latest-shortlist.json
    if ($LASTEXITCODE -ne 0) { throw "Git staging failed." }
    & $git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) { Write-Host "Already up to date."; exit 0 }
    & $git commit -m "Update private Yahoo fantasy data"
    if ($LASTEXITCODE -ne 0) { throw "Git commit failed." }
    & $git push
    if ($LASTEXITCODE -ne 0) { throw "Git push failed." }
    Write-Host "Private Yahoo data published."
} finally { Pop-Location }
