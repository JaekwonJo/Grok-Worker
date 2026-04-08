@echo off
setlocal
cd /d "%~dp0"

echo.
echo [INFO] Grok Worker 필수 라이브러리를 설치합니다...
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

echo [INFO] 사용할 명령: %PY_CMD%
%PY_CMD% -m pip install --upgrade pip
if errorlevel 1 goto :FAIL

%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :FAIL

%PY_CMD% -m playwright install chromium
if errorlevel 1 goto :FAIL

echo.
echo [OK] 설치가 끝났습니다.
echo [OK] 다음에는 "2_Grok_Worker_실행.bat"을 더블클릭하면 됩니다.
echo.
pause
exit /b 0

:FAIL
echo.
echo [ERROR] 설치 중 문제가 발생했습니다. 위 메시지를 확인해주세요.
echo.
pause
exit /b 1

