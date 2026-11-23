@echo off
REM One-time setup: creates .venv, installs packages, creates .env, runs checks.
chcp 65001 >nul
cd /d "%~dp0"

set PYCMD=python
py -3.12 --version >nul 2>nul && set PYCMD=py -3.12

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment...
    %PYCMD% -m venv .venv || goto :error
) else (
    echo [1/4] Virtual environment already exists.
)

echo [2/4] Installing packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error

if not exist ".env" (
    echo [3/4] Creating .env from .env.example...
    copy ".env.example" ".env" >nul
) else (
    echo [3/4] .env already exists - not overwritten.
)

echo [4/4] Running checks...
".venv\Scripts\python.exe" -m app.main doctor
".venv\Scripts\python.exe" -m pytest -q
echo.
echo Setup finished.
pause
exit /b 0

:error
echo.
echo SETUP FAILED - copy the messages above and send them to Claude.
pause
exit /b 1
