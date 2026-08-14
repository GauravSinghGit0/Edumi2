# =====================================================
# EduMi 2 - Trust Self-Signed SSL Certificate
# Installs certs/edumi.crt into Windows Trusted Root CA
# so browsers stop showing the "Not Secure" warning.
#
# Run as Administrator (or this script will self-elevate).
# =====================================================

$BASE_DIR  = Split-Path -Parent $PSScriptRoot
$CERT_FILE = Join-Path $BASE_DIR "certs\edumi-trust-this.crt"
$CERT_NAME = "EduMi Academic Local CA"

# ── Self-elevate if not running as admin ──────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$targetStore = "LocalMachine"

if (-not $isAdmin) {
    Write-Host "Requesting administrator privileges (UAC prompt)..." -ForegroundColor Yellow
    try {
        Start-Process powershell `
            -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" `
            -Verb RunAs `
            -Wait -ErrorAction Stop
        exit
    } catch {
        Write-Host "[WARNING] Elevation declined or failed. Falling back to installing for the Current User." -ForegroundColor Yellow
        Write-Host "          Note: A Windows Security Warning dialog may pop up to ask for your confirmation." -ForegroundColor Yellow
        $targetStore = "CurrentUser"
    }
}

# ── Install the certificate ───────────────────────────────────────────
Write-Host ""
Write-Host "Installing EduMi Local Root CA certificate..." -ForegroundColor Cyan
Write-Host "  File: $CERT_FILE" -ForegroundColor Gray
Write-Host "  Store: $targetStore" -ForegroundColor Gray
Write-Host ""

if (-not (Test-Path $CERT_FILE)) {
    Write-Host "[ERROR] Certificate file not found: $CERT_FILE" -ForegroundColor Red
    Write-Host "        Run: python scripts\generate_ssl_cert.py" -ForegroundColor Yellow
    exit 1
}

try {
    # Remove old certs first
    $stores = @(
        [System.Security.Cryptography.X509Certificates.X509Store]::new("Root", "LocalMachine"),
        [System.Security.Cryptography.X509Certificates.X509Store]::new("Root", "CurrentUser")
    )
    foreach ($store in $stores) {
        try {
            $store.Open("ReadWrite")
            $old = $store.Certificates | Where-Object { $_.Subject -match "edumi" -or $_.Issuer -match "edumi" }
            foreach ($c in $old) {
                $store.Remove($c)
                Write-Host "      Removed old cert: $($c.Thumbprint) from $($store.Location)" -ForegroundColor DarkYellow
            }
            $store.Close()
        } catch {}
    }

    # Import into target store Root
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CERT_FILE)
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
        [System.Security.Cryptography.X509Certificates.StoreName]::Root,
        $targetStore
    )
    $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $store.Add($cert)
    $store.Close()

    Write-Host "[OK] Certificate installed successfully!" -ForegroundColor Green
    Write-Host "     Subject   : $($cert.Subject)" -ForegroundColor Gray
    Write-Host "     Thumbprint: $($cert.Thumbprint)" -ForegroundColor Gray
    Write-Host "     Valid until: $($cert.NotAfter)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "======================================================" -ForegroundColor Green
    Write-Host " DONE! Restart Chrome and go to https://edumi.ac.in:8002" -ForegroundColor Green
    Write-Host " The padlock should now show as SECURE (green/locked)."  -ForegroundColor Green
    Write-Host "======================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host " If Chrome still warns, open a new tab and go to:"      -ForegroundColor Yellow
    Write-Host "   chrome://restart"                                      -ForegroundColor Yellow
    Write-Host " or close ALL Chrome windows and reopen."                -ForegroundColor Yellow
}
catch {
    Write-Host "[ERROR] Failed to install certificate: $_" -ForegroundColor Red
    exit 1
}
