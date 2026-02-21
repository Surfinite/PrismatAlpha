@echo off
title Prismata Tools (Sniffer + Advisor + Autopilot)
echo ============================================
echo  Prismata Tools Launcher
echo  Started: %date% %time%
echo.
echo  Sniffer: captures replay codes + chat codes
echo  Advisor: neural eval overlay (F6 / Shift+F6)
echo  Autopilot: AI move injection (--autopilot)
echo.
echo  Escape = quit both tools
echo  Ctrl+D = toggle overlay drag mode
echo ============================================
echo.

cd /d c:\libraries\PrismataAI

:: Pre-flight checks
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

:: Check hosts file for proxy redirect
findstr /C:"127.0.0.1" /C:"ec2-54-83-83-240.compute-1.amazonaws.com" %SystemRoot%\System32\drivers\etc\hosts >nul 2>&1
if errorlevel 1 (
    echo WARNING: Hosts file does not have proxy redirect.
    echo The sniffer needs:  127.0.0.1 ec2-54-83-83-240.compute-1.amazonaws.com
    echo.
    echo Run tmp_restore_hosts.ps1 as admin to set it up, or continue without sniffer.
    echo.
    choice /M "Continue anyway (advisor only)"
    if errorlevel 2 exit /b 1
    echo Starting advisor only...
    python tools\prismata_advisor.py %*
    goto :done
)

:: Start sniffer proxy in a minimized background window
:: Pass --autopilot to enable AI move injection (add --auto for full-auto, --dry-run for testing)
echo [*] Starting network sniffer proxy...
start "Prismata Sniffer" /MIN python tools\prismata_sniffer.py proxy %*

:: Give the sniffer a moment to bind ports
timeout /t 2 /noerror >nul

echo [*] Starting neural eval overlay...
echo.

:: Run advisor in foreground — blocks until user presses Escape
python tools\prismata_advisor.py %*

:: When advisor exits, kill the sniffer
echo.
echo [*] Overlay closed. Stopping sniffer...
for /f "tokens=2" %%p in ('tasklist /FI "WINDOWTITLE eq Prismata Sniffer" /NH 2^>nul ^| findstr /I "python"') do (
    taskkill /PID %%p /F >nul 2>&1
)

:done
echo [*] All tools stopped.
if errorlevel 1 (
    echo.
    echo Exited with an error. Check output above.
    pause
)
