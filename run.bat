@echo off
title SOCIAL-MD
cd /d "%~dp0"

where python >nul 2>&1 || (
  echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add Python to PATH".
  pause & exit /b 1
)

echo Installing / updating dependencies...
python -m pip install -q -r requirements.txt
python -m pip install -q -U yt-dlp

echo.
python run.py
pause