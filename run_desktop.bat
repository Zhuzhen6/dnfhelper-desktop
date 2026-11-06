@echo off
setlocal
cd /d "%~dp0"
if not exist .venv-windows\Scripts\pythonw.exe (
    echo Run build_windows.bat first.
    pause
    exit /b 1
)
start "" .venv-windows\Scripts\pythonw.exe desktop.py
