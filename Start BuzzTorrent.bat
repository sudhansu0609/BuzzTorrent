@echo off
setlocal EnableExtensions
title BuzzTorrent
cd /d "%~dp0"
rem Tip: the "BuzzTorrent" shortcut on your Desktop / Start Menu starts the app
rem without even this brief console window.

rem ---- 1. Find Python 3.10 or newer --------------------------------------
set "PY="
for %%C in (python py python3) do (
  if not defined PY (
    %%C -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=%%C"
  )
)
if not defined PY goto :nopython

rem ---- 2. pythonw.exe runs the app with no console window ----------------
set "PYW="
for /f "usebackq delims=" %%W in (`%PY% -c "import sys, pathlib; w = pathlib.Path(sys.executable).with_name('pythonw.exe'); print(w if w.exists() else sys.executable)"`) do set "PYW=%%W"

rem ---- 3. The built-in downloader needs aria2 (offered once) -------------
if not exist "data\aria2-asked" (
  where aria2c >nul 2>&1
  if errorlevel 1 if not exist "%LOCALAPPDATA%\Microsoft\WinGet\Packages\aria2.aria2_Microsoft.Winget.Source_8wekyb3d8bbwe" (
    where winget >nul 2>&1 && (
      echo.
      echo    BuzzTorrent downloads torrents itself with aria2, a free open-source download engine.
      choice /c YN /m "   Install aria2 now with winget"
      if not errorlevel 2 winget install -e --id aria2.aria2 --accept-source-agreements --accept-package-agreements
    )
  )
  if not exist data mkdir data
  echo asked> "data\aria2-asked"
)

rem ---- 4. First run: create the Desktop / Start Menu shortcuts -----------
if not exist "static\buzztorrent.ico" %PY% app.py --install-shortcuts >nul 2>&1

rem ---- 5. Launch (opens the app window; quits when you close it) ---------
start "" "%PYW%" "%~dp0launcher.pyw"
exit /b 0

:nopython
echo.
echo    Python 3.10 or newer is required but was not found.
echo.
where winget >nul 2>&1
if errorlevel 1 (
  echo    Download it from https://www.python.org/downloads/
  echo    During setup, tick "Add python.exe to PATH". Then run this file again.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)
choice /c YN /m "   Install Python 3.12 now with winget"
if errorlevel 2 (
  echo    OK. Install Python from https://www.python.org/downloads/ and run this file again.
  pause
  exit /b 1
)
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
echo.
echo    Python installed. Close this window and double-click "Start BuzzTorrent" again.
pause
exit /b 0
