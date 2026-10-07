@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo LectureCapture's Python environment is missing.
  echo See README.md for environment setup.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launch.pyw"
