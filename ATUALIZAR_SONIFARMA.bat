@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0atualizar-github.ps1" -Destino "%~dp0."
if errorlevel 1 (
 echo ERRO: Atualizacao ou inicializacao nao concluida. Confira a mensagem e os logs.
 pause
 exit /b 1
)
