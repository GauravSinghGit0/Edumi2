@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title EduMi 2 Startup Manager (Batch Wrapper)

rem  ---------------------------------------------------------------------------
rem  EduMi 2 - start_app.bat
rem  Wrapper for start_app.ps1 so users can double-click this .bat and launch
rem  the full stack without manually enabling execution policy or activating
rem  the Python venv.  On launch + after shutdown it also prints both the
rem  localhost URL and the LAN URL so remote devices on the same network can
rem  access the meeting room.
rem  ---------------------------------------------------------------------------

cd /d "%~dp0"

rem  --- Resolve the machine's primary LAN IPv4 (not loopback) ---------------
set "PORT=8002"
set "LAN_IP=127.0.0.1"

for /f "tokens=2 delims=:" %%a in ('2^>nul "%SystemRoot%\System32\netsh.exe" interface ipv4 show addresses ^| "%SystemRoot%\System32\findstr.exe" /r /c:"IP Address"') do (
    for /f "tokens=* delims= " %%b in ("%%a") do (
        set "_ip=%%b"
        if not "!_ip:~0,3!"=="127" if "!LAN_IP!"=="127.0.0.1" set "LAN_IP=!_ip!"
    )
)

rem  Fallback: if netsh didn't work, try WMIC
if "%LAN_IP%"=="127.0.0.1" (
    for /f "tokens=2 delims==" %%a in ('2^>nul "%SystemRoot%\System32\wbem\wmic.exe" nicconfig where "IPEnabled=TRUE" get IPAddress /value ^| "%SystemRoot%\System32\findstr.exe" "="') do (
        for /f "tokens=1 delims=," %%b in ("%%a") do (
            set "_ip=%%~b"
            if not "!_ip:~0,3!"=="127" if "!LAN_IP!"=="127.0.0.1" set "LAN_IP=!_ip!"
        )
    )
)

rem  --- Auto-activate venv if present ---------------------------------------
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
)

rem  --- Header ---------------------------------------------------------------
echo.
echo ========================================================================
echo           EduMi 2 - Unified Enterprise Launcher (Batch Wrapper)
echo ========================================================================
echo   Script dir  : %~dp0
echo   Python venv : %VIRTUAL_ENV:=(not active)=%
echo   LAN IP      : %LAN_IP%
echo.
echo   Access URLs:
echo     Local URL  : https://localhost:%PORT%
echo     LAN URL    : https://%LAN_IP%:%PORT%
echo ------------------------------------------------------------------------
echo   Launching PowerShell start_app.ps1 now ...
echo   PowerShell will print [OK] / [FAIL] status for every background
echo   service (LiveKit / Camera / Celery) and re-print both URLs above
echo   right before Daphne begins listening on :%PORT%.
echo ========================================================================
echo.

rem  --- Run the real launcher ----------------------------------------------
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" ^
    -NoProfile ^
    -ExecutionPolicy Bypass ^
    -File "%~dp0start_app.ps1"

set "EXIT_CODE=%ERRORLEVEL%"

rem  --- Post-shutdown summary ----------------------------------------------
echo.
echo ========================================================================
echo   EduMi 2 stack stopped.
echo.
echo   Last known URLs (still correct if you re-run this .bat):
echo     Local URL  : https://localhost:%PORT%
echo     LAN URL    : https://%LAN_IP%:%PORT%
echo ------------------------------------------------------------------------
echo   PowerShell exit code: %EXIT_CODE%
echo   (open logs\*.stdout.log / *.stderr.log to debug a service crash)
echo ========================================================================
echo.
echo Press any key to exit...
pause >nul
endlocal
exit /b %EXIT_CODE%
