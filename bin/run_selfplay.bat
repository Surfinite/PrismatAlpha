@echo off
title SelfPlay HardestAI 1s - DO NOT CLOSE
echo ============================================
echo  SelfPlay HardestAI 1s Generation
echo  Started: %date% %time%
echo  Run this bat multiple times for more CPU.
echo  Each instance is independent and crash-safe.
echo  Close this window to stop.
echo ============================================
echo.

cd /d c:\libraries\PrismataAI\bin
Prismata_Testing.exe > selfplay_log_%random%.txt

echo.
echo ============================================
echo  STOPPED: %date% %time%
echo ============================================
pause
