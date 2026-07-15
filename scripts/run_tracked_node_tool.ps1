param(
  [Parameter(Mandatory = $true)]
  [string]$Tool,

  [Parameter(Mandatory = $true)]
  [string[]]$Patterns,

  [string]$ToolArgs = '',

  [int]$BatchSize = 64
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$files = @(git ls-files -- @Patterns | Where-Object { $_ })
if ($files.Count -eq 0) {
  exit 0
}

$extraArgs = @()
if ($ToolArgs) {
  $extraArgs = @($ToolArgs -split ';' | Where-Object { $_ })
}

for ($index = 0; $index -lt $files.Count; $index += $BatchSize) {
  $end = [Math]::Min($index + $BatchSize - 1, $files.Count - 1)
  $batch = $files[$index..$end]
  & corepack npm exec --no -- $Tool @extraArgs @batch
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}
