#Requires -Version 5.1
# =============================================================================
# 界鉴仓库开发入口
#
# 定位
#   全局项目专用 Conda 环境、冻结 uv 依赖与仓库源码之间的唯一开发编排入口
#
# 职责
#   创建或更新 Python 基线｜冻结同步 editable 项目｜开发启动/测试/交互/发布构建
#
# 边界
#   只有 update 可以改写 uv.lock；不修改用户 PATH、PowerShell Profile 或仓库外环境。
# =============================================================================

[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet("bootstrap", "sync", "update", "start", "test", "shell", "package")]
    [string]$Command = "start",
    [string]$VarDir = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments = @()
)

$ErrorActionPreference = "Stop"
$script:ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$script:VarDir = if ([string]::IsNullOrWhiteSpace($VarDir)) {
    Join-Path $script:ProjectRoot "var"
} elseif ([IO.Path]::IsPathRooted($VarDir)) {
    [IO.Path]::GetFullPath($VarDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot $VarDir))
}
$script:ToolchainPath = Join-Path $script:ProjectRoot "product\config\toolchain.json"
$script:EnvironmentPath = Join-Path $script:ProjectRoot "environment.yml"
$script:StatePath = Join-Path $script:VarDir "cache\startup\development-state.json"
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:PrepareLock = $null
$script:Python = $null
$script:Conda = $null
$script:CondaPrefix = $null
$script:Uv = $null
$script:UvVersion = $null
$script:Node = $null
$script:NodeVersion = $null
$script:PnpmRunner = @()
$script:PnpmVersion = $null
$script:State = [pscustomobject]@{ schema_version = "1" }
$script:OriginalPath = $env:PATH

function Fail-Development([string]$Stage, [string]$Message, [string]$Recovery) {
    Write-Host ""
    Write-Host ("开发环境失败：{0}" -f $Stage) -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    Write-Host ("建议：{0}" -f $Recovery) -ForegroundColor Yellow
    throw $Message
}

function Invoke-External([string]$Stage, [string[]]$Invocation) {
    if ($Invocation.Count -lt 1) { Fail-Development $Stage "缺少外部命令" "检查开发脚本参数" }
    $executable = $Invocation[0]
    [string[]]$arguments = if ($Invocation.Count -gt 1) { @($Invocation[1..($Invocation.Count - 1)]) } else { @() }
    & $executable @arguments
    if ($LASTEXITCODE -ne 0) {
        Fail-Development $Stage ("外部命令返回 {0}" -f $LASTEXITCODE) "修复上方错误后重试同一命令"
    }
}

function Get-FileDigest([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-CombinedDigest([string[]]$Paths) {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($path in ($Paths | Sort-Object)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $null = $lines.Add(("{0}|{1}" -f [IO.Path]::GetFullPath($path), (Get-FileDigest $path)))
        }
    }
    $bytes = $script:Utf8NoBom.GetBytes(($lines -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Enter-PrepareLock {
    $lockPath = Join-Path $script:VarDir "runtime\locks\prepare.lock"
    New-Item -ItemType Directory -Path (Split-Path -Parent $lockPath) -Force | Out-Null
    try {
        $script:PrepareLock = [IO.File]::Open(
            $lockPath,
            [IO.FileMode]::OpenOrCreate,
            [IO.FileAccess]::ReadWrite,
            [IO.FileShare]::None
        )
    } catch [IO.IOException] {
        Fail-Development "prepare-lock" "另一个界鉴准备进程正在修改运行环境" "等待另一进程完成后重试"
    }
}

function Exit-PrepareLock {
    if ($null -ne $script:PrepareLock) {
        $script:PrepareLock.Dispose()
        $script:PrepareLock = $null
    }
}

function Read-State {
    if (-not (Test-Path -LiteralPath $script:StatePath -PathType Leaf)) { return }
    try {
        $value = Get-Content -LiteralPath $script:StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($value.schema_version -eq "1") { $script:State = $value }
    } catch {
        $script:State = [pscustomobject]@{ schema_version = "1" }
    }
}

function Get-StateValue([string]$Name) {
    $property = $script:State.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Set-StateValue([string]$Name, [object]$Value) {
    $script:State | Add-Member -MemberType NoteProperty -Name $Name -Value $Value -Force
}

function Save-State {
    $directory = Split-Path -Parent $script:StatePath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = Join-Path $directory ("development-state-{0}.tmp" -f [guid]::NewGuid().ToString("N"))
    $backup = Join-Path $directory ("development-state-{0}.bak" -f [guid]::NewGuid().ToString("N"))
    [IO.File]::WriteAllText($temporary, ($script:State | ConvertTo-Json -Depth 8 -Compress), $script:Utf8NoBom)
    try {
        if (Test-Path -LiteralPath $script:StatePath -PathType Leaf) {
            [IO.File]::Replace([string]$temporary, [string]$script:StatePath, [string]$backup, $true)
        } else {
            [IO.File]::Move([string]$temporary, [string]$script:StatePath)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
}

function Read-Toolchain {
    try {
        $toolchain = Get-Content -LiteralPath $script:ToolchainPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($toolchain.schema_version -ne "1") { throw "unsupported toolchain schema" }
        return $toolchain
    } catch {
        Fail-Development "toolchain" "无法读取唯一工具链清单" "恢复 product/config/toolchain.json 后重试"
    }
}

function Resolve-CondaPrefix([bool]$RequireExisting) {
    $command = Get-Command conda -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        Fail-Development "conda" "未找到 Conda" "安装或修复 Miniconda/Conda 后执行 scripts/dev.ps1 bootstrap"
    }
    $script:Conda = $command.Source
    $raw = & $script:Conda env list --json 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { Fail-Development "conda" "无法读取 Conda 环境列表" "修复 Conda 后重试" }
    try { $environments = @(($raw | ConvertFrom-Json).envs) }
    catch { Fail-Development "conda" "Conda 环境列表不是有效 JSON" "修复 Conda 后重试" }
    $prefix = $environments | Where-Object { (Split-Path -Leaf ([string]$_)) -eq "jiejian_env" } | Select-Object -First 1
    if ($RequireExisting -and [string]::IsNullOrWhiteSpace([string]$prefix)) {
        Fail-Development "conda" "尚未创建 jiejian_env" "执行 .\scripts\dev.ps1 bootstrap"
    }
    return [string]$prefix
}

function Test-CondaPython([string]$Prefix) {
    if ([string]::IsNullOrWhiteSpace($Prefix)) { return $false }
    $python = Join-Path $Prefix "python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { return $false }
    # Python 基线探针不加载 site；项目依赖半同步时仍应由后续 uv sync 自动修复。
    & $python -S -B -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" 2>$null
    return $LASTEXITCODE -eq 0
}

function Ensure-Conda([ValidateSet("auto", "force", "existing")][string]$Mode) {
    $prefix = Resolve-CondaPrefix ($Mode -eq "existing")
    $environmentDigest = Get-FileDigest $script:EnvironmentPath
    $stateDigest = [string](Get-StateValue "environment_digest")
    $ready = Test-CondaPython $prefix
    $mustUpdate = $Mode -eq "force" -or -not $ready -or $stateDigest -ne $environmentDigest
    if ($Mode -eq "existing" -and $mustUpdate) {
        Fail-Development "conda" "environment.yml 已变化或 Python 基线探针失败" "执行 .\scripts\dev.ps1 bootstrap"
    }
    if ([string]::IsNullOrWhiteSpace($prefix)) {
        Write-Host "正在创建 jiejian_env Python 基线……" -ForegroundColor Cyan
        Invoke-External "conda" @($script:Conda, "env", "create", "--file", $script:EnvironmentPath)
        $prefix = Resolve-CondaPrefix $true
    } elseif ($mustUpdate -and $Mode -ne "existing") {
        Write-Host "正在更新 jiejian_env Python 基线……" -ForegroundColor Cyan
        Invoke-External "conda" @($script:Conda, "env", "update", "--name", "jiejian_env", "--file", $script:EnvironmentPath, "--prune")
        $prefix = Resolve-CondaPrefix $true
    } elseif (-not $ready) {
        Fail-Development "conda" "jiejian_env 的 Python 基线不符合 3.13" "执行 .\scripts\dev.ps1 bootstrap"
    }
    if (-not (Test-CondaPython $prefix)) {
        Fail-Development "conda" "Conda 更新后仍未获得 CPython 3.13" "检查 environment.yml 与 Conda 输出"
    }
    $script:CondaPrefix = [IO.Path]::GetFullPath($prefix)
    $script:Python = Join-Path $script:CondaPrefix "python.exe"
    Set-StateValue "environment_digest" $environmentDigest
}

function Resolve-Uv($Toolchain) {
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    $key = switch ($architecture.ToUpperInvariant()) { "AMD64" { "x64" } "ARM64" { "arm64" } default { $null } }
    if ($null -eq $key) { Fail-Development "uv" "当前 Windows 架构不受支持" "使用 AMD64 或 ARM64 Windows" }
    $metadata = $Toolchain.uv.windows.$key
    $version = [string]$Toolchain.uv.version
    $install = Join-Path $script:VarDir ("runtime\uv\{0}\{1}" -f $version, $key)
    $executable = Join-Path $install "uv.exe"
    $receipt = Join-Path $install "receipt.json"
    $healthy = $false
    if ((Test-Path -LiteralPath $executable -PathType Leaf) -and (Test-Path -LiteralPath $receipt -PathType Leaf)) {
        try {
            $record = Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
            $healthy = $record.archive_sha256 -eq [string]$metadata.sha256 -and
                $record.executable_sha256 -eq (Get-FileDigest $executable)
        } catch { $healthy = $false }
    }
    if (-not $healthy) {
        New-Item -ItemType Directory -Path $install -Force | Out-Null
        $downloadRoot = Join-Path $script:VarDir ("temp\downloads\uv-{0}" -f [guid]::NewGuid().ToString("N"))
        $partial = Join-Path $script:VarDir ("cache\downloads\.tmp-{0}-{1}" -f [guid]::NewGuid().ToString("N"), [string]$metadata.asset)
        New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
        New-Item -ItemType Directory -Path (Split-Path -Parent $partial) -Force | Out-Null
        try {
            $uri = "https://github.com/astral-sh/uv/releases/download/{0}/{1}" -f $version, [string]$metadata.asset
            Invoke-WebRequest -Uri $uri -OutFile $partial -UseBasicParsing
            if ((Get-FileDigest $partial) -ne [string]$metadata.sha256) {
                Fail-Development "uv" "uv 归档 SHA-256 校验失败" "删除 var/cache/downloads 后重试"
            }
            Expand-Archive -LiteralPath $partial -DestinationPath $downloadRoot -Force
            $candidate = Get-ChildItem -LiteralPath $downloadRoot -Recurse -Filter "uv.exe" -File | Select-Object -First 1
            if ($null -eq $candidate) { Fail-Development "uv" "uv 归档缺少可执行文件" "重新下载固定 uv 归档" }
            Copy-Item -LiteralPath $candidate.FullName -Destination $executable -Force
            $payload = [ordered]@{
                schema_version = "1"
                version = $version
                archive_sha256 = [string]$metadata.sha256
                executable_sha256 = Get-FileDigest $executable
            }
            [IO.File]::WriteAllText($receipt, ($payload | ConvertTo-Json -Compress), $script:Utf8NoBom)
        } finally {
            Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    $actual = (& $executable --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -notmatch ("^uv\s+" + [regex]::Escape($version) + "(\s|$)")) {
        Fail-Development "uv" "受控 uv 版本不符合工具链清单" "执行 .\scripts\dev.ps1 bootstrap 重建运行时"
    }
    $script:Uv = [IO.Path]::GetFullPath($executable)
    $script:UvVersion = $version
}

function Set-DevelopmentEnvironment {
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONNOUSERSITE = "1"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    $env:UV_PROJECT_ENVIRONMENT = $script:CondaPrefix
    $env:UV_CACHE_DIR = Join-Path $script:VarDir "cache\uv"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $script:VarDir "runtime\python\installations"
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $script:VarDir "runtime\playwright\development"
    $env:JIEJIAN_VAR_DIR = $script:VarDir
    $env:JIEJIAN_PROJECT_ROOT = $script:ProjectRoot
    $env:JIEJIAN_RUNTIME_MODE = "development"
    $env:JIEJIAN_PYTHON_EXECUTABLE = $script:Python
    $env:JIEJIAN_PYTHON_ENVIRONMENT_PATH = $script:CondaPrefix
    $env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE = "conda"
    $env:JIEJIAN_UV_EXECUTABLE = $script:Uv
    $env:JIEJIAN_UV_VERSION = $script:UvVersion
    $env:JIEJIAN_TOOLCHAIN_MANIFEST = $script:ToolchainPath
}

function Read-DevelopmentIdentity {
    Remove-Item Env:JIEJIAN_RUNTIME_FINGERPRINT -ErrorAction SilentlyContinue
    $probe = "import json; from product.backend.infra.runtime.environment_identity import python_environment_report; print(json.dumps(python_environment_report(), ensure_ascii=False))"
    $raw = (& $script:Python -B -c $probe 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return $null }
    try { return $raw | ConvertFrom-Json } catch { return $null }
}

function Confirm-DevelopmentIdentity {
    $report = Read-DevelopmentIdentity
    if ($null -eq $report) {
        Fail-Development "python-identity" "无法读取 Python 环境身份" "执行 .\scripts\dev.ps1 sync"
    }
    if (-not $report.ok) {
        Fail-Development "python-identity" ("Python 环境来源异常：" + (@($report.issues) -join "；")) "执行 .\scripts\dev.ps1 bootstrap"
    }
    $env:JIEJIAN_RUNTIME_FINGERPRINT = [string]$report.runtime_fingerprint
    & $script:Python -B -c "from product.backend.infra.runtime.environment_identity import require_python_environment; require_python_environment()" 2>$null
    if ($LASTEXITCODE -ne 0) { Fail-Development "python-identity" "主进程环境指纹复核失败" "执行 .\scripts\dev.ps1 sync" }
    Set-StateValue "runtime_fingerprint" $env:JIEJIAN_RUNTIME_FINGERPRINT
}

function Sync-Project([bool]$ForceSync) {
    $syncDigest = Get-CombinedDigest @(
        (Join-Path $script:ProjectRoot "pyproject.toml"),
        (Join-Path $script:ProjectRoot "uv.lock")
    )
    Push-Location -LiteralPath $script:ProjectRoot
    try {
        Invoke-External "uv-lock" @($script:Uv, "lock", "--check")
        $stateDigest = [string](Get-StateValue "sync_digest")
        $identity = if ($stateDigest -eq $syncDigest) { Read-DevelopmentIdentity } else { $null }
        if ($ForceSync -or $stateDigest -ne $syncDigest -or $null -eq $identity -or -not $identity.ok) {
            Write-Host "正在按 uv.lock 精确同步项目依赖……" -ForegroundColor Cyan
            Invoke-External "uv-sync" @($script:Uv, "sync", "--frozen", "--all-groups")
            Set-StateValue "sync_digest" $syncDigest
        } else {
            Write-Host "Python 依赖指纹未变化，复用 jiejian_env。" -ForegroundColor DarkGray
        }
    } finally { Pop-Location }
    Confirm-DevelopmentIdentity
    Save-State
}

function Prepare-Python([ValidateSet("auto", "bootstrap", "sync")][string]$Mode) {
    $toolchain = Read-Toolchain
    if ($Mode -eq "bootstrap") { Ensure-Conda "force" }
    elseif ($Mode -eq "sync") { Ensure-Conda "existing" }
    else { Ensure-Conda "auto" }
    Resolve-Uv $toolchain
    Set-DevelopmentEnvironment
    Sync-Project ($Mode -in @("bootstrap", "sync"))
    return $toolchain
}

function Prepare-Chromium {
    $probe = "from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); x=Path(p.chromium.executable_path).resolve(); p.stop(); print(x); raise SystemExit(0 if x.is_file() else 1)"
    $path = (& $script:Python -B -c $probe 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($path)) {
        Write-Host "正在准备 Playwright Chromium……" -ForegroundColor Cyan
        Invoke-External "playwright" @($script:Python, "-B", "-m", "playwright", "install", "chromium")
        $path = (& $script:Python -B -c $probe 2>$null | Out-String).Trim()
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Fail-Development "playwright" "Chromium 可执行文件探针失败" "检查网络和 var/runtime/playwright 后重试"
    }
    $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE = [IO.Path]::GetFullPath($path)
}

function Resolve-DevelopmentNode($Toolchain, [bool]$Exact) {
    if ($Exact) {
        $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
        $key = switch ($architecture.ToUpperInvariant()) {
            "AMD64" { "x64" }
            "ARM64" { "arm64" }
            default { $null }
        }
        if ($null -eq $key) {
            Fail-Development "frontend" "当前 Windows 架构不受发布构建工具链支持" "使用 AMD64 或 ARM64 Windows"
        }
        $nodeVersion = [string]$Toolchain.node.build_version
        $pnpmVersion = [string]$Toolchain.pnpm.version
        $nodeRoot = Join-Path $script:VarDir ("runtime\build\node\{0}\{1}" -f $nodeVersion, $key)
        $nodeExecutable = Join-Path $nodeRoot ("node-v{0}-win-{1}\node.exe" -f $nodeVersion, $key)
        $pnpmRoot = Join-Path $script:VarDir ("runtime\build\pnpm\{0}" -f $pnpmVersion)
        $pnpmEntry = Join-Path $pnpmRoot "package\bin\pnpm.cjs"
        $receiptPath = Join-Path $script:VarDir "runtime\build\toolchain-receipt.json"
        $hashProperty = "{0}_sha256" -f $key
        $expectedNodeHash = [string]$Toolchain.node.windows.PSObject.Properties[$hashProperty].Value
        $healthy = $false
        if ((Test-Path -LiteralPath $nodeExecutable -PathType Leaf) -and
            (Test-Path -LiteralPath $pnpmEntry -PathType Leaf) -and
            (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
            try {
                $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $healthy = $receipt.node_version -eq $nodeVersion -and
                    $receipt.pnpm_version -eq $pnpmVersion -and
                    $receipt.node_executable_sha256 -eq (Get-FileDigest $nodeExecutable) -and
                    $receipt.pnpm_entry_sha256 -eq (Get-FileDigest $pnpmEntry)
            } catch { $healthy = $false }
        }
        if (-not $healthy) {
            $downloadRoot = Join-Path $script:VarDir ("temp\downloads\build-toolchain-{0}" -f [guid]::NewGuid().ToString("N"))
            $nodeArchive = Join-Path $downloadRoot ("node-v{0}-win-{1}.zip" -f $nodeVersion, $key)
            $pnpmArchive = Join-Path $downloadRoot ("pnpm-{0}.tgz" -f $pnpmVersion)
            New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
            try {
                Invoke-WebRequest -Uri ("{0}node-v{1}-win-{2}.zip" -f [string]$Toolchain.node.source, $nodeVersion, $key) -OutFile $nodeArchive -UseBasicParsing
                if ((Get-FileDigest $nodeArchive) -ne $expectedNodeHash) {
                    Fail-Development "frontend" "Node.js 发布构建归档校验失败" "检查 product/config/toolchain.json 与官方下载源"
                }
                Invoke-WebRequest -Uri ([string]$Toolchain.pnpm.source) -OutFile $pnpmArchive -UseBasicParsing
                $sha512 = [Security.Cryptography.SHA512]::Create()
                try { $pnpmIntegrity = "sha512-" + [Convert]::ToBase64String($sha512.ComputeHash([IO.File]::ReadAllBytes($pnpmArchive))) }
                finally { $sha512.Dispose() }
                if ($pnpmIntegrity -ne [string]$Toolchain.pnpm.integrity) {
                    Fail-Development "frontend" "pnpm 发布构建归档完整性校验失败" "检查 product/config/toolchain.json 与 npm 官方归档"
                }
                Remove-Item -LiteralPath $nodeRoot -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item -LiteralPath $pnpmRoot -Recurse -Force -ErrorAction SilentlyContinue
                New-Item -ItemType Directory -Path $nodeRoot -Force | Out-Null
                New-Item -ItemType Directory -Path $pnpmRoot -Force | Out-Null
                Expand-Archive -LiteralPath $nodeArchive -DestinationPath $nodeRoot -Force
                & tar.exe -xzf $pnpmArchive -C $pnpmRoot
                if ($LASTEXITCODE -ne 0) {
                    Fail-Development "frontend" "无法展开固定 pnpm 归档" "确认 Windows tar.exe 可用后重试"
                }
                if (-not (Test-Path -LiteralPath $nodeExecutable -PathType Leaf) -or -not (Test-Path -LiteralPath $pnpmEntry -PathType Leaf)) {
                    Fail-Development "frontend" "发布构建工具归档缺少预期入口" "删除 var/runtime/build 后重试"
                }
                $receipt = [ordered]@{
                    schema_version = "1"
                    node_version = $nodeVersion
                    pnpm_version = $pnpmVersion
                    node_archive_sha256 = $expectedNodeHash
                    pnpm_integrity = $pnpmIntegrity
                    node_executable_sha256 = Get-FileDigest $nodeExecutable
                    pnpm_entry_sha256 = Get-FileDigest $pnpmEntry
                }
                New-Item -ItemType Directory -Path (Split-Path -Parent $receiptPath) -Force | Out-Null
                [IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Compress), $script:Utf8NoBom)
            } finally {
                Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        $script:Node = [IO.Path]::GetFullPath($nodeExecutable)
        $script:PnpmRunner = @($script:Node, [IO.Path]::GetFullPath($pnpmEntry))
        $script:NodeVersion = (& $script:Node --version 2>&1 | Out-String).Trim().TrimStart("v")
        $script:PnpmVersion = (& $script:PnpmRunner[0] $script:PnpmRunner[1] --version 2>&1 | Out-String).Trim()
        if ($script:NodeVersion -ne $nodeVersion -or $script:PnpmVersion -ne $pnpmVersion) {
            Fail-Development "frontend" "固定发布构建工具版本探针失败" "删除 var/runtime/build 后重新执行 package"
        }
        $env:PATH = (Split-Path -Parent $script:Node) + ";" + $script:OriginalPath
        $env:JIEJIAN_NODE_EXECUTABLE = $script:Node
        $env:JIEJIAN_NODE_VERSION = $script:NodeVersion
        $env:JIEJIAN_PNPM_EXECUTABLE = $script:PnpmRunner[1]
        $env:JIEJIAN_PNPM_VERSION = $script:PnpmVersion
        return
    }

    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    $pnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $node -or $null -eq $pnpm) {
        Fail-Development "frontend" "开发前端需要 Node.js 与 pnpm" "安装满足 package.json 的 Node.js 和 pnpm，或执行发布构建准备"
    }
    $nodeVersion = (& $node.Source --version 2>&1 | Out-String).Trim().TrimStart("v")
    $pnpmVersion = (& $pnpm.Source --version 2>&1 | Out-String).Trim()
    try { $parsed = [version]$nodeVersion } catch { $parsed = $null }
    $nodeOk = $null -ne $parsed -and $parsed -ge [version]"24.13.0" -and $parsed.Major -lt 25
    if (-not $nodeOk -or $pnpmVersion -ne [string]$Toolchain.pnpm.version) {
        Fail-Development "frontend" "Node/pnpm 版本不符合工具链清单" ("需要 Node {0} 与 pnpm {1}" -f $Toolchain.node.development_range, $Toolchain.pnpm.version)
    }
    $script:Node = $node.Source
    $script:NodeVersion = $nodeVersion
    $script:PnpmRunner = @($pnpm.Source)
    $script:PnpmVersion = $pnpmVersion
    $env:JIEJIAN_NODE_EXECUTABLE = $script:Node
    $env:JIEJIAN_NODE_VERSION = $script:NodeVersion
    $env:JIEJIAN_PNPM_EXECUTABLE = $script:PnpmRunner[0]
    $env:JIEJIAN_PNPM_VERSION = $script:PnpmVersion
}

function Get-FrontendDigest {
    $frontend = Join-Path $script:ProjectRoot "product\frontend"
    $files = @(
        (Join-Path $frontend "package.json"),
        (Join-Path $frontend "pnpm-lock.yaml"),
        (Join-Path $frontend "pnpm-workspace.yaml"),
        (Join-Path $frontend "index.html"),
        (Join-Path $frontend "tsconfig.json"),
        (Join-Path $frontend "vite.config.ts")
    ) + @(Get-ChildItem -LiteralPath (Join-Path $frontend "src") -Recurse -File | Select-Object -ExpandProperty FullName)
    return Get-CombinedDigest $files
}

function Prepare-Frontend($Toolchain, [bool]$Exact) {
    Resolve-DevelopmentNode $Toolchain $Exact
    $frontend = Join-Path $script:ProjectRoot "product\frontend"
    $fingerprint = Get-FrontendDigest
    $index = Join-Path $frontend "dist\index.html"
    $modules = Join-Path $frontend "node_modules\.modules.yaml"
    $stateDigest = [string](Get-StateValue "frontend_digest")
    if ($stateDigest -ne $fingerprint -or -not (Test-Path -LiteralPath $modules -PathType Leaf) -or -not (Test-Path -LiteralPath $index -PathType Leaf)) {
        Push-Location -LiteralPath $frontend
        try {
            Invoke-External "frontend-install" @($script:PnpmRunner + @("install", "--frozen-lockfile", "--store-dir", (Join-Path $script:VarDir "cache\pnpm-store")))
            Invoke-External "frontend-build" @($script:PnpmRunner + @("build"))
        } finally { Pop-Location }
        if (-not (Test-Path -LiteralPath $index -PathType Leaf)) {
            Fail-Development "frontend-build" "前端构建没有生成 dist/index.html" "检查 TypeScript/Vite 输出"
        }
        Set-StateValue "frontend_digest" $fingerprint
        Save-State
    }
    $env:JIEJIAN_FRONTEND_DEPENDENCIES = "pnpm $($script:PnpmVersion) · 已同步"
    $env:JIEJIAN_FRONTEND_DIST = Join-Path $frontend "dist"
}

function Prepare-Database {
    Invoke-External "migration" @(
        $script:Python,
        "-B",
        "-c",
        "import sys; from pathlib import Path; from product.backend.infra.storage import default_database_path, upgrade_database; upgrade_database(default_database_path(Path(sys.argv[1])))",
        $script:VarDir
    )
}

function Invoke-DevelopmentStart($Toolchain) {
    Prepare-Frontend $Toolchain $false
    Prepare-Chromium
    Prepare-Database
    Exit-PrepareLock
    Write-Host "界鉴开发环境已准备完成，正在打开图形界面。" -ForegroundColor Cyan
    Invoke-External "serve" @(
        $script:Python,
        "-B",
        "-m",
        "product.backend.cli",
        "--var-dir",
        $script:VarDir,
        "serve",
        "--open",
        "--frontend-dir",
        $env:JIEJIAN_FRONTEND_DIST
    )
}

function Invoke-DevelopmentTest {
    Exit-PrepareLock
    $testRoot = Join-Path $script:VarDir "test"
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
    $baseTemp = Join-Path $testRoot ("dev-{0}" -f [guid]::NewGuid().ToString("N"))
    try {
        Invoke-External "pytest" (@($script:Python, "-B", "-m", "pytest", "-p", "no:cacheprovider", "--basetemp", $baseTemp) + $CommandArguments)
    } finally {
        Remove-Item -LiteralPath $baseTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-DevelopmentShell {
    Exit-PrepareLock
    $shell = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) { "pwsh.exe" } else { "powershell.exe" }
    $python = $script:Python.Replace("'", "''")
    $project = $script:ProjectRoot.Replace("'", "''")
    $var = $script:VarDir.Replace("'", "''")
    $child = @"
function jiejian {
    param([Parameter(ValueFromRemainingArguments=`$true)][object[]]`$Arguments)
    & '$python' -B -m product.backend.cli --var-dir '$var' @Arguments
}
Set-Location -LiteralPath '$project'
Write-Host '已进入界鉴开发环境。输入 jiejian --help 查看命令。' -ForegroundColor Cyan
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($child))
    & $shell -NoLogo -NoProfile -NoExit -EncodedCommand $encoded
}

function Invoke-Update {
    $toolchain = Read-Toolchain
    Ensure-Conda "auto"
    Resolve-Uv $toolchain
    Set-DevelopmentEnvironment
    Push-Location -LiteralPath $script:ProjectRoot
    try {
        Invoke-External "uv-update" (@($script:Uv, "lock") + $CommandArguments)
        Invoke-External "uv-sync" @($script:Uv, "sync", "--frozen", "--all-groups")
    } finally { Pop-Location }
    Set-StateValue "sync_digest" (Get-CombinedDigest @((Join-Path $script:ProjectRoot "pyproject.toml"), (Join-Path $script:ProjectRoot "uv.lock")))
    Confirm-DevelopmentIdentity
    Save-State
}

function Invoke-Package($Toolchain) {
    Prepare-Frontend $Toolchain $true
    Prepare-Chromium
    $dist = Join-Path $script:VarDir "runtime\release-artifacts"
    New-Item -ItemType Directory -Path $dist -Force | Out-Null
    Get-ChildItem -LiteralPath $dist -Filter "jiejian-*.whl" -File -ErrorAction SilentlyContinue | Remove-Item -Force
    Push-Location -LiteralPath $script:ProjectRoot
    try { Invoke-External "wheel" @($script:Uv, "build", "--wheel", "--out-dir", $dist) }
    finally { Pop-Location }
    $wheels = @(Get-ChildItem -LiteralPath $dist -Filter "jiejian-*.whl" -File)
    if ($wheels.Count -ne 1) { Fail-Development "wheel" "发布构建没有形成唯一 Wheel" "检查 uv build 输出" }
    Write-Host ("发布资源已生成：{0}" -f $wheels[0].FullName) -ForegroundColor Green
}

try {
    [Console]::InputEncoding = $script:Utf8NoBom
    [Console]::OutputEncoding = $script:Utf8NoBom
    $OutputEncoding = $script:Utf8NoBom
    Enter-PrepareLock
    Read-State
    if ($Command -eq "update") {
        Invoke-Update
        Write-Host "uv.lock 与 jiejian_env 已更新。" -ForegroundColor Green
        exit 0
    }
    $mode = if ($Command -eq "bootstrap") { "bootstrap" } elseif ($Command -eq "sync") { "sync" } else { "auto" }
    $toolchain = Prepare-Python $mode
    switch ($Command) {
        "bootstrap" { Write-Host "jiejian_env 已按 environment.yml 与 uv.lock 完整准备。" -ForegroundColor Green }
        "sync" { Write-Host "jiejian_env 已按 uv.lock 精确同步。" -ForegroundColor Green }
        "start" { Invoke-DevelopmentStart $toolchain }
        "test" { Invoke-DevelopmentTest }
        "shell" { Invoke-DevelopmentShell }
        "package" { Invoke-Package $toolchain }
    }
} catch {
    if ($_.Exception.Message) { Write-Host $_.Exception.Message -ForegroundColor Red }
    exit 1
} finally {
    $env:PATH = $script:OriginalPath
    Exit-PrepareLock
}
