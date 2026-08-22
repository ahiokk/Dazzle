@echo off
setlocal

powershell -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1" -Edition vag -RebuildExe %*
if errorlevel 1 (
    echo.
    echo VAG installer build failed.
    pause
    exit /b 1
)

echo.
echo VAG installer build completed.
pause
