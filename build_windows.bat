@echo off
setlocal
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo Please install Python 3.12 x64 from python.org, including Tcl/Tk and the py launcher.
    pause
    exit /b 1
)
py -3.12 -m venv .venv-windows
if errorlevel 1 goto failed
.venv-windows\Scripts\python.exe -m pip install -r requirements-desktop.txt
if errorlevel 1 goto failed
.venv-windows\Scripts\python.exe -m compileall -q desktop.py desktop_app.py desktop_worker.py desktop_storage.py desktop_schedule.py
if errorlevel 1 goto failed
.venv-windows\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name DNFHelperDesktop --collect-all requests --collect-all tzdata --add-data "update_sources.json;." desktop.py
if errorlevel 1 goto failed
copy /y LICENSE dist\LICENSE.txt >nul
copy /y DESKTOP.md dist\DESKTOP.md >nul
copy /y ACTIVITY_GUIDE.md dist\ACTIVITY_GUIDE.md >nul
copy /y THIRD_PARTY_NOTICES.md dist\THIRD_PARTY_NOTICES.md >nul
echo Ready: dist\DNFHelperDesktop.exe
pause
exit /b 0
:failed
echo Build failed. Check the error above.
pause
exit /b 1
