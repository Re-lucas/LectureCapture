@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto install

py -3.14 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)" >nul 2>&1
if not errorlevel 1 (
  py -3.14 -m venv .venv
  if errorlevel 1 goto failed
  goto install
)
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)" >nul 2>&1
if errorlevel 1 (
  echo Install official Python 3.14 for Windows, including Tcl/Tk, first.
  echo https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
python -m venv .venv
if errorlevel 1 goto failed

:install
".venv\Scripts\python.exe" -c "import sys, tkinter; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.lock.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click LectureCapture.cmd to open the app.
pause
exit /b 0

:failed
echo.
echo Setup failed. Read the error above and README.md. Your recordings are unchanged.
pause
exit /b 1
