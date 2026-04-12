@echo off
setlocal
set "PROFILE=%~dp0runtime\edge_attach_profile_2"
if not exist "%PROFILE%" mkdir "%PROFILE%"
start "" msedge --remote-debugging-port=9223 --user-data-dir="%PROFILE%" --new-window https://grok.com/imagine
pause
