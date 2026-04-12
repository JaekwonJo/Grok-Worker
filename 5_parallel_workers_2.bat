@echo off
cd /d "%~dp0"

set "PY_CMD="
where python >nul 2>&1
if %errorlevel% equ 0 set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1
    if %errorlevel% equ 0 set "PY_CMD=py"
)
if not defined PY_CMD (
    echo [ERROR] Python command was not found.
    echo.
    pause
    exit /b 1
)

%PY_CMD% parallel_launcher.py 2
pause
