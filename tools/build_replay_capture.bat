@echo off
title Build Prismata Replay Capture (standalone exe)
echo.
echo  Building standalone replay capture tool...
echo  This bundles Python + sniffer into a single exe.
echo.

:: Check PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo  Installing PyInstaller...
    pip install pyinstaller
)

:: Build the exe — bundles replay_capture.py + prismata_sniffer.py
:: The --add-data flag includes the sniffer so the exe can find it
pyinstaller --onefile --name "PrismataReplayCapture" ^
    --add-data "%~dp0prismata_sniffer.py;." ^
    --hidden-import=ssl ^
    --hidden-import=hashlib ^
    --uac-admin ^
    "%~dp0replay_capture.py"

if errorlevel 1 (
    echo.
    echo  [!] Build failed. Check errors above.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo  Build complete!
echo  Exe: dist\PrismataReplayCapture.exe
echo.
echo  To distribute, send these 2 files:
echo    - dist\PrismataReplayCapture.exe
echo    - run_replay_capture_standalone.bat
echo  ============================================
pause
