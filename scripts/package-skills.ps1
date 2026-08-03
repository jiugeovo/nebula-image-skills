#!/usr/bin/env pwsh
[CmdletBinding()]
param(
  [string]$OutputRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$defaultOutputRoot = Join-Path $projectRoot "dist\skills"
$effectiveOutputRoot = if ([string]::IsNullOrWhiteSpace($OutputRoot)) { $defaultOutputRoot } else { $OutputRoot }
$skillNames = @(
  "nebula-image2-1k",
  "nebula-image2-4k",
  "nebula-nanobanana",
  "nebula-grok"
)

$resolvedOutputRoot = [IO.Path]::GetFullPath($effectiveOutputRoot)
New-Item -ItemType Directory -Force -Path $resolvedOutputRoot | Out-Null

$stageRoot = Join-Path ([IO.Path]::GetTempPath()) ("jiuge-canva-skills-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

try {
  $hashLines = [Collections.Generic.List[string]]::new()

  foreach ($skillName in $skillNames) {
    $source = Join-Path $projectRoot "skills\$skillName"
    $required = @(
      (Join-Path $source "SKILL.md"),
      (Join-Path $source "agents\openai.yaml"),
      (Join-Path $source "scripts\config.json"),
      (Join-Path $source "scripts\generate_image.py")
    )
    foreach ($path in $required) {
      if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required Skill file: $path"
      }
    }

    $stagedSkill = Join-Path $stageRoot $skillName
    New-Item -ItemType Directory -Force -Path $stagedSkill | Out-Null
    Copy-Item -LiteralPath (Join-Path $source "SKILL.md") -Destination $stagedSkill
    Copy-Item -LiteralPath (Join-Path $source "agents") -Destination $stagedSkill -Recurse
    $stagedScripts = Join-Path $stagedSkill "scripts"
    New-Item -ItemType Directory -Force -Path $stagedScripts | Out-Null
    Copy-Item -LiteralPath (Join-Path $source "scripts\config.json") -Destination $stagedScripts
    Copy-Item -LiteralPath (Join-Path $source "scripts\generate_image.py") -Destination $stagedScripts

    $archive = Join-Path $resolvedOutputRoot "$skillName.zip"
    if (Test-Path -LiteralPath $archive -PathType Leaf) {
      Remove-Item -LiteralPath $archive -Force
    }
    Compress-Archive -LiteralPath $stagedSkill -DestinationPath $archive -CompressionLevel Optimal

    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $hashLines.Add("$hash  $skillName.zip")
    Write-Output ("PACKED {0} {1} bytes SHA256 {2}" -f $skillName, (Get-Item -LiteralPath $archive).Length, $hash)
  }

  $checksums = Join-Path $resolvedOutputRoot "SHA256SUMS.txt"
  if (Test-Path -LiteralPath $checksums -PathType Leaf) {
    Remove-Item -LiteralPath $checksums -Force
  }
  Set-Content -LiteralPath $checksums -Value $hashLines -Encoding ASCII
  Write-Output "WROTE $checksums"
}
finally {
  if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
  }
}
