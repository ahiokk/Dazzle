param(
    [string]$PythonVersion = "3.13",
    [string]$PythonExe = "python",
    [ValidateSet("auto255", "vag")]
    [string]$Edition = "auto255",
    [switch]$SkipDeps
)

# Сборка EXE для редакций на PySide6 (Windows 10/11):
#   auto255 -> dist\Dazzle\Dazzle.exe          (с вкладкой Ozon)
#   vag     -> dist\DazzleVAG\DazzleVAG.exe    (без Ozon)
# Редакция определяется в программе по имени exe (tirika_importer\version.py).
# Сборка Lastochka (Windows 7, PySide2) — отдельный скрипт build_exe_lastochka.ps1.

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if ($Edition -eq "vag") {
    $appName = "DazzleVAG"
}
else {
    $appName = "Dazzle"
}

$iconPath = Join-Path $projectRoot "assets\dazzle.ico"
$logoSvgPath = Join-Path $projectRoot "store-business-and-finance-svgrepo-com.svg"
$chevronSvgPath = Join-Path $projectRoot "chevron-down.svg"

# Свой рабочий каталог PyInstaller на редакцию — тогда сборки можно гонять параллельно.
$workPath = Join-Path $projectRoot "build\$appName"
$venvDir = Join-Path $projectRoot ".build_venv_py$($PythonVersion.Replace('.', ''))"
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

Write-Host "== Edition: $Edition (exe: $appName.exe) ==" -ForegroundColor Cyan

if (-not (Test-Path $venvPython)) {
    Write-Host "== Creating build virtual environment ==" -ForegroundColor Cyan
    New-BuildVenv
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось создать build venv"
    }
}

if ($SkipDeps) {
    Write-Host "== Skipping dependency install (-SkipDeps) ==" -ForegroundColor DarkCyan
}
else {
    Write-Host "== Installing build dependencies in venv ==" -ForegroundColor Cyan
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r .\requirements.txt pyinstaller
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось установить зависимости в build venv"
    }
}

Write-Host "== Cleaning old build folders ==" -ForegroundColor Cyan
# Чистим только свою редакцию, чтобы не сносить сборки остальных магазинов.
Remove-PathWithRetry $workPath
Remove-PathWithRetry ".\dist\$appName"
Remove-PathWithRetry ".\TirikaInvoiceImporter.spec"

Write-Host "== Building EXE ==" -ForegroundColor Cyan
$pyiArgs = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--uac-admin",
    "--name", $appName,
    "--workpath", $workPath,
    # Сгенерированный .spec кладём в рабочий каталог: в корне лежат свои,
    # с относительными путями, и их незачем перетирать абсолютными.
    "--specpath", $workPath,
    "--collect-all", "PySide6",
    "--collect-all", "shiboken6",
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

# theme.py ищет иконки рядом с пакетом (в сборке это _internal), иначе у выпадающих
# списков пропадает стрелка.
if (Test-Path $chevronSvgPath) {
    $pyiArgs += @("--add-data", "$chevronSvgPath;.")
}
else {
    Write-Host "Предупреждение: chevron-down.svg не найден ($chevronSvgPath)." -ForegroundColor Yellow
}

& $venvPython -m PyInstaller @pyiArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller завершился с ошибкой: $LASTEXITCODE"
}

Write-Host "== Done ==" -ForegroundColor Green
Write-Host "EXE folder: $projectRoot\dist\$appName" -ForegroundColor Green
Write-Host "Main file: $projectRoot\dist\$appName\$appName.exe" -ForegroundColor Green
