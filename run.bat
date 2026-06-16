@echo off
title Portal Secreto

echo.
echo  ================================================
echo    Portal Secreto - Iniciando...
echo  ================================================
echo.

python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python no encontrado. Instalalo desde python.org
    pause
    exit /b 1
)

echo  Verificando dependencias...
pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo  [ERROR] No se pudieron instalar las dependencias.
    pause
    exit /b 1
)
echo  Dependencias OK.
echo.

if not exist "static\uploads" mkdir "static\uploads"

start "" cmd /c "timeout /t 2 > nul && start http://127.0.0.1:5002"

echo  Servidor iniciando en: http://127.0.0.1:5002
echo  Admin panel en:        http://127.0.0.1:5002/admin/login
echo.
echo  Presiona Ctrl+C para detener el servidor.
echo  ================================================
echo.

python app.py
pause