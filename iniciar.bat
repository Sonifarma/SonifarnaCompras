@echo off
setlocal
cd /d "%~dp0"
set "SONIFARMA_PY_EXE=py"
if exist ".venv\Scripts\python.exe" set "SONIFARMA_PY_EXE=%~dp0.venv\Scripts\python.exe"
"%SONIFARMA_PY_EXE%" -c "import fastapi, uvicorn, multipart, openpyxl, fitz, reportlab, xlrd, rapidocr_onnxruntime" >nul 2>&1
if errorlevel 1 "%SONIFARMA_PY_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
 echo ERRO: Nao foi possivel instalar as dependencias.
 pause
 exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SONIFARMA_CONTROLE.ps1" start
if errorlevel 1 (
 echo ERRO: Inicializacao nao confirmada. Consulte os logs do Compras.
 pause
 exit /b 1
)
endlocal
