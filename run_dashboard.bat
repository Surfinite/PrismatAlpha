@echo off
echo.
echo  =============================================
echo   PrismataAI Command Center
echo   Starting on http://localhost:3000
echo   Close this window to stop the server.
echo  =============================================
echo.
cd /d "%~dp0dashboard"
if not exist node_modules (
    echo  Installing dependencies...
    call npm install
    echo.
)
start http://localhost:3000
node server.js --lan
