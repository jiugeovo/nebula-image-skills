param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Arguments
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $scriptRoot "scripts\generate_image.py"

function Find-CodexPython {
    $runtimeRoot = Join-Path $env:USERPROFILE ".cache\codex-runtimes"
    if (-not (Test-Path -LiteralPath $runtimeRoot -PathType Container)) {
        return $null
    }

    $runtimes = Get-ChildItem -LiteralPath $runtimeRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    foreach ($runtime in $runtimes) {
        $candidate = Join-Path $runtime.FullName "dependencies\python\python.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

$python = Find-CodexPython
if (-not $python) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        $python = $command.Source
    }
}
if (-not $python) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $python = $launcher.Source
        $Arguments = @("$script") + $Arguments
    }
}

if (-not $python) {
    Write-Error @"
Cannot find Python.
Install Python 3.9+ for standalone terminal use, or run this Skill from Codex Desktop with its bundled Python runtime.
"@
    exit 1
}

if ($Arguments -and $Arguments[0] -eq "$script") {
    & $python @Arguments
} else {
    & $python "$script" @Arguments
}
$exitCode = $LASTEXITCODE
if ($null -eq $exitCode) {
    $exitCode = 0
}
exit $exitCode
