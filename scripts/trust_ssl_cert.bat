@echo off
:: EduMi 2 - Install SSL certificate as Trusted Root CA
:: Double-click this file to trust the self-signed cert.
:: A UAC (admin) prompt will appear - click Yes to allow.

powershell -ExecutionPolicy Bypass -File "%~dp0trust_ssl_cert.ps1"
pause
