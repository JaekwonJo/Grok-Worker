@echo off
setlocal
set "PROFILE=%~dp0runtime\edge_attach_profile_3"
if not exist "%PROFILE%" mkdir "%PROFILE%"
start "" msedge --remote-debugging-port=9224 --user-data-dir="%PROFILE%" --disable-features=msDownloadsHub,DownloadBubble,DownloadBubbleV2 --new-window https://grok.com/imagine
pause
