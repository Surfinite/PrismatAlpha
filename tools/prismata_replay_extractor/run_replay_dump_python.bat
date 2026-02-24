@echo off
:: Prismata Replay Code Extractor (requires Python installed)
:: Double-click to run. Needs Administrator for hosts file + SWF patch.

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

:: Try system Python
where python >nul 2>&1
if %errorlevel% equ 0 (
    python "%~dp0prismata_replay_dump.py" %*
) else (
    echo ERROR: Python is not installed or not on PATH.
    echo.
    echo Download Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    echo.
    echo Or use the bundled version ^(prismata_replay_extractor_standalone.zip^)
)

:: Safety net — keep window open if Python crashed
if %errorlevel% neq 0 (
    echo.
    echo Something went wrong. See error above.
    pause
)
