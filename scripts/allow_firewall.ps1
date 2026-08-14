# ── Edumi Firewall Rules ──────────────────────────────────────────────────────
# Run once as Administrator to allow all Edumi ports through Windows Firewall
# Usage: Right-click → "Run as Administrator"  OR
#        Start-Process powershell -Verb RunAs -ArgumentList "-File allow_firewall.ps1"

# Check if running as admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Write-Host "Not running as Administrator. Relaunching with elevation..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Write-Host ""
Write-Host "=== Edumi Firewall Setup ===" -ForegroundColor Cyan
Write-Host ""

$rules = @(
    @{ Name="Edumi-Nginx-80";      Port=80;              Proto="TCP"; Desc="Nginx web server" },
    @{ Name="Edumi-Django-8002";   Port=8002;            Proto="TCP"; Desc="Django web server" },
    @{ Name="Edumi-Camera-8003";   Port=8003;            Proto="TCP"; Desc="Camera service" },
    @{ Name="Edumi-LiveKit-7880";  Port=7880;            Proto="TCP"; Desc="LiveKit HTTP/WS signaling" },
    @{ Name="Edumi-LiveKit-7881";  Port=7881;            Proto="TCP"; Desc="LiveKit RTC TCP" },
    @{ Name="Edumi-LiveKit-7882";  Port=7882;            Proto="UDP"; Desc="LiveKit RTC UDP" },
    @{ Name="Edumi-LiveKit-UDP";   Port="50000-50200";   Proto="UDP"; Desc="LiveKit media UDP range" }
)

foreach ($r in $rules) {
    # Remove old rule if exists
    Remove-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue

    # Add inbound rule
    New-NetFirewallRule `
        -DisplayName $r.Name `
        -Direction Inbound `
        -Protocol $r.Proto `
        -LocalPort $r.Port `
        -Action Allow `
        -Profile Any `
        -Description $r.Desc | Out-Null

    # Add outbound rule
    New-NetFirewallRule `
        -DisplayName "$($r.Name)-Out" `
        -Direction Outbound `
        -Protocol $r.Proto `
        -LocalPort $r.Port `
        -Action Allow `
        -Profile Any `
        -Description $r.Desc | Out-Null

    Write-Host "  [OK] $($r.Desc) ($($r.Proto) $($r.Port))" -ForegroundColor Green
}

# Also allow the executables themselves
$exes = @(
    @{ Name="Edumi-LiveKit-Exe";  Path="$PSScriptRoot\livekit-bin\livekit-server.exe" },
    @{ Name="Edumi-Python";       Path=(Get-Command python).Source }
)

foreach ($e in $exes) {
    if (Test-Path $e.Path) {
        Remove-NetFirewallRule -DisplayName $e.Name -ErrorAction SilentlyContinue
        New-NetFirewallRule `
            -DisplayName $e.Name `
            -Direction Inbound `
            -Program $e.Path `
            -Action Allow `
            -Profile Any | Out-Null
        Write-Host "  [OK] Allowed exe: $($e.Path)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "All firewall rules applied." -ForegroundColor Cyan
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
