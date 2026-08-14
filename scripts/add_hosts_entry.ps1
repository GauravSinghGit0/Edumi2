# Add edumi.ac.in to Windows hosts file
# MUST be run as Administrator (right-click -> Run as Administrator)

$HOSTS_FILE = "$env:windir\System32\drivers\etc\hosts"
$ENTRY      = "127.0.0.1    edumi.ac.in    www.edumi.ac.in"

# Check if entry already exists
if (Select-String -Path $HOSTS_FILE -Pattern "edumi\.ac\.in" -Quiet) {
    Write-Host "[SKIP] edumi.ac.in already exists in hosts file." -ForegroundColor Yellow
} else {
    # Append entry (requires admin)
    Add-Content -Path $HOSTS_FILE -Value "`n# EduMi 2 - Local Development SSL Domain`n$ENTRY" -Force
    Write-Host "[OK]   Added '$ENTRY' to hosts file." -ForegroundColor Green
}

# Flush DNS cache so the new entry takes effect immediately
ipconfig /flushdns | Out-Null
Write-Host "[OK]   DNS cache flushed." -ForegroundColor Green

Write-Host ""
Write-Host "You can now access: https://edumi.ac.in:8002" -ForegroundColor Cyan
