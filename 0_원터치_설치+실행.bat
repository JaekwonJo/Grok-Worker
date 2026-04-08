@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0"

title Grok Worker - One Touch Setup and Run

echo ========================================================
echo [Grok Worker] One Touch Setup and Run
echo ========================================================
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
    echo [ERROR] Please install Python and add it to PATH.
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking pip...
%PY_CMD% -m pip install --upgrade pip
if errorlevel 1 goto :FAIL

echo [2/4] Installing required libraries...
%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :FAIL

echo [3/4] Installing Playwright Chromium...
%PY_CMD% -m playwright install chromium
if errorlevel 1 goto :FAIL

echo [4/4] Starting Grok Worker...
echo.
%PY_CMD% main.py

echo.
echo [INFO] Grok Worker has stopped.
echo.
pause
exit /b 0

:FAIL
echo.
echo [ERROR] Setup or launch failed.
echo [ERROR] Please check the messages above.
echo.
pause
exit /b 1
