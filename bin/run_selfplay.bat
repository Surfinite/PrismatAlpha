@echo off
title SelfPlay HardestAI 1s - DO NOT CLOSE
echo ============================================
echo  SelfPlay HardestAI 1s Generation
echo  Started: %date% %time%
echo  Run this bat multiple times for more CPU.
echo  Each instance is independent and crash-safe.
echo  Close this window to stop.
echo  Loops automatically (1000 games per cycle).
echo ============================================
echo.

cd /d c:\libraries\PrismataAI\bin

if not exist Prismata_Testing.exe (
    echo ERROR: Prismata_Testing.exe not found in %cd%
    pause
    exit /b 1
)

set BATCH=0
:loop
set /a BATCH+=1
echo [%date% %time%] Starting batch %BATCH% (1000 games)...
Prismata_Testing.exe 2>> selfplay_log.txt
if errorlevel 1 (
    echo [%date% %time%] Batch %BATCH% exited with error. Waiting 5s before retry...
    timeout /t 5 /nobreak >nul
)
echo [%date% %time%] Batch %BATCH% complete.
goto loop
