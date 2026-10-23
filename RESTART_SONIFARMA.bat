@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SONIFARMA_CONTROLE.ps1" restart
if errorlevel 1 (
 pause
 exit /b 1
)
