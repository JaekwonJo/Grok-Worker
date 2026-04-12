@echo off
setlocal
set "PROFILE=%~dp0runtime\edge_attach_profile"
if not exist "%PROFILE%" mkdir "%PROFILE%"
start "" msedge --remote-debugging-port=9222 --user-data-dir="%PROFILE%" --new-window https://grok.com/imagine
pause
