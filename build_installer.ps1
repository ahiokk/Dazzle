param(
    [string]$PythonVersion = "3.13",
    [string]$PythonExe = "python",
    [string]$AppVersion = "",
    [ValidateSet("auto255", "vag")]
    [string]$Edition = "auto255",
    [switch]$RebuildExe,
    [switch]$SkipDeps
)

# Установщики редакций на PySide6 (Windows 10/11):
#   auto255 -> installer_output\Dazzle-Setup-<version>.exe
#   vag     -> installer_output\Dazzle-VAG-Setup-<version>.exe
# Lastochka (Windows 7) собирается скриптом build_installer_lastochka.ps1.

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if ($Edition -eq "vag") {
    $appName = "DazzleVAG"
    $issFile = ".\installer_vag.iss"
    $setupPattern = "Dazzle-VAG-Win10-Setup-*.exe"
}
else {
    $appName = "Dazzle"
    $issFile = ".\installer.iss"
    $setupPattern = "Dazzle-AUTO255-Win10-Setup-*.exe"
}

function Get-AppVersionFromSource {
    $versionFile = Join-Path $projectRoot "tirika_importer\version.py"
    if (-not (Test-Path $versionFile)) {
        return ""
    }
    $content = Get-Content $versionFile -Raw -Encoding UTF8
    $m = [regex]::Match($content, "APP_VERSION\s*=\s*['""]([^'""]+)['""]")
    if ($m.Success) {
        return $m.Groups[1].Value.Trim()
    }
    return ""
}

function Get-IsccPath {
    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $roots = @(
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)},
        (Join-Path $env:LOCALAPPDATA "Programs")
    ) | Where-Object { $_ }

    foreach ($root in $roots) {
        $candidate = Join-Path $root "Inno Setup 6\ISCC.exe"
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

Write-Host "== Edition: $Edition ==" -ForegroundColor Cyan

$exePath = Join-Path $projectRoot "dist\$appName\$appName.exe"
if ($RebuildExe -or -not (Test-Path $exePath)) {
    Write-Host "== Building application EXE ==" -ForegroundColor Cyan
    & "$projectRoot\build_exe.ps1" -PythonVersion $PythonVersion -PythonExe $PythonExe -Edition $Edition -SkipDeps:$SkipDeps
    if ($LASTEXITCODE -ne 0) {
        throw "Сборка EXE завершилась с ошибкой: $LASTEXITCODE"
    }
}
else {
    Write-Host "== Reusing existing EXE ==" -ForegroundColor Cyan
    Write-Host "Path: $exePath" -ForegroundColor DarkCyan
}

$isccPath = Get-IsccPath
if (-not $isccPath) {
    throw "Не найден ISCC.exe (Inno Setup 6). Установите Inno Setup и повторите."
}

$outputDir = Join-Path $projectRoot "installer_output"
if (Test-Path $outputDir) {
    Get-ChildItem $outputDir -Filter $setupPattern -File -ErrorAction SilentlyContinue | Remove-Item -Force
}

Write-Host "== Building installer ==" -ForegroundColor Cyan
if (-not $AppVersion) {
    $AppVersion = Get-AppVersionFromSource
}
if (-not $AppVersion) {
    $AppVersion = "1.0.0"
}
Write-Host "Installer version: $AppVersion" -ForegroundColor DarkCyan
& $isccPath "/DAppVersion=$AppVersion" $issFile
if ($LASTEXITCODE -ne 0) {
    throw "Сборка установщика завершилась с ошибкой: $LASTEXITCODE"
}

$installer = Get-ChildItem $outputDir -Filter $setupPattern -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $installer) {
    throw "Установщик не найден в папке: $outputDir"
}

Write-Host "== Done ==" -ForegroundColor Green
Write-Host "Installer file: $($installer.FullName)" -ForegroundColor Green
Write-Host "SHA256: $((Get-FileHash $installer.FullName -Algorithm SHA256).Hash.ToLower())" -ForegroundColor Green
