@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "app\dashboard\Home.py" (
    echo The dashboard is built in stage 4 - not available yet.
    pause
    exit /b 0
)
".venv\Scripts\python.exe" -m streamlit run app\dashboard\Home.py
