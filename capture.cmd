@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Python environment missing. See README.md.
  pause
  exit /b 1
)

rem With arguments, use the command-line interface directly.
if not "%~1"=="" (
  "%PY%" capture.py %*
  exit /b
)

rem Generic fallback; the GUI resolves redirected Documents folders.
set "OUTDIR=%USERPROFILE%\Documents\LectureScripts"

echo ============================================
echo   Lecture Capture - 课程字幕抓取
echo ============================================
echo.
echo  输出目录：%OUTDIR%
echo.
echo  开始前请确认：
echo    1) 已按 Win+Ctrl+L 打开「实时辅助字幕」
echo    2) 已在 Edge 里开始播放课程视频
echo.
set /p "NAME=本次课程名称（例如 Lecture_01）: "
if "%NAME%"=="" (
  echo.
  echo 未输入名称，已取消。
  pause
  exit /b 1
)
echo.
echo 正在抓取... 看完课后回到本窗口按 Ctrl+C 结束。
echo.
"%PY%" capture.py --name "%NAME%" --out "%OUTDIR%"
echo.
echo 已结束，文件保存在：
echo   %OUTDIR%
pause
