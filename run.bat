@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
python bot.py %*
endlocal
