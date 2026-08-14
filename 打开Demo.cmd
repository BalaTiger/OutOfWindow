@echo off
setlocal
cd /d "%~dp0"

if not exist "node_modules\electron\dist\electron.exe" (
  echo [Out of Window] First-time setup: installing dependencies...
  call npm.cmd install
  if errorlevel 1 goto :error
)

if not exist "dist\index.html" (
  echo [Out of Window] First-time setup: building the demo...
  call npm.cmd run build
  if errorlevel 1 goto :error
)

start "Out of Window" /B "node_modules\electron\dist\electron.exe" "."
exit /b 0

:error
echo.
echo Failed to prepare the demo. Please keep this window open and send the error above.
pause
exit /b 1
