param(
    [string]$PythonVersion = "3.13",
    [string]$PythonExe = "python",
    [string]$AppVersion = "",
    [switch]$RebuildExe
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$appName = "Dazzle"

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
    Write-Host "== Building application EXE ==" -ForegroundColor Cyan
    & "$projectRoot\build_exe.ps1" -PythonVersion $PythonVersion -PythonExe $PythonExe
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
    Get-ChildItem $outputDir -Filter "$appName-Setup-*.exe" -File -ErrorAction SilentlyContinue | Remove-Item -Force
}

Write-Host "== Building installer ==" -ForegroundColor Cyan
if (-not $AppVersion) {
    $AppVersion = Get-AppVersionFromSource
}
if (-not $AppVersion) {
    $AppVersion = "1.0.0"
}
Write-Host "Installer version: $AppVersion" -ForegroundColor DarkCyan
& $isccPath "/DAppVersion=$AppVersion" ".\installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Сборка установщика завершилась с ошибкой: $LASTEXITCODE"
}

$installer = Get-ChildItem $outputDir -Filter "$appName-Setup-*.exe" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $installer) {
    throw "Установщик не найден в папке: $outputDir"
}

Write-Host "== Done ==" -ForegroundColor Green
Write-Host "Installer file: $($installer.FullName)" -ForegroundColor Green
