[CmdletBinding()]
param(
    [string]$SchemaPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Get-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDir "..\..")).Path
}

function Test-CommandAvailable {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function New-DirectoryIfMissing {
    [CmdletBinding(SupportsShouldProcess)]
    param([string]$Path)

    if ($PSCmdlet.ShouldProcess($Path, "Create directory")) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

Test-CommandAvailable -Name "uv"

$repoRoot = Get-RepoRoot
if ([string]::IsNullOrWhiteSpace($SchemaPath)) {
    $SchemaPath = Join-Path $repoRoot ".tmp\napcat-schema\ob11-all-event.schema.json"
}
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $repoRoot ".tmp\napcat-schema\ob11-all-event.normalized.schema.json"
}

$SchemaPath = [System.IO.Path]::GetFullPath($SchemaPath)
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

if (-not (Test-Path -LiteralPath $SchemaPath)) {
    throw "Schema file not found: $SchemaPath"
}

New-DirectoryIfMissing -Path (Split-Path -Parent $OutputPath)

& uv run python (Join-Path $repoRoot "scripts\napcat\normalize_ob11_event_schema.py") `
    --input $SchemaPath `
    --output $OutputPath
if ($LASTEXITCODE -ne 0) {
    throw "normalize_ob11_event_schema.py failed for $SchemaPath"
}

if (-not (Test-Path -LiteralPath $OutputPath)) {
    throw "Normalized schema file was not created: $OutputPath"
}

try {
    $rawJson = [System.IO.File]::ReadAllText($OutputPath, [System.Text.Encoding]::UTF8)
    $null = $rawJson | ConvertFrom-Json
}
catch {
    throw "Normalized schema is not valid JSON: $OutputPath"
}

Write-Output "Generated normalized schema:"
Write-Output "  $OutputPath"
