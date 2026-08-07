@echo off
REM Double-click this file to start the finance app.
REM
REM %~dp0 is the folder this script lives in, so it works no matter what the
REM current directory is when Windows launches it.

title Finance app
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   The Python environment is missing.
    echo.
    echo   Set it up once with:
    echo       cd "%~dp0backend"
    echo       python -m venv .venv
    echo       .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "..\frontend\dist\index.html" (
    echo.
    echo   The web interface has not been built yet.
    echo.
    echo   Build it once with:
    echo       cd "%~dp0frontend"
    echo       npm install
    echo       npm run build
    echo.
    pause
    exit /b 1
)

REM Rebuild the interface when its source is newer than the last build.
REM Without this, editing frontend code leaves the server serving the previous
REM bundle and the change appears not to have happened at all.
REM
REM The comparison is done in PowerShell because batch has no way to compare
REM the newest file in a tree against a single file.
REM Signalled by exit code rather than captured output: inside a for /f the
REM pipes in the PowerShell pipeline need escaping, and that escaping silently
REM broke the comparison so it never rebuilt.
powershell -NoProfile -Command "$src = Get-ChildItem '%~dp0frontend\src' -Recurse -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1; $dist = Get-Item '%~dp0frontend\dist\index.html' -ErrorAction SilentlyContinue; if ($src -and $dist -and $src.LastWriteTime -gt $dist.LastWriteTime) { exit 1 } else { exit 0 }"

if errorlevel 1 (
    echo.
    echo   Frontend changed since the last build - rebuilding...
    pushd "%~dp0frontend"
    call npm run build
    if errorlevel 1 (
        REM A broken build must not block the app: the previous bundle still
        REM works, so warn and carry on rather than refusing to start.
        echo.
        echo   The rebuild failed. Starting with the previous version instead.
        echo   The error is above.
        echo.
    )
    popd
)

echo.
echo   Starting the finance app...
echo   Your browser will open at http://127.0.0.1:8000
echo.
echo   Leave this window open while you use the app.
echo   Press Ctrl+C here to stop it.
echo.

REM Opens the browser a few seconds from now, in the background, so the server
REM has time to come up first. PowerShell avoids the nested-quote problems that
REM the batch "start" command runs into here.
start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 4; Start-Process 'http://127.0.0.1:8000'"

REM Runs in the foreground so the log stays visible and Ctrl+C stops the server.
.venv\Scripts\python.exe -m uvicorn app.main:app

REM Only reached if the server exits by itself, which means something failed.
REM Without the pause the window would vanish before the error can be read.
if errorlevel 1 (
    echo.
    echo   The server stopped unexpectedly. The error is above.
    echo   A common cause is the app already running in another window.
    echo.
    pause
)
