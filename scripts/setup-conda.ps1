[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$environmentName = "jiejian_env"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$environmentFile = Join-Path $projectRoot "environment.yml"
$condaExecutable = (Get-Command conda -ErrorAction Stop).Source

$environmentListText = & $condaExecutable env list --json
if ($LASTEXITCODE -ne 0) {
    throw "无法读取 Conda 环境列表"
}
$environmentList = $environmentListText | ConvertFrom-Json
$environmentPrefix = $environmentList.envs |
    Where-Object { (Split-Path -Leaf $_) -eq $environmentName } |
    Select-Object -First 1

if (-not $environmentPrefix) {
    & $condaExecutable env create --file $environmentFile
    if ($LASTEXITCODE -ne 0) {
        throw "创建 Conda 环境 $environmentName 失败"
    }
    $environmentListText = & $condaExecutable env list --json
    if ($LASTEXITCODE -ne 0) {
        throw "创建后无法读取 Conda 环境列表"
    }
    $environmentList = $environmentListText | ConvertFrom-Json
    $environmentPrefix = $environmentList.envs |
        Where-Object { (Split-Path -Leaf $_) -eq $environmentName } |
        Select-Object -First 1
}

if (-not $environmentPrefix) {
    throw "未找到 Conda 环境 $environmentName"
}
$environmentPrefix = (Resolve-Path -LiteralPath $environmentPrefix).Path
$pythonExecutable = Join-Path $environmentPrefix "python.exe"
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw "Conda 环境缺少 Python：$pythonExecutable"
}

$previousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
Push-Location $projectRoot
try {
    $env:PYTHONDONTWRITEBYTECODE = "1"
    & $condaExecutable run --no-capture-output --name $environmentName `
        python -B -m pip install --group dev --editable .
    if ($LASTEXITCODE -ne 0) {
        throw "pip 项目依赖安装失败"
    }
    & $condaExecutable run --no-capture-output --name $environmentName `
        python -B -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        throw "Playwright Chromium 安装失败"
    }
    & $condaExecutable run --no-capture-output --name $environmentName `
        python -B -c "from pathlib import Path; import alembic, httpx, jiejian, playwright, pydantic, pytest, sqlalchemy, typer, yaml; from playwright.sync_api import sync_playwright; p = sync_playwright().start(); executable = Path(p.chromium.executable_path); p.stop(); assert executable.is_file(); print('jiejian_env ready')"
    if ($LASTEXITCODE -ne 0) {
        throw "Conda 环境导入验证失败"
    }
}
finally {
    if ($null -eq $previousBytecodeSetting) {
        Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONDONTWRITEBYTECODE = $previousBytecodeSetting
    }
    Pop-Location
}

Write-Host "环境已就绪。请执行：conda activate $environmentName"
