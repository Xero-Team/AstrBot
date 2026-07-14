[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repoRoot = (git rev-parse --show-toplevel).Trim()
if (-not $repoRoot) {
    throw 'Unable to determine the Git repository root.'
}

Push-Location $repoRoot
try {
    $changedFiles = [System.Collections.Generic.List[string]]::new()
    foreach ($entry in git ls-files --eol) {
        $parts = $entry -split "`t", 2
        if ($parts.Count -ne 2 -or $parts[0] -notmatch 'attr/text(?:=auto)?') {
            continue
        }

        $path = Join-Path $repoRoot $parts[1]
        $bytes = [System.IO.File]::ReadAllBytes($path)
        if (-not ($bytes -contains [byte]13)) {
            continue
        }

        $normalized = [System.Collections.Generic.List[byte]]::new($bytes.Length)
        for ($index = 0; $index -lt $bytes.Length; $index += 1) {
            if ($bytes[$index] -eq 13) {
                $normalized.Add(10)
                if ($index + 1 -lt $bytes.Length -and $bytes[$index + 1] -eq 10) {
                    $index += 1
                }
                continue
            }
            $normalized.Add($bytes[$index])
        }

        [System.IO.File]::WriteAllBytes($path, $normalized.ToArray())
        $changedFiles.Add($parts[1])
    }

    if ($changedFiles.Count -eq 0) {
        Write-Host 'All tracked text files already use LF.'
        return
    }

    Write-Host "Normalized $($changedFiles.Count) tracked text file(s) to LF:"
    $changedFiles | ForEach-Object { Write-Host "  $_" }
} finally {
    Pop-Location
}
