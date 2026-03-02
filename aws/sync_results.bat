@echo off
REM Sync self-play results from S3 to local machine
REM Run manually or via Task Scheduler (e.g., every 30 min)

set PATH=%PATH%;C:\Program Files\Amazon\AWSCLIV2
set REGION=eu-north-1
set BUCKET=prismata-selfplay-data
set LOCAL_DIR=c:\libraries\PrismataAI\bin\training\data\selfplay

aws s3 sync s3://%BUCKET%/results/ %LOCAL_DIR%/ --region %REGION% --exclude "*.log" --exclude "*.txt"
