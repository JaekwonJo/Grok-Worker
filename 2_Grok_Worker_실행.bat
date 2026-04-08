@echo off
CHCP 65001 > nul
setlocal
cd /d "%~dp0"

echo.
echo [INFO] Starting Grok Worker...
echo.

set "PY_CMD="
where python >nul 2>&1
if %errorlevel% equ 0 set "PY_CMD=python"

if not defined PY_CMD (
    where py >nul 2>&1
    if %errorlevel% equ 0 set "PY_CMD=py"
)

if not defined PY_CMD (
    echo [ERROR] Python command was not found.
    echo [ERROR] Please run the install batch file first.
    echo.
    pause
    exit /b 1
)

echo [INFO] Using command: %PY_CMD%
%PY_CMD% main.py

echo.
echo [INFO] Grok Worker has stopped.
echo.
pause
