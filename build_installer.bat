@echo off
setlocal

powershell -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1" %*
if errorlevel 1 (
    echo.
    echo Installer build failed.
    pause
    exit /b 1
)

echo.
echo Installer build completed.
pause
