# EduMi 2 One-Click Startup Launcher
# Redirects to start_app.bat for unified single-file startup logic

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

& cmd.exe /c "$ScriptDir\start_app.bat"
