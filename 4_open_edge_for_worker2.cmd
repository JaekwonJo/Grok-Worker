@echo off
setlocal
set "PROFILE=%~dp0runtime\edge_attach_profile_2"
if not exist "%PROFILE%" mkdir "%PROFILE%"
reg add "HKCU\Software\Policies\Microsoft\Edge" /v VisualSearchEnabled /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKCU\Software\Policies\Microsoft\Edge" /v SearchForImageEnabled /t REG_DWORD /d 0 /f >nul 2>&1
start "" msedge --remote-debugging-port=9223 --user-data-dir="%PROFILE%" --disable-features=msDownloadsHub,DownloadBubble,DownloadBubbleV2 --new-window https://grok.com/imagine
pause
