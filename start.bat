@echo off
REM Image Forensics Inspector - Windows launcher
REM Usage:
REM   start.bat            : create venv, install deps, launch Web UI
REM   start.bat --demo     : also prepare demo images and run a demo analysis first
setlocal
cd /d "%~dp0"

if not exist .venv (
    echo Creating Python virtualenv...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --disable-pip-version-check -r requirements.txt

if /I "%~1"=="--demo" (
    echo.
    echo === Running one-click demo (data prep + analysis) ===
    python demo.py
    echo.
)

echo.
echo Starting Image Forensics Inspector at http://127.0.0.1:5050
echo Press Ctrl+C to stop.
echo.
start "" "http://127.0.0.1:5050"
python webapp.py --host 127.0.0.1 --port 5050
endlocal
