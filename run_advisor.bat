@echo off
title Prismata Neural Eval Overlay
echo ============================================
echo  Prismata Neural Eval Overlay
echo  Started: %date% %time%
echo.
echo  Press F6 in Prismata to analyze game state
echo  Ctrl+D = toggle drag mode
echo  Escape = quit overlay
echo ============================================
echo.

cd /d c:\libraries\PrismataAI

if not exist bin\Prismata_Testing.exe (
    echo ERROR: bin\Prismata_Testing.exe not found.
    echo Build the solution first: Release^|x86
    pause
    exit /b 1
)

if not exist bin\asset\config\neural_weights.bin (
    echo ERROR: bin\asset\config\neural_weights.bin not found.
    echo Export weights first: python training/export_weights.py
    pause
    exit /b 1
)

python tools\prismata_advisor.py %*
if errorlevel 1 (
    echo.
    echo Overlay exited with an error. Check output above.
    pause
)
