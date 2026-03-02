@echo off
title AWS Selfplay Relaunch Watcher
echo Watching for EC2 selfplay instances to finish...
echo Will relaunch 8 on-demand + 4 spot when all terminate.
echo.
cd /d c:\libraries\PrismataAI
"C:\Program Files\Git\bin\bash.exe" aws/relaunch_when_done.sh
pause
