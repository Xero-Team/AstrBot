<#
.SYNOPSIS
  Lint or format PowerShell scripts with PSScriptAnalyzer.
  Driven by `make check-ps` / `make format-ps`.
.PARAMETER Fix
  Format files in place with Invoke-Formatter instead of linting.
#>
param(
    [switch]$Fix,
    [switch]$Require
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Module -ListAvailable PSScriptAnalyzer)) {
    if ($Require) {
        throw 'PSScriptAnalyzer is required. Install it with: Install-Module PSScriptAnalyzer -Scope CurrentUser'
    }
    Write-Host '==> [ps] PSScriptAnalyzer not installed, skipping'
    exit 0
}

$settings = Join-Path (Split-Path -Parent $PSScriptRoot) 'PSScriptAnalyzerSettings.psd1'
$files = @(git ls-files '*.ps1' | Where-Object {
        Test-Path -LiteralPath $_ -PathType Leaf
    })

if (-not $files) {
    Write-Host '==> [ps] no PowerShell files'
    exit 0
}

if ($Fix) {
    foreach ($p in $files) {
        $orig = Get-Content -Raw $p
        $fmt = Invoke-Formatter -ScriptDefinition $orig -Settings $settings
        if ($fmt -ne $orig) {
            Set-Content -Path $p -Value $fmt -NoNewline
            Write-Host "formatted: $p"
        }
    }
    exit 0
}

$findings = foreach ($p in $files) {
    Invoke-ScriptAnalyzer -Path $p -Settings $settings
}

if ($findings) {
    $findings | Format-Table RuleName, Severity, ScriptName, Line, Message -AutoSize | Out-String -Width 200 | Write-Host
    exit 1
}

Write-Host 'ok'
