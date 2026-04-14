@echo off
setlocal
cd /d "%~dp0"
set "PROFILE=%~dp0runtime\edge_attach_profile_3"
set "CONFIG=%~dp0grok_worker_config_worker3.json"
if not exist "%CONFIG%" set "CONFIG=%~dp0grok_worker_config.json"
if not exist "%PROFILE%" mkdir "%PROFILE%"
reg add "HKCU\Software\Policies\Microsoft\Edge" /v VisualSearchEnabled /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKCU\Software\Policies\Microsoft\Edge" /v SearchForImageEnabled /t REG_DWORD /d 0 /f >nul 2>&1
set "PY_CMD="
where python >nul 2>&1
if %errorlevel% equ 0 set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1
    if %errorlevel% equ 0 set "PY_CMD=py"
)
if not defined PY_CMD (
    echo [ERROR] Python command was not found.
    pause
    exit /b 1
)
%PY_CMD% "%~dp0edge_launcher.py" --port 9224 --profile-dir "%PROFILE%" --config "%CONFIG%" --url "https://grok.com/imagine"
pause
