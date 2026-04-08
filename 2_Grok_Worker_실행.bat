@echo off
CHCP 65001 > nul
setlocal
cd /d "%~dp0"

echo.
echo [INFO] Grok Worker를 실행합니다...
echo.

set "PY_CMD="
where python >nul 2>&1
if %errorlevel% equ 0 set "PY_CMD=python"

if not defined PY_CMD (
    where py >nul 2>&1
    if %errorlevel% equ 0 set "PY_CMD=py"
)

if not defined PY_CMD (
    echo [ERROR] Python 명령을 찾지 못했습니다.
    echo [ERROR] 먼저 "1_필수라이브러리_설치.bat"를 실행해주세요.
    echo.
    pause
    exit /b 1
)

echo [INFO] 사용할 명령: %PY_CMD%
%PY_CMD% main.py

echo.
echo [INFO] Grok Worker 실행이 종료되었습니다.
echo.
pause

