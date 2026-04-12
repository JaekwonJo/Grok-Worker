@echo off
setlocal
set "PROFILE=%~dp0runtime\edge_attach_profile_2"
if not exist "%PROFILE%" mkdir "%PROFILE%"
start "" msedge --remote-debugging-port=9223 --user-data-dir="%PROFILE%" --disable-features=msDownloadsHub,DownloadBubble,DownloadBubbleV2 --new-window https://grok.com/imagine
pause
