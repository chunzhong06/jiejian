# Windows 便携版固定启动：只核对发行组件、建立本地运行目录并调用已安装 CLI。
[CmdletBinding()]
param([switch]$NoOpen, [ValidateRange(1, 65535)][int]$Port = 8765, [string]$ReopenEvent = "", [string]$VarDir = "", [switch]$FinishUpdate, [int]$ExitCode = 0)
$ErrorActionPreference = "Stop"
# 原生入口不经过 pwsh 的模块路径适配，只加载当前 Windows PowerShell 的系统模块。
$env:PSModulePath = [IO.Path]::Combine($PSHOME, 'Modules')
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$failureMessage = "发行组件不完整或版本不匹配，请重新解压完整发布包。"
$failureCode = 'PACKAGE_PATHS'
try {
    Write-Output "__JIEJIAN_RELEASE_STATUS__:validate"
    $releaseRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    $runtimeRoot = Join-Path $releaseRoot "runtime"
    $releasePath = Join-Path $PSScriptRoot "release.json"
    $pythonRoot = Join-Path $runtimeRoot "python"
    $python = Join-Path $pythonRoot "python.exe"
    $playwrightRoot = Join-Path $runtimeRoot "playwright"
    $frontend = Join-Path $PSScriptRoot "product\frontend\dist"
    if (-not $VarDir) { $VarDir = Join-Path $releaseRoot "var" }
    $varDir = [IO.Path]::GetFullPath($VarDir)
    $temporary = Join-Path $varDir "temp"
    $failureCode = 'PACKAGE_FILES'
    foreach ($required in @($releasePath, $python, (Join-Path $frontend "index.html"), (Join-Path $runtimeRoot "node\node.exe"))) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "PACKAGE_FILE_MISSING" }
    }
    $failureCode = 'PACKAGE_LAYOUT'
    $release = Get-Content -LiteralPath $releasePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$release.schema_version -ne "3" -or [string]$release.product -ne "JieJian Web V1" -or [string]$release.platform -ne "windows" -or [string]$release.architecture -ne "x64" -or [string]$release.runtime_layout_version -ne "3") { throw "PACKAGE_LAYOUT_INVALID" }
    $failureCode = 'PACKAGE_NODE'
    if ((Get-FileHash -LiteralPath (Join-Path $runtimeRoot "node\node.exe") -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$release.node_sha256) { throw "PACKAGE_NODE_INVALID" }
    $failureCode = 'PACKAGE_BROWSER'
    $chromium = @(Get-ChildItem -LiteralPath $playwrightRoot -Recurse -Filter "chrome.exe" -File | Where-Object { $_.FullName -match "[\\/]chromium-[^\\/]+[\\/]chrome-win[^\\/]*[\\/]chrome\.exe$" })
    if ($chromium.Count -ne 1) { throw "PACKAGE_BROWSER_INVALID" }
    $failureCode = 'PACKAGE_LAUNCHER'
    if ($ReopenEvent -and $ReopenEvent -cnotmatch '^Local\\JieJian-Reopen-[0-9a-f]{16}$') { throw "PACKAGE_LAUNCHER_INVALID" }

    $failureMessage = "发行目录无法写入。请把整个界鉴目录放到可写位置后启动。"
    $failureCode = 'WORKSPACE_WRITE'
    New-Item -ItemType Directory -Path $temporary -Force | Out-Null
    $env:JIEJIAN_PYTHON_EXECUTABLE = [IO.Path]::GetFullPath($python)
    $env:JIEJIAN_PYTHON_ENVIRONMENT_PATH = [IO.Path]::GetFullPath($pythonRoot)
    $env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE = "uv-managed"
    $env:JIEJIAN_RELEASE_ROOT = $releaseRoot
    $env:JIEJIAN_RUNTIME_MODE = "portable"
    $env:JIEJIAN_VAR_DIR = [IO.Path]::GetFullPath($varDir)
    $env:JIEJIAN_FRONTEND_DIST = [IO.Path]::GetFullPath($frontend)
    $env:JIEJIAN_NODE_EXECUTABLE = [IO.Path]::GetFullPath((Join-Path $runtimeRoot "node\node.exe"))
    $env:JIEJIAN_NODE_VERSION = [string]$release.node_version
    $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE = [IO.Path]::GetFullPath($chromium[0].FullName)
    $env:PLAYWRIGHT_BROWSERS_PATH = [IO.Path]::GetFullPath($playwrightRoot)
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONNOUSERSITE = "1"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:TEMP = [IO.Path]::GetFullPath($temporary)
    $env:TMP = [IO.Path]::GetFullPath($temporary)
    # Agent 使用用户已安装的客户端；先保留准确入口，目标 Worker 仍只继承冻结环境。
    $codexCommand = Get-Command codex.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($codexCommand) { $env:JIEJIAN_CODEX_EXECUTABLE = $codexCommand.Source }
    $env:PATH = "$pythonRoot;$env:SystemRoot\System32"
    foreach ($name in @("PYTHONHOME", "PYTHONPATH", "JIEJIAN_PROJECT_ROOT", "JIEJIAN_RUNTIME_FINGERPRINT", "JIEJIAN_SERVE_LOCK_PATH", "JIEJIAN_SERVE_OWNER_TOKEN")) {
        Remove-Item -LiteralPath ("Env:" + $name) -ErrorAction SilentlyContinue
    }
    Set-Location -LiteralPath $varDir
    if ($FinishUpdate) {
        & $python -B -m product.backend.infrastructure.runtime.updates --var-dir $varDir --release-root $releaseRoot --exit-code $ExitCode
        exit $LASTEXITCODE
    }
    Write-Output "__JIEJIAN_RELEASE_STATUS__:identity"
    $failureMessage = "包内 Python 或产品版本校验失败，请重新解压匹配版本的完整发布包。"
    $failureCode = 'RUNTIME_IDENTITY'
    $identityProbe = "import importlib.metadata,json; from product.backend import __version__; from product.backend.infrastructure.runtime.process.controlled.identity import python_environment_report; r=python_environment_report(); assert r['ok']; print(json.dumps({'fingerprint':r['runtime_fingerprint'],'version':__version__,'package_version':importlib.metadata.version('jiejian')}))"
    $identity = (& $python -B -c $identityProbe | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "PACKAGE_IDENTITY_INVALID" }
    $identity = $identity | ConvertFrom-Json
    if ($identity.fingerprint -notmatch '^[0-9a-f]{64}$' -or $identity.version -ne $release.version -or $identity.package_version -ne $release.package_version -or $release.version -ne $release.package_version) { throw "PACKAGE_VERSION_INVALID" }
    $env:JIEJIAN_RUNTIME_FINGERPRINT = $identity.fingerprint

    $failureMessage = "端口 $Port 已被占用，请关闭占用该端口的程序，或使用 --port 指定空闲端口。"
    $failureCode = 'PORT_BUSY'
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
    try { $listener.Start() } finally { $listener.Stop() }
    $failureMessage = "界鉴服务未能启动，请查看 var\logs 中的运行日志。"
    $failureCode = 'SERVICE_START'
    Write-Output "__JIEJIAN_RELEASE_STATUS__:serve"
    $arguments = @("-B", "-m", "product.backend.interfaces.cli", "--var-dir", $varDir, "serve", "--host", "127.0.0.1", "--port", [string]$Port, "--frontend-dir", $frontend)
    $sampleRoot = Join-Path $releaseRoot "samples\digital_gallery"
    if (Test-Path -LiteralPath (Join-Path $sampleRoot "sample.json") -PathType Leaf) { $arguments += @("--official-sample-root", $sampleRoot) }
    if ($NoOpen) { $arguments += "--no-open" } else { $arguments += "--open" }
    if ($ReopenEvent) { $arguments += @("--launcher-event", $ReopenEvent) }
    & $python @arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) { Write-Output ("__JIEJIAN_RELEASE_ERROR__:" + $failureMessage) }
    exit $code
} catch {
    Write-Output ("__JIEJIAN_RELEASE_ERROR__:" + $failureMessage + ' [' + $failureCode + ']')
    exit 1
}
