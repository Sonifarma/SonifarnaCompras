@echo off
cd /d "%~dp0"
echo ========================================
echo SONIFARMA - INTELIGENCIA DE COMPRAS
 echo ========================================
py -m pip install -r requirements.txt
if errorlevel 1 (
 echo ERRO: Nao foi possivel instalar as dependencias.
 pause
 exit /b 1
)
py -m uvicorn app:app --host 127.0.0.1 --port 8766
pause
