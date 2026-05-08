param(
    [string]$PythonVersion = "3.8",
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$appName = "DazzleWin7"
$iconPath = Join-Path $projectRoot "assets\dazzle.ico"
$logoSvgPath = Join-Path $projectRoot "store-business-and-finance-svgrepo-com.svg"

$venvDir = Join-Path $projectRoot ".build_venv_py$($PythonVersion.Replace('.', ''))_win7"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

function New-BuildVenv {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py "-$PythonVersion" -m venv $venvDir
    }
    else {
        & $PythonExe -m venv $venvDir
    }
}

function Remove-PathWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [int]$Attempts = 8,
        [int]$DelayMs = 500
    )

    if (-not (Test-Path $Path)) {
        return
    }

    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            Remove-Item $Path -Recurse -Force -ErrorAction Stop
            return
        }
        catch {
            if ($i -eq $Attempts) {
                throw "Не удалось удалить '$Path'. Закройте запущенный EXE/папку dist и повторите сборку. Детали: $($_.Exception.Message)"
            }
            Start-Sleep -Milliseconds $DelayMs
        }
    }
}

if (-not (Test-Path $venvPython)) {
    Write-Host "== Creating Win7 build virtual environment ==" -ForegroundColor Cyan
    New-BuildVenv
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось создать build venv для Win7"
    }
}

Write-Host "== Installing Win7 build dependencies in venv ==" -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r .\requirements.win7.txt pyinstaller==5.13.2
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось установить зависимости Win7 в build venv"
}

Write-Host "== Cleaning old Win7 build folders ==" -ForegroundColor Cyan
Remove-PathWithRetry ".\build"
Remove-PathWithRetry ".\dist\$appName"
Remove-PathWithRetry ".\$appName.spec"

Write-Host "== Building Win7 EXE ==" -ForegroundColor Cyan
$pyiArgs = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--uac-admin",
    "--name", $appName,
    "--collect-all", "PySide2",
    "--collect-all", "shiboken2",
    "--collect-submodules", "win32com",
    "--collect-submodules", "pythoncom",
    "--collect-submodules", "pywintypes",
    "--hidden-import", "win32timezone",
    "--exclude-module", "scipy",
    "--exclude-module", "pytest",
    "--exclude-module", "IPython",
    "--exclude-module", "matplotlib",
    "main.py"
)

if (Test-Path $iconPath) {
    $pyiArgs += @("--icon", $iconPath)
}
else {
    Write-Host "Предупреждение: иконка не найдена ($iconPath). Будет использована иконка по умолчанию." -ForegroundColor Yellow
}

if (Test-Path $logoSvgPath) {
    $pyiArgs += @("--add-data", "$logoSvgPath;.")
}
else {
    Write-Host "Предупреждение: SVG логотип не найден ($logoSvgPath)." -ForegroundColor Yellow
}

& $venvPython -m PyInstaller @pyiArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller (Win7) завершился с ошибкой: $LASTEXITCODE"
}

Write-Host "== Done ==" -ForegroundColor Green
Write-Host "EXE folder: $projectRoot\dist\$appName" -ForegroundColor Green
Write-Host "Main file: $projectRoot\dist\$appName\$appName.exe" -ForegroundColor Green
