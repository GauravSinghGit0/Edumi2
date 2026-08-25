# ==============================================================================
# EduMi2 — One-Click Enterprise PowerShell Startup Manager
# ==============================================================================
# Features:
#   1. Kills previous processes on ports 8002, 8003, 8008, 7880, 7881, 7882
#   2. Launches all microservices silently in 1 single terminal (no 3 extra windows!)
#   3. Cleans up all background processes automatically when stopped
#   4. Verifies each background service is actually running before continuing
# ==============================================================================

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "          EduMi 2 - Unified Enterprise Launcher" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""

function Test-TcpPort {
    param([int]$Port, [string]$Hostname = "127.0.0.1", [int]$TimeoutMs = 200)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($Hostname, $Port, $null, $null)
        $wait = $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($wait -and $client.Connected) { $client.Close(); return $true }
        $client.Close(); return $false
    } catch { return $false }
}

function Wait-ForPort {
    param([int]$Port, [int]$MaxSeconds = 15, [string]$ServiceName = "service")
    $end = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $end) {
        if (Test-TcpPort -Port $Port) { return $true }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

function Start-BackgroundProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$LogFile,
        [string]$ServiceName,
        [int]$VerifyPort = 0,
        [int]$VerifyWaitSec = 12
    )
    $baseName  = [System.IO.Path]::GetFileNameWithoutExtension($LogFile)
    $outDir    = [System.IO.Path]::GetDirectoryName($LogFile)
    $stdOutLog = Join-Path $outDir ("{0}.stdout.log" -f $baseName)
    $stdErrLog = Join-Path $outDir ("{0}.stderr.log" -f $baseName)
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

    try {
        $spArgs = @{
            FilePath               = $FilePath
            ArgumentList           = $ArgumentList
            RedirectStandardOutput = $stdOutLog
            RedirectStandardError  = $stdErrLog
            WindowStyle            = "Hidden"
            PassThru               = $true
            ErrorAction            = "Stop"
        }
        $proc = Start-Process @spArgs
    } catch {
        Write-Host ("  -> [FAIL] {0} failed to launch: {1}" -f $ServiceName, $_) -ForegroundColor Red
        Write-Host ("     Stdout log: {0}" -f $stdOutLog) -ForegroundColor DarkGray
        Write-Host ("     Stderr log: {0}" -f $stdErrLog) -ForegroundColor DarkGray
        return $null
    }

    Start-Sleep -Milliseconds 800
    if ($proc.HasExited) {
        Write-Host ("  -> [FAIL] {0} exited immediately (exit code {1})." -f $ServiceName, $proc.ExitCode) -ForegroundColor Red
        Write-Host ("     Combined stdout+stderr (see full logs at {0} / {1}):" -f $stdOutLog, $stdErrLog) -ForegroundColor DarkGray
        $merged = @()
        if (Test-Path $stdOutLog) { $merged += Get-Content $stdOutLog -Tail 40 }
        if (Test-Path $stdErrLog) { $merged += Get-Content $stdErrLog -Tail 40 }
        if ($merged.Count -eq 0) { $merged += "(no log output yet - process crashed before writing anything)" }
        foreach ($line in $merged) { Write-Host ("     | {0}" -f $line) -ForegroundColor DarkGray }
        return $null
    }

    if ($VerifyPort -gt 0) {
        if (Wait-ForPort -Port $VerifyPort -MaxSeconds $VerifyWaitSec -ServiceName $ServiceName) {
            Write-Host ("  -> [OK] {0} started (PID: {1}, Port {2})" -f $ServiceName, $proc.Id, $VerifyPort) -ForegroundColor Green
            Write-Host ("     Logs: {0} (stdout) | {1} (stderr)" -f $stdOutLog, $stdErrLog) -ForegroundColor DarkGray
        } else {
            Write-Host ("  -> [WARN] {0} PID {1} alive but port {2} not open after {3}s." -f $ServiceName, $proc.Id, $VerifyPort, $VerifyWaitSec) -ForegroundColor Yellow
            Write-Host ("     Tail of stderr ({0}):" -f $stdErrLog) -ForegroundColor DarkGray
            if (Test-Path $stdErrLog) {
                foreach ($line in (Get-Content $stdErrLog -Tail 15)) { Write-Host ("     | {0}" -f $line) -ForegroundColor DarkGray }
            } else {
                Write-Host "     | (no stderr log yet)" -ForegroundColor DarkGray
            }
            Write-Host ("     Tail of stdout ({0}):" -f $stdOutLog) -ForegroundColor DarkGray
            if (Test-Path $stdOutLog) {
                foreach ($line in (Get-Content $stdOutLog -Tail 10)) { Write-Host ("     | {0}" -f $line) -ForegroundColor DarkGray }
            } else {
                Write-Host "     | (no stdout log yet)" -ForegroundColor DarkGray
            }
        }
    } else {
        Write-Host ("  -> [OK] {0} started (PID: {1})" -f $ServiceName, $proc.Id) -ForegroundColor Green
        Write-Host ("     Logs: {0} (stdout) | {1} (stderr)" -f $stdOutLog, $stdErrLog) -ForegroundColor DarkGray
    }
    return $proc
}

# ------------------------------------------------------------------------------
# STEP 1: Process & Port Cleanup (Kill Stale Processes)
# ------------------------------------------------------------------------------
Write-Host "[1/6] Cleaning up previous processes & releasing ports..." -ForegroundColor Yellow

$TargetPorts = @(8002, 8003, 8008, 7880, 7881, 7882)
foreach ($Port in $TargetPorts) {
    $Connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($Connections) {
        foreach ($Conn in $Connections) {
            $PidToKill = $Conn.OwningProcess
            if ($PidToKill -gt 0 -and $PidToKill -ne $PID) {
                Write-Host "  -> Releasing port $Port (PID: $PidToKill)" -ForegroundColor Gray
                Stop-Process -Id $PidToKill -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

Get-Process -Name "livekit-server" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name "celery" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Write-Host "  -> Ports and processes cleaned up cleanly." -ForegroundColor Green


# ------------------------------------------------------------------------------
# STEP 2: Environment Check & Log Directory Setup
# ------------------------------------------------------------------------------
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "[ERROR] Virtual environment not found in .\venv" -ForegroundColor Red
    Write-Host "Please create it using: python -m venv venv" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$LogsDir    = Join-Path $ScriptDir "logs"
if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null }

if (-not (Test-Path ".env")) {
    Write-Host "[INFO] Creating .env from config\.env.example..." -ForegroundColor Cyan
    Copy-Item "config\.env.example" ".env" -Force
}


# ------------------------------------------------------------------------------
# STEP 2b: Ensure LiveKit config has correct bind + STUN for Windows
# ------------------------------------------------------------------------------
$LkExePath    = Join-Path $ScriptDir "livekit-bin\livekit-server.exe"
$LkConfigPath = Join-Path $ScriptDir "config\livekit.yaml"
if ((Test-Path $LkExePath) -and (Test-Path $LkConfigPath)) {
    $lkYaml = Get-Content $LkConfigPath -Raw
    $needsUpdate = $false
    if ($lkYaml -notmatch 'rtc:') { $needsUpdate = $true }
    if ($lkYaml -notmatch 'stun.l.google.com') { $needsUpdate = $true }
    if ($lkYaml -match 'node_ip:\s*"127\.0\.0\.1"') { $needsUpdate = $true }
    if ($needsUpdate) {
        try {
            $LK_KEY    = "devkey"
            $LK_SECRET = "devsecret_must_be_32_characters_long_1234"
            if (Test-Path ".env") {
                $envContent = Get-Content ".env" -Raw
                if ($envContent -match 'LIVEKIT_API_KEY=([^\r\n]+)') { $LK_KEY = $Matches[1].Trim('"').Trim("'") }
                if ($envContent -match 'LIVEKIT_API_SECRET=([^\r\n]+)') { $LK_SECRET = $Matches[1].Trim('"').Trim("'") }
            }
            $LAN_IP = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1 -ExpandProperty IPv4Address | Select-Object -First 1 -ExpandProperty IPAddress)
            if (-not $LAN_IP) { $LAN_IP = "127.0.0.1" }

            # Use a SINGLE-QUOTED here-string (@' ... '@) so PowerShell does NOT try
            # to parse '$LK_KEY: $LK_SECRET' as a $Drive:Variable reference.
            $newYamlTpl = @'
# ==============================================================================
# LiveKit SFU Server Configuration (Windows - auto-updated by start_app.ps1)
# ==============================================================================
port: 7880
bind_addresses:
  - "0.0.0.0"

rtc:
  tcp_port: 7881
  udp_port: 7882
  use_external_ip: true
  node_ip: "__LAN_IP__"
  stun_servers:
    - "stun.l.google.com:19302"
    - "stun1.l.google.com:19302"

keys:
  __LK_KEY_LINE__

room:
  empty_timeout: 300
  max_participants: 100

logging:
  level: info
'@
            $lkKeyLine = '  {0}: {1}' -f $LK_KEY, $LK_SECRET
            $newYaml = $newYamlTpl.Replace('__LK_KEY_LINE__', $lkKeyLine).Replace('__LAN_IP__', $LAN_IP)
            Set-Content -Path $LkConfigPath -Value $newYaml -Encoding UTF8
            Write-Host ("  -> LiveKit config updated (bind=0.0.0.0, STUN enabled, LAN IP={0})" -f $LAN_IP) -ForegroundColor Gray
        } catch {
            Write-Host "  -> [WARN] Could not auto-update livekit.yaml: $_" -ForegroundColor Yellow
        }
    }
}


# ------------------------------------------------------------------------------
# STEP 2: Database Migrations
# ------------------------------------------------------------------------------
Write-Host "[2/6] Running Database Migrations..." -ForegroundColor Yellow
& $VenvPython manage.py migrate --noinput
if ($LASTEXITCODE -eq 0) {
    Write-Host "  -> Database schema is up to date." -ForegroundColor Green
} else {
    Write-Host "  -> [WARN] Migrations exited with code $LASTEXITCODE (continuing anyway)" -ForegroundColor Yellow
}


# ------------------------------------------------------------------------------
# STEP 3: Build Static Assets (collectstatic + django-compressor offline)
# ------------------------------------------------------------------------------
Write-Host "[3/6] Building static assets & compressing CSS/JS..." -ForegroundColor Yellow

& $VenvPython manage.py collectstatic --noinput
if ($LASTEXITCODE -ne 0) {
    Write-Host "  -> [WARN] collectstatic exited with code $LASTEXITCODE (continuing)" -ForegroundColor Yellow
} else {
    Write-Host "  -> Static files collected successfully." -ForegroundColor Green
}

& $VenvPython manage.py compress --force
if ($LASTEXITCODE -ne 0) {
    Write-Host "  -> [WARN] compress exited with code $LASTEXITCODE (continuing)" -ForegroundColor Yellow
} else {
    Write-Host "  -> CSS/JS bundles compressed successfully." -ForegroundColor Green
}


# ------------------------------------------------------------------------------
# STEP 4: Launch Microservices Silently (No Extra Windows)
# ------------------------------------------------------------------------------
Write-Host "[4/6] Starting Background Services (LiveKit, Camera, Celery)..." -ForegroundColor Yellow

$BGProcesses = New-Object System.Collections.ArrayList

if (Test-Path $LkExePath) {
    $LkLog = Join-Path $LogsDir "livekit.log"
    $LkArgs = @("--config", $LkConfigPath)
    if ($LAN_IP -and $LAN_IP -ne "127.0.0.1") {
        $LkArgs += @("--node-ip", $LAN_IP)
    }
    $LkProc = Start-BackgroundProcess `
        -FilePath    $LkExePath `
        -ArgumentList $LkArgs `
        -LogFile     $LkLog `
        -ServiceName "LiveKit SFU Server" `
        -VerifyPort  7880
    if ($LkProc) { [void]$BGProcesses.Add($LkProc) }
} else {
    Write-Host "  -> [SKIP] livekit-server.exe not found at $LkExePath" -ForegroundColor DarkYellow
    Write-Host "     Download it from: https://github.com/livekit/livekit/releases" -ForegroundColor DarkYellow
}

if (Test-Path "camera_service\serve.py") {
    $CamLog = Join-Path $LogsDir "camera_service.log"
    $CamProc = Start-BackgroundProcess `
        -FilePath    $VenvPython `
        -ArgumentList @("camera_service/serve.py") `
        -LogFile     $CamLog `
        -ServiceName "Camera Microservice" `
        -VerifyPort  8008
    if ($CamProc) { [void]$BGProcesses.Add($CamProc) }
} else {
    Write-Host "  -> [SKIP] camera_service/serve.py not found" -ForegroundColor DarkYellow
}

$CeleryLog = Join-Path $LogsDir "celery.log"
$CeleryProc = Start-BackgroundProcess `
    -FilePath    $VenvPython `
    -ArgumentList @("-m", "celery", "-A", "school_project", "worker", "-l", "info", "-P", "threads") `
    -LogFile     $CeleryLog `
    -ServiceName "Celery Task Worker" `
    -VerifyPort  0
if ($CeleryProc) { [void]$BGProcesses.Add($CeleryProc) }


# ------------------------------------------------------------------------------
# STEP 5: Start Daphne HTTP Server (Main Single Terminal Window)
# ------------------------------------------------------------------------------
Write-Host "[5/6] Starting HTTP Application Server..." -ForegroundColor Yellow

$SITE_HTTP_PORT = 8002
$lanIp = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1 -ExpandProperty IPv4Address | Select-Object -First 1 -ExpandProperty IPAddress)
if (-not $lanIp) { $lanIp = "127.0.0.1" }
$localUrl = ("http://localhost:{0}" -f $SITE_HTTP_PORT)
$lanUrl   = ("http://{0}:{1}" -f $lanIp, $SITE_HTTP_PORT)

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "   EduMi 2 Application Ready!" -ForegroundColor Green
Write-Host "   ------------------------------------------------------------" -ForegroundColor DarkGreen
Write-Host ("   Local URL  : {0}" -f $localUrl) -ForegroundColor Cyan
Write-Host ("   LAN URL    : {0}" -f $lanUrl)   -ForegroundColor Yellow
Write-Host "   ------------------------------------------------------------" -ForegroundColor DarkGreen
Write-Host ("   Logs dir   : {0}" -f $LogsDir) -ForegroundColor Gray
Write-Host "   Tip        : Open the LAN URL on other devices on the" -ForegroundColor Gray
Write-Host "                same Wi-Fi/network to join meetings remotely." -ForegroundColor Gray
Write-Host "   ------------------------------------------------------------" -ForegroundColor DarkGreen
Write-Host "   Press Ctrl+C in this window to stop all services." -ForegroundColor Gray
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""

try {
    & $VenvPython run_ssl_server.py
} finally {
    Write-Host "`nCleaning up background microservices..." -ForegroundColor Yellow
    foreach ($P in $BGProcesses) {
        if ($P -and -not $P.HasExited) {
            try { Stop-Process -Id $P.Id -Force -ErrorAction Stop; Write-Host "  -> Stopped PID $($P.Id)" -ForegroundColor Gray } catch {}
        }
    }
    Get-Process -Name "livekit-server" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "All EduMi services stopped." -ForegroundColor Green
}
