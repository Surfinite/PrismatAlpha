@echo off
title SelfPlay 10K Generation - DO NOT CLOSE
echo ============================================
echo  SelfPlay 10K Generation (1s think time)
echo  Started: %date% %time%
echo  ETA: ~7.5 hours
echo  This window is safe from Claude Code.
echo  Each run writes to its own timestamped folder.
echo  Crash-safe: restart anytime, no data lost.
echo ============================================
echo.

cd /d c:\libraries\PrismataAI\bin
Prismata_Testing.exe > selfplay_10k_log.txt 2>&1

echo.
echo ============================================
echo  FINISHED: %date% %time%
echo  Check bin\training\data\selfplay\run_*\ for shards
echo  Log: bin\selfplay_10k_log.txt
echo ============================================
pause
