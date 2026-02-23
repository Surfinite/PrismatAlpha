@echo off
:: Prismata Replay Code Extractor
:: Double-click to run. Needs Administrator for hosts file changes.

:: Check for admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: We have admin — change to the script's directory
cd /d "%~dp0"

echo.
echo ============================================================
echo   Prismata Replay Code Extractor
echo ============================================================
echo.
echo Working directory: %cd%
echo.

:: Check Python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found!
    echo.
    echo Please install Python 3.8 or later from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Run the extractor (the script has its own "Press Enter to exit" prompt)
python "%~dp0prismata_replay_dump.py" %*

:: Safety net — keep window open if Python crashed
if %errorlevel% neq 0 (
    echo.
    echo Something went wrong. See error above.
    pause
)
