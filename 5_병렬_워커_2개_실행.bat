@echo off
CHCP 65001 > nul
cd /d "%~dp0"
call "%~dp04_병렬_워커_실행.bat" 2
