@echo off
title Prismata Replay Capture
echo.
echo  Prismata Replay Capture Tool
echo  ============================
echo.
echo  This tool will:
echo    1. Temporarily patch Prismata.swf for proxy compatibility
echo    2. Capture replay codes from games you play or spectate
echo    3. Restore everything when you're done
echo.
echo  IMPORTANT: Close Prismata before starting!
echo.
pause

:: Run the capture tool (requests admin elevation internally)
python "%~dp0tools\replay_capture.py" %*

:: If python not found, show helpful message
if errorlevel 9009 (
    echo.
    echo  [!] Python is not installed or not on PATH.
    echo  [!] Download Python from https://www.python.org/downloads/
    echo  [!] Make sure to check "Add Python to PATH" during install.
    echo.
    pause
)
