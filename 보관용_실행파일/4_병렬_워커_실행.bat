@echo off
CHCP 65001 > nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "COUNT=%~1"
if not defined COUNT (
    set /p COUNT=몇 개 워커를 병렬로 여시겠어요? (2 또는 3) :
)
if not defined COUNT set "COUNT=2"
if /I not "%COUNT%"=="2" if /I not "%COUNT%"=="3" (
    echo [ERROR] 2 또는 3만 입력해 주세요.
    echo.
    pause
    exit /b 1
)

set "PY_GUI_CMD="
set "PY_CMD="
where pythonw >nul 2>&1
if %errorlevel% equ 0 set "PY_GUI_CMD=pythonw"
where python >nul 2>&1
if %errorlevel% equ 0 set "PY_CMD=python"
if not defined PY_GUI_CMD (
    where pyw >nul 2>&1
    if %errorlevel% equ 0 set "PY_GUI_CMD=pyw"
)
if not defined PY_CMD (
    where py >nul 2>&1
    if %errorlevel% equ 0 set "PY_CMD=py"
)
if not defined PY_GUI_CMD if not defined PY_CMD (
    echo [ERROR] Python 실행 명령을 찾지 못했습니다.
    echo.
    pause
    exit /b 1
)

echo.
echo [INFO] %COUNT%개 병렬 워커를 준비합니다.
echo [INFO] Edge 창이 %COUNT%개 열리고, 각 창은 다른 디버그 포트를 씁니다.
echo [INFO] 각 Edge 창에서 서로 다른 계정으로 로그인해 주세요.
echo.

for /L %%I in (1,1,%COUNT%) do (
    set /a PORT=9221+%%I
    set "PROFILE=%CD%\runtime\edge_attach_profile_%%I"
    if not exist "!PROFILE!" mkdir "!PROFILE!"
    echo [INFO] Edge %%I 열기 - 포트 !PORT!
    start "" msedge --remote-debugging-port=!PORT! --user-data-dir="!PROFILE!" --new-window https://grok.com/imagine
)

echo.
echo [INFO] Edge 창이 뜬 뒤, 각 창에서 로그인해 주세요.
echo [INFO] 워커 창도 바로 같이 엽니다.
echo.

timeout /t 2 >nul

for /L %%I in (1,1,%COUNT%) do (
    set /a PORT=9221+%%I
    set "ATTACH_URL=http://127.0.0.1:!PORT!"
    set "INSTANCE=worker%%I"
    set "WORKER_NAME=Grok_워커%%I"
    echo [INFO] 워커 %%I 실행 - !ATTACH_URL!
    if defined PY_GUI_CMD (
        start "" !PY_GUI_CMD! main.py --instance !INSTANCE! --attach-url !ATTACH_URL! --worker-name !WORKER_NAME!
    ) else (
        start "" !PY_CMD! main.py --instance !INSTANCE! --attach-url !ATTACH_URL! --worker-name !WORKER_NAME!
    )
)

echo.
echo [INFO] 병렬 실행 요청을 보냈습니다.
echo [INFO] 워커1 = 9222 / 워커2 = 9223 / 워커3 = 9224
echo [INFO] 각 워커 설정은 따로 저장됩니다.
echo.
pause
