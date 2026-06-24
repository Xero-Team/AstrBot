param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("run-backend", "run-dashboard", "stop-backend", "stop-dashboard", "status", "clean")]
    [string]$Action
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $repoRoot ".make"
$dashboardDir = Join-Path $repoRoot "dashboard"
$backendPidFile = Join-Path $runDir "backend.pid"
$dashboardPidFile = Join-Path $runDir "dashboard.pid"
$backendLog = Join-Path $repoRoot "backend_run.log"
$backendErrLog = Join-Path $repoRoot "backend_run.err.log"
$dashboardLog = Join-Path $repoRoot "frontend_run.log"
$dashboardErrLog = Join-Path $repoRoot "frontend_run.err.log"
$dashboardDist = Join-Path $dashboardDir "dist"
$dashboardViteCache = Join-Path $dashboardDir "node_modules/.vite"

function Ensure-RunDir {
    if (-not (Test-Path $runDir)) {
        New-Item -ItemType Directory -Path $runDir | Out-Null
    }
}

function Remove-IfExists {
    param([string]$Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function New-EmptyFile {
    param([string]$Path)

    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }
    Set-Content -Path $Path -Value "" -NoNewline
}

function Stop-FromPidFile {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) {
        return
    }

    $pidValue = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pidValue) {
        & taskkill /PID $pidValue /T /F *> $null
    }
    Remove-IfExists $PidFile
}

function Stop-ByPort {
    param([int]$Port)

    $pids = @()
    try {
        $pids += Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
    }
    catch {
        $netstatLines = netstat -ano -p tcp | Select-String ":$Port "
        foreach ($line in $netstatLines) {
            $parts = ($line.Line -split "\s+") | Where-Object { $_ }
            if ($parts.Length -ge 5 -and $parts[3] -eq "LISTENING") {
                $pids += $parts[4]
            }
        }
    }

    $pids = $pids | Where-Object { $_ } | Select-Object -Unique
    foreach ($procId in $pids) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
        }
        catch {
            & taskkill /PID $procId /T /F *> $null
        }
    }
}

function Start-ManagedProcess {
    param(
        [string]$PidFile,
        [string]$WorkingDirectory,
        [string]$Command,
        [string]$StdoutPath,
        [string]$StderrPath,
        [int]$WarmupSeconds
    )

    Ensure-RunDir
    Stop-FromPidFile -PidFile $PidFile
    Remove-IfExists $StdoutPath
    Remove-IfExists $StderrPath
    New-EmptyFile -Path $StdoutPath
    New-EmptyFile -Path $StderrPath

    $proc = Start-Process `
        -FilePath "powershell" `
        -ArgumentList @("-NoProfile", "-Command", $Command) `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -Path $PidFile -Value $proc.Id
    Start-Sleep -Seconds $WarmupSeconds
}

function Test-Url {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing $Url -Method Head -TimeoutSec 10
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        try {
            $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 10
            return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
        }
        catch {
            return $false
        }
    }
}

switch ($Action) {
    "run-backend" {
        Start-ManagedProcess `
            -PidFile $backendPidFile `
            -WorkingDirectory $repoRoot `
            -Command "Set-Location '$repoRoot'; uv run main.py" `
            -StdoutPath $backendLog `
            -StderrPath $backendErrLog `
            -WarmupSeconds 6
    }
    "run-dashboard" {
        Start-ManagedProcess `
            -PidFile $dashboardPidFile `
            -WorkingDirectory $dashboardDir `
            -Command "Set-Location '$dashboardDir'; npm exec --yes pnpm@10 -- dev" `
            -StdoutPath $dashboardLog `
            -StderrPath $dashboardErrLog `
            -WarmupSeconds 8
    }
    "stop-backend" {
        Stop-FromPidFile -PidFile $backendPidFile
        Stop-ByPort -Port 6185
        Remove-IfExists $backendPidFile
    }
    "stop-dashboard" {
        Stop-FromPidFile -PidFile $dashboardPidFile
        Stop-ByPort -Port 3000
        Remove-IfExists $dashboardPidFile
    }
    "status" {
        $backendOk = Test-Url -Url "http://127.0.0.1:6185/api/v1/openapi.json"
        $dashboardOk = Test-Url -Url "http://127.0.0.1:3000"

        Write-Host "Backend  : $(Split-Path -Leaf $backendPidFile) -> $(if ($backendOk) { 'up' } else { 'down' })"
        Write-Host "Dashboard: $(Split-Path -Leaf $dashboardPidFile) -> $(if ($dashboardOk) { 'up' } else { 'down' })"

        if (-not $backendOk -or -not $dashboardOk) {
            exit 1
        }
    }
    "clean" {
        Stop-FromPidFile -PidFile $dashboardPidFile
        Stop-FromPidFile -PidFile $backendPidFile
        Stop-ByPort -Port 3000
        Stop-ByPort -Port 6185
        Remove-IfExists $runDir
        Remove-IfExists $backendLog
        Remove-IfExists $backendErrLog
        Remove-IfExists $dashboardLog
        Remove-IfExists $dashboardErrLog
        Remove-IfExists $dashboardDist
        Remove-IfExists $dashboardViteCache
    }
}
