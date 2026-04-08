@echo off
setlocal
cd /d "%~dp0"

echo.
echo [INFO] Installing Grok Worker libraries...
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

echo [INFO] Using command: %PY_CMD%
%PY_CMD% -m pip install --upgrade pip
if errorlevel 1 goto :FAIL

%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :FAIL

%PY_CMD% -m playwright install chromium
if errorlevel 1 goto :FAIL

echo.
echo [OK] Installation finished.
echo [OK] Next, run the launch batch file.
echo.
pause
exit /b 0

:FAIL
echo.
echo [ERROR] Installation failed.
echo [ERROR] Please check the messages above.
echo.
pause
exit /b 1
