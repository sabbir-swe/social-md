@echo off
title Building SOCIAL-MD.exe
cd /d "%~dp0"

echo Preparing build tools...
python -m pip install -q -U pyinstaller yt-dlp flask

echo Cleaning previous build...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q SOCIAL-MD.spec 2>nul

echo.
echo Building executable (this can take a few minutes)...
echo.
python -m PyInstaller --onefile ^
  --name "SOCIAL-MD" ^
  --icon "NONE" ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --collect-all yt_dlp ^
  --hidden-import flask ^
  run.py

echo.
if exist "dist\SOCIAL-MD.exe" (
  echo ==========================================
  echo  SUCCESS  ->  dist\SOCIAL-MD.exe
  echo  Put ffmpeg.exe next to it before sharing.
  echo ==========================================
) else (
  echo  BUILD FAILED - see the errors above.
)
pause