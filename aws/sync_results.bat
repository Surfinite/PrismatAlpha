@echo off
REM Sync self-play results from S3 to local machine
REM Run manually or via Task Scheduler (e.g., every 30 min)

set PATH=%PATH%;C:\Program Files\Amazon\AWSCLIV2

REM Source cloud config if CLOUD_BUCKET not already set
if not defined CLOUD_BUCKET (
    if exist "%~dp0..\cloud-config.env" (
        for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0..\cloud-config.env") do (
            if not "%%a"=="" if not "%%a"=="#" set "%%a=%%b"
        )
    )
)
set REGION=%AWS_REGION%
if not defined REGION set REGION=eu-north-1
set BUCKET=%CLOUD_BUCKET%
if not defined BUCKET (
    echo ERROR: Set CLOUD_BUCKET in cloud-config.env
    exit /b 1
)
set LOCAL_DIR=c:\libraries\PrismataAI\bin\training\data\selfplay

aws s3 sync s3://%BUCKET%/results/ %LOCAL_DIR%/ --region %REGION% --exclude "*.log" --exclude "*.txt"
