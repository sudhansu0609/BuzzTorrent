@echo off
rem Stops the BuzzTorrent server started from this folder (uses the PID it recorded).
rem Normally you don't need this: closing the BuzzTorrent window stops it.
cd /d "%~dp0"
if not exist ".buzztorrent.pid" (
  echo    BuzzTorrent is not running.
  timeout /t 2 >nul
  exit /b 0
)
set /p PID=<".buzztorrent.pid"
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter 'ProcessId=%PID%'; if ($p -and ($p.CommandLine -like '*app.py*' -or $p.CommandLine -like '*launcher.pyw*')) { Stop-Process -Id %PID% -Force; '   BuzzTorrent stopped.' } else { '   BuzzTorrent is not running.' }"
del ".buzztorrent.pid" >nul 2>&1
timeout /t 2 >nul
