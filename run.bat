@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 exit /b %errorlevel%
)
.venv\Scripts\python.exe -c "import requests, yaml, dotenv, schedule" >nul 2>&1
if errorlevel 1 (
    echo Installing missing dependencies...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 exit /b %errorlevel%
)
.venv\Scripts\python.exe bot.py %*
set "BOT_EXIT=%errorlevel%"
endlocal & exit /b %BOT_EXIT%
