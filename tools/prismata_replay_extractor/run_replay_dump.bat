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

:: Use bundled Python (no install needed)
set "PYTHON=%~dp0python\python.exe"
if not exist "%PYTHON%" (
    echo ERROR: Bundled Python not found at %PYTHON%
    echo Make sure you extracted the full zip, not just this bat file.
    echo.
    pause
    exit /b 1
)

:: Run the extractor
"%PYTHON%" "%~dp0prismata_replay_dump.py" %*

:: Safety net — keep window open if Python crashed
if %errorlevel% neq 0 (
    echo.
    echo Something went wrong. See error above.
    pause
)
