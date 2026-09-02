#!/usr/bin/env pwsh
[CmdletBinding()]
param(
  [string]$OutputRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
  throw "Python 3.9 or newer is required to package the Skills."
}

$scriptPath = Join-Path $PSScriptRoot "package_skills.py"
$arguments = @($scriptPath)
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
  $arguments += @("--output", $OutputRoot)
}

& $python.Source @arguments
exit $LASTEXITCODE
