@echo off
echo ========================================
echo Adding Windows Firewall Rules
echo ========================================
echo.
echo This will allow Python to accept connections on ports 8002 and 8003
echo You may need to run this as Administrator
echo.
pause

netsh advfirewall firewall add rule name="DigiRoom Main App (Port 8002)" dir=in action=allow protocol=TCP localport=8002
netsh advfirewall firewall add rule name="DigiRoom Camera Service (Port 8003)" dir=in action=allow protocol=TCP localport=8003

echo.
echo ========================================
echo Firewall rules added!
echo ========================================
echo.
echo If you see errors above, try:
echo 1. Right-click this file
echo 2. Select "Run as administrator"
echo.
pause
