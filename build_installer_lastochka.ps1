param(
    [string]$PythonVersion = "3.8",
    [string]$PythonExe = "python",
    [string]$AppVersion = "",
    [switch]$RebuildExe,
    [switch]$SkipDeps
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$appName = "DazzleWin7"   # имя exe не меняем: на нём завязано автообновление
$setupPattern = "Dazzle-Lastochka-Win7-Setup-*.exe"

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

$exePath = Join-Path $projectRoot "dist\$appName\$appName.exe"
if ($RebuildExe -or -not (Test-Path $exePath)) {
    Write-Host "== Building Lastochka application EXE ==" -ForegroundColor Cyan
    & "$projectRoot\build_exe_lastochka.ps1" -PythonVersion $PythonVersion -PythonExe $PythonExe -SkipDeps:$SkipDeps
    if ($LASTEXITCODE -ne 0) {
        throw "Сборка Lastochka EXE завершилась с ошибкой: $LASTEXITCODE"
    }
}
else {
    Write-Host "== Reusing existing Lastochka EXE ==" -ForegroundColor Cyan
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

Write-Host "== Building Lastochka installer ==" -ForegroundColor Cyan
if (-not $AppVersion) {
    $AppVersion = Get-AppVersionFromSource
}
if (-not $AppVersion) {
    $AppVersion = "1.0.0"
}
Write-Host "Installer version: $AppVersion" -ForegroundColor DarkCyan
& $isccPath "/DAppVersion=$AppVersion" ".\installer_lastochka.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Сборка установщика Lastochka завершилась с ошибкой: $LASTEXITCODE"
}

$installer = Get-ChildItem $outputDir -Filter $setupPattern -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $installer) {
    throw "Установщик Lastochka не найден в папке: $outputDir"
}

Write-Host "== Done ==" -ForegroundColor Green
Write-Host "Installer file: $($installer.FullName)" -ForegroundColor Green
Write-Host "SHA256: $((Get-FileHash $installer.FullName -Algorithm SHA256).Hash.ToLower())" -ForegroundColor Green
