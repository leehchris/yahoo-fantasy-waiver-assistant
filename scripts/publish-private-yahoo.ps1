param([string]$PrivateRepoPath, [string]$PythonPath, [string]$Repository = 'leehchris/yahoo-fantasy-private-data')
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
if (!$PythonPath) { $PythonPath = Join-Path $project '.venv\Scripts\python.exe' }
if (!(Test-Path -LiteralPath $PythonPath)) { throw 'Project Python environment is missing.' }
# Retain PrivateRepoPath for compatibility; publish all files in one GitHub commit.
Push-Location $project
try {
    $env:PYTHONPATH = Join-Path $project 'src'
    & $PythonPath -m yahoo_waiver_assistant.sync --repository $Repository
    if ($LASTEXITCODE -ne 0) { throw 'Yahoo synchronization failed; previous capture preserved.' }
} finally { Pop-Location }
