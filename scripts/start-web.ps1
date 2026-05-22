param(
  [int]$Port = 8010,
  [string]$HostAddress = "127.0.0.1",
  [switch]$InstallDeps,
  [switch]$NoBuild,
  [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "== Personal Ops Workbench =="
Write-Host "Project: $Root"
$Url = "http://${HostAddress}:${Port}"

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$CreatedVenv = $false
if (-not (Test-Path $VenvPython)) {
  Write-Host "Creating Python virtual environment..."
  python -m venv .venv
  $CreatedVenv = $true
}

if ($CreatedVenv -or $InstallDeps) {
  Write-Host "Installing Python dependencies..."
  & $VenvPython -m pip install -r requirements.txt
}

if (-not (Test-Path (Join-Path $Root "node_modules"))) {
  Write-Host "Installing frontend dependencies..."
  npm ci
}

if (-not $NoBuild) {
  Write-Host "Building web UI..."
  $env:VITE_API_BASE = $Url
  npm run build
}

if (-not $NoOpen) {
  Start-Process $Url
}

Write-Host ""
Write-Host "Web tool is starting at $Url"
Write-Host "Press Ctrl+C in this window to stop it."
Write-Host ""

& $VenvPython -m uvicorn backend.app.main:app --host $HostAddress --port $Port
