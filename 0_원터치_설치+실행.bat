@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0"

title Grok Worker - 원터치 설치+실행

echo ========================================================
echo [Grok Worker] 원터치 설치+실행
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
    echo [ERROR] Python 명령을 찾지 못했습니다.
    echo [ERROR] Python 설치 후 PATH 등록이 필요합니다.
    echo.
    pause
    exit /b 1
)

echo [1/4] pip 업데이트 확인 중...
%PY_CMD% -m pip install --upgrade pip
if errorlevel 1 goto :FAIL

echo [2/4] 필수 라이브러리 설치 중...
%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :FAIL

echo [3/4] Playwright Chromium 설치 확인 중...
%PY_CMD% -m playwright install chromium
if errorlevel 1 goto :FAIL

echo [4/4] Grok Worker 실행 중...
echo.
%PY_CMD% main.py

echo.
echo [INFO] Grok Worker 실행이 종료되었습니다.
echo.
pause
exit /b 0

:FAIL
echo.
echo [ERROR] 준비 또는 실행 중 문제가 발생했습니다.
echo [ERROR] 위 메시지를 먼저 확인해주세요.
echo.
pause
exit /b 1

