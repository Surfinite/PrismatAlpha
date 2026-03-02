Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File ""c:\libraries\PrismataAI\aws\watcher.ps1""", 0, True
