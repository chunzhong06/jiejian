#Requires -Version 5.1
# =============================================================================
# 界鉴仓库开发入口
#
# 定位
#   全局项目专用 Conda 环境、冻结 uv 依赖与仓库源码之间的唯一开发编排入口
#
# 职责
#   创建或更新 Python 基线｜冻结同步 editable 项目｜源码启动准备｜开发测试/交互/可选打包
#
# 边界
#   只有 update 可以改写 uv.lock；不修改用户 PATH、PowerShell Profile 或仓库外环境。
# =============================================================================

[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet("bootstrap", "sync", "update", "prepare", "start", "cli", "test", "frontend-test", "schema", "shell", "package")]
    [string]$Command = "start",
    [string]$VarDir = "",
    [switch]$ForcePrepare,
    [switch]$Update,
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
$script:FrontendBuildState = $null
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

# prepare 子进程只输出固定机器标记；路径、秘密和外部命令正文继续留在日志边界。
function Write-PrepareStatus(
    [ValidateSet("toolchain", "python", "browser", "frontend-dependencies", "frontend-build", "database")][string]$Token,
    [ValidateSet("start", "done")][string]$State
) {
    [Console]::Out.WriteLine(("__JIEJIAN_PREPARE_STATUS__:{0}:{1}" -f $Token, $State))
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

function Get-PathSetDigest([string[]]$Paths) {
    $lines = @(
        $Paths |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            ForEach-Object { [IO.Path]::GetFullPath($_) } |
            Sort-Object
    )
    $bytes = $script:Utf8NoBom.GetBytes(($lines -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Get-ProjectPackageTopologyInputs {
    $paths = New-Object System.Collections.Generic.List[string]
    # Hatch editable 会冻结包发现结果；包目录新增、删除或移动时必须重新同步。
    foreach ($relativeRoot in @("product\backend", "product\protocols")) {
        $root = Join-Path $script:ProjectRoot $relativeRoot
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        foreach ($packageMarker in (Get-ChildItem -LiteralPath $root -Recurse -Filter "__init__.py" -File)) {
            $null = $paths.Add($packageMarker.FullName)
        }
    }
    return @($paths)
}

function Get-ProjectSyncInputs {
    return @(
        (Join-Path $script:ProjectRoot "pyproject.toml")
        (Join-Path $script:ProjectRoot "uv.lock")
    )
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
    $probe = "import json; from product.backend.infra.runtime.process.identity import python_environment_report; print(json.dumps(python_environment_report(), ensure_ascii=False))"
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
    & $script:Python -B -c "from product.backend.infra.runtime.process.identity import require_python_environment; require_python_environment()" 2>$null
    if ($LASTEXITCODE -ne 0) { Fail-Development "python-identity" "主进程环境指纹复核失败" "执行 .\scripts\dev.ps1 sync" }
    Set-StateValue "runtime_fingerprint" $env:JIEJIAN_RUNTIME_FINGERPRINT
}

function Sync-Project([bool]$ForceSync) {
    $syncDigest = Get-CombinedDigest @(Get-ProjectSyncInputs)
    $topologyDigest = Get-PathSetDigest @(Get-ProjectPackageTopologyInputs)
    Push-Location -LiteralPath $script:ProjectRoot
    try {
        Invoke-External "uv-lock" @($script:Uv, "lock", "--check")
        $stateDigest = [string](Get-StateValue "sync_digest")
        $stateTopologyDigest = [string](Get-StateValue "package_topology_digest")
        $identity = if ($stateDigest -eq $syncDigest) { Read-DevelopmentIdentity } else { $null }
        if ($ForceSync -or $stateDigest -ne $syncDigest -or $stateTopologyDigest -ne $topologyDigest -or $null -eq $identity -or -not $identity.ok) {
            Write-Host "正在按 uv.lock 精确同步项目依赖……" -ForegroundColor Cyan
            $syncArguments = @($script:Uv, "sync", "--frozen", "--all-groups")
            if ($ForceSync -or $stateTopologyDigest -ne $topologyDigest -or $null -eq $identity -or -not $identity.ok) {
                $syncArguments += @("--reinstall-package", "jiejian")
            }
            Invoke-External "uv-sync" $syncArguments
            Set-StateValue "sync_digest" $syncDigest
            Set-StateValue "package_topology_digest" $topologyDigest
        } else {
            Write-Host "Python 依赖指纹未变化，复用 jiejian_env。" -ForegroundColor DarkGray
        }
    } finally { Pop-Location }
    Confirm-DevelopmentIdentity
    Save-State
}

function Prepare-Python([ValidateSet("auto", "bootstrap", "sync")][string]$Mode) {
    Write-PrepareStatus "toolchain" "start"
    $toolchain = Read-Toolchain
    Resolve-Uv $toolchain
    Write-PrepareStatus "toolchain" "done"
    Write-PrepareStatus "python" "start"
    if ($Mode -eq "bootstrap") { Ensure-Conda "force" }
    elseif ($Mode -eq "sync") { Ensure-Conda "existing" }
    else { Ensure-Conda "auto" }
    Set-DevelopmentEnvironment
    Sync-Project ($Mode -in @("bootstrap", "sync"))
    Write-PrepareStatus "python" "done"
    return $toolchain
}

function Prepare-Chromium {
    Write-PrepareStatus "browser" "start"
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
    Write-PrepareStatus "browser" "done"
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

function Remove-LegacyFrontendArtifacts {
    $frontend = Join-Path $script:ProjectRoot "product\frontend"
    # 只删除旧设计明确生成的三类路径；未知文件属于用户工作树，准备入口不得猜测清理。
    foreach ($path in @(
        (Join-Path $frontend "node_modules"),
        (Join-Path $frontend "dist"),
        (Join-Path $frontend "tsconfig.tsbuildinfo")
    )) {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-FrontendSourceInputs {
    $frontend = [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot "product\frontend"))
    $prefix = $frontend.TrimEnd("\") + "\"
    # 这一个集合同时供指纹和镜像使用，避免构建判定与实际工作区出现两份漂移清单。
    $generatedDirectories = @("node_modules", "dist", "coverage", ".vite", ".cache")
    $directories = New-Object System.Collections.Generic.Stack[string]
    $inputs = New-Object System.Collections.Generic.List[object]
    $directories.Push($frontend)
    while ($directories.Count -gt 0) {
        $directory = $directories.Pop()
        foreach ($item in Get-ChildItem -LiteralPath $directory -Force) {
            if ($item.PSIsContainer) {
                if ($item.Name -notin $generatedDirectories) { $directories.Push($item.FullName) }
                continue
            }
            if ($item.Name.EndsWith(".tsbuildinfo", [StringComparison]::OrdinalIgnoreCase)) { continue }
            $relative = $item.FullName.Substring($prefix.Length).Replace("\", "/")
            $null = $inputs.Add([pscustomobject]@{
                source = [IO.Path]::GetFullPath($item.FullName)
                relative = $relative
            })
        }
    }
    return @($inputs | Sort-Object relative)
}

function Get-FrontendDigest($Inputs) {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($input in $Inputs) {
        $null = $lines.Add(("{0}|{1}" -f [string]$input.relative, (Get-FileDigest ([string]$input.source))))
    }
    $editorPlugin = Get-FrontendEditorPluginRoot
    $editorPrefix = $editorPlugin.TrimEnd("\") + "\"
    foreach ($file in Get-ChildItem -LiteralPath $editorPlugin -File -Recurse | Sort-Object FullName) {
        $relative = $file.FullName.Substring($editorPrefix.Length).Replace("\", "/")
        $null = $lines.Add(("../editor/{0}|{1}" -f $relative, (Get-FileDigest $file.FullName)))
    }
    $null = $lines.Add(("../config/toolchain.json|{0}" -f (Get-FileDigest $script:ToolchainPath)))
    $bytes = $script:Utf8NoBom.GetBytes(($lines -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Get-FrontendWorkspace {
    return Join-Path $script:VarDir "runtime\build\frontend-workspace"
}

function Get-FrontendEditorPluginRoot {
    return Join-Path $script:ProjectRoot "scripts\editor\typescript-plugins\jiejian-controlled-workspace-resolver"
}

function Get-FrontendEditorPluginTarget([string]$Workspace) {
    return Join-Path $Workspace "node_modules\jiejian-controlled-workspace-resolver"
}

function Test-FrontendEditorPluginInstalled([string]$Workspace) {
    $target = Get-FrontendEditorPluginTarget $Workspace
    return (Test-Path -LiteralPath (Join-Path $target "package.json") -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $target "index.cjs") -PathType Leaf)
}

function Install-FrontendEditorPlugin([string]$Workspace) {
    $source = Get-FrontendEditorPluginRoot
    $target = Get-FrontendEditorPluginTarget $Workspace
    if (-not (Test-Path -LiteralPath (Join-Path $source "package.json") -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $source "index.cjs") -PathType Leaf)) {
        Fail-Development "frontend-editor" "编辑器解析插件源码不完整" "恢复 scripts/editor/typescript-plugins 后重试"
    }
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
    if (-not (Test-FrontendEditorPluginInstalled $Workspace)) {
        Fail-Development "frontend-editor" "编辑器解析插件未进入受控前端工作区" "执行 runtime repair 后重试"
    }
}

function Get-FrontendBuildReceiptPath {
    return Join-Path $script:VarDir "runtime\build\frontend-receipt.json"
}

function Read-FrontendBuildReceipt {
    $path = Get-FrontendBuildReceiptPath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { return $null }
}

function Write-FrontendBuildReceipt($Record) {
    $path = Get-FrontendBuildReceiptPath
    $temporary = "$path.$([guid]::NewGuid().ToString('N')).tmp"
    New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
    try {
        [IO.File]::WriteAllText($temporary, ($Record | ConvertTo-Json -Compress), $script:Utf8NoBom)
        if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path -Force }
        [IO.File]::Move($temporary, $path)
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Prepare-FrontendWorkspace($Toolchain, $Inputs, [string]$Fingerprint) {
    Resolve-DevelopmentNode $Toolchain $true
    $workspace = Get-FrontendWorkspace
    $workspaceDigest = Join-Path $workspace ".jiejian-source-digest"
    $modules = Join-Path $workspace "node_modules\.modules.yaml"
    $healthy = (Test-Path -LiteralPath $workspaceDigest -PathType Leaf) -and
        ((Get-Content -LiteralPath $workspaceDigest -Raw -Encoding UTF8).Trim() -eq $Fingerprint) -and
        (Test-Path -LiteralPath $modules -PathType Leaf) -and
        (Test-FrontendEditorPluginInstalled $workspace)
    if ($healthy) { return }

    Remove-Item -LiteralPath $workspace -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $workspace -Force | Out-Null
    foreach ($input in $Inputs) {
        $destination = Join-Path $workspace ([string]$input.relative).Replace("/", "\")
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath ([string]$input.source) -Destination $destination -Force
    }
    Push-Location -LiteralPath $workspace
    try {
        Invoke-External "frontend-install" @($script:PnpmRunner + @(
            "install", "--frozen-lockfile", "--store-dir", (Join-Path $script:VarDir "cache\pnpm-store")
        ))
        if (-not (Test-Path -LiteralPath $modules -PathType Leaf)) {
            Fail-Development "frontend-install" "pnpm 未在 var/runtime/build/frontend-workspace 生成完整依赖安装视图" "执行 runtime repair 后重试"
        }
        # VS Code 禁止工作区覆盖机器级插件探测目录；插件必须随可重建依赖视图安装。
        Install-FrontendEditorPlugin $workspace
        [IO.File]::WriteAllText($workspaceDigest, $Fingerprint, $script:Utf8NoBom)
    } catch {
        # runtime repair 只处理可证明损坏的运行时；失败安装用标记提供该证明。
        [IO.File]::WriteAllText((Join-Path $workspace ".invalid"), "frontend-workspace", $script:Utf8NoBom)
        throw
    } finally { Pop-Location }
}

function Invoke-FrontendBuild([string]$Workspace, [string]$Dist) {
    $savedOutDir = $env:JIEJIAN_FRONTEND_OUT_DIR
    $savedCacheDir = $env:JIEJIAN_FRONTEND_CACHE_DIR
    Push-Location -LiteralPath $Workspace
    try {
        $env:JIEJIAN_FRONTEND_OUT_DIR = [IO.Path]::GetFullPath($Dist)
        $env:JIEJIAN_FRONTEND_CACHE_DIR = [IO.Path]::GetFullPath((Join-Path $script:VarDir "cache\vite"))
        Invoke-External "frontend-build" @($script:PnpmRunner + @("build"))
    } finally {
        if ($null -eq $savedOutDir) { Remove-Item Env:JIEJIAN_FRONTEND_OUT_DIR -ErrorAction SilentlyContinue }
        else { $env:JIEJIAN_FRONTEND_OUT_DIR = $savedOutDir }
        if ($null -eq $savedCacheDir) { Remove-Item Env:JIEJIAN_FRONTEND_CACHE_DIR -ErrorAction SilentlyContinue }
        else { $env:JIEJIAN_FRONTEND_CACHE_DIR = $savedCacheDir }
        Pop-Location
    }
}

function Set-FrontendToolEnvironment($Record) {
    if ($null -eq $Record) { return }
    $script:Node = [string]$Record.node_executable
    $script:NodeVersion = [string]$Record.node_version
    $script:PnpmVersion = [string]$Record.pnpm_version
    if (-not [string]::IsNullOrWhiteSpace([string]$Record.pnpm_executable)) {
        $script:PnpmRunner = @([string]$Record.node_executable, [string]$Record.pnpm_executable)
    }
    if (-not [string]::IsNullOrWhiteSpace($script:Node)) {
        $env:JIEJIAN_NODE_EXECUTABLE = $script:Node
        $env:JIEJIAN_NODE_VERSION = $script:NodeVersion
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$Record.pnpm_executable)) {
        $env:JIEJIAN_PNPM_EXECUTABLE = [string]$Record.pnpm_executable
        $env:JIEJIAN_PNPM_VERSION = $script:PnpmVersion
    }
}

function Prepare-SourceFrontend($Toolchain) {
    Remove-LegacyFrontendArtifacts
    $inputs = @(Get-FrontendSourceInputs)
    $fingerprint = Get-FrontendDigest $inputs
    $dist = Join-Path $script:VarDir "runtime\frontend"
    $index = Join-Path $dist "index.html"
    $record = Read-FrontendBuildReceipt
    $workspace = Get-FrontendWorkspace
    $recordHit = -not $ForcePrepare -and $null -ne $record -and
        [string]$record.digest -eq $fingerprint -and
        [string]$record.dist -eq [IO.Path]::GetFullPath($dist) -and
        (Test-Path -LiteralPath $index -PathType Leaf) -and
        (Test-FrontendEditorPluginInstalled $workspace)
    if ($recordHit) {
        Write-PrepareStatus "frontend-dependencies" "start"
        Set-FrontendToolEnvironment $record
        Write-PrepareStatus "frontend-dependencies" "done"
        Write-PrepareStatus "frontend-build" "start"
        $script:FrontendBuildState = "reused"
        $env:JIEJIAN_FRONTEND_DEPENDENCIES = "构建指纹命中，运行阶段无需 Node/pnpm"
        $env:JIEJIAN_FRONTEND_DIST = [IO.Path]::GetFullPath($dist)
        $env:JIEJIAN_FRONTEND_BUILD_STATE = $script:FrontendBuildState
        Write-PrepareStatus "frontend-build" "done"
        Write-Host "前端构建指纹未变化，复用 var/runtime/frontend。" -ForegroundColor DarkGray
        return
    }

    # Node/pnpm 只属于构建阶段；已有可验证构建命中时不会解析、下载或启动它们。
    Write-PrepareStatus "frontend-dependencies" "start"
    Prepare-FrontendWorkspace $Toolchain $inputs $fingerprint
    Write-PrepareStatus "frontend-dependencies" "done"
    Write-PrepareStatus "frontend-build" "start"
    Invoke-FrontendBuild $workspace $dist
    if (-not (Test-Path -LiteralPath $index -PathType Leaf)) {
        Fail-Development "frontend-build" "前端构建没有生成 var/runtime/frontend/index.html" "检查 TypeScript/Vite 输出"
    }
    $record = [pscustomobject]@{
        digest = $fingerprint
        dist = [IO.Path]::GetFullPath($dist)
        workspace = [IO.Path]::GetFullPath($workspace)
        node_executable = $script:Node
        node_version = $script:NodeVersion
        pnpm_executable = $script:PnpmRunner[1]
        pnpm_version = $script:PnpmVersion
    }
    Write-FrontendBuildReceipt $record
    $script:FrontendBuildState = "rebuilt"
    $env:JIEJIAN_FRONTEND_DEPENDENCIES = "pnpm $($script:PnpmVersion) · 已同步并构建"
    $env:JIEJIAN_FRONTEND_DIST = [IO.Path]::GetFullPath($dist)
    $env:JIEJIAN_FRONTEND_BUILD_STATE = $script:FrontendBuildState
    Write-PrepareStatus "frontend-build" "done"
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

function Write-SourceReceipt {
    $identity = Read-DevelopmentIdentity
    if ($null -eq $identity -or -not $identity.ok) {
        Fail-Development "python-identity" "无法为源码启动形成可信环境回执" "执行 .\scripts\dev.ps1 sync"
    }
    $pythonVersion = (& $script:Python -S -B -c "import platform; print(platform.python_version())" 2>$null | Out-String).Trim()
    $receiptPath = Join-Path $script:VarDir "runtime\source\receipt.json"
    $receipt = [ordered]@{
        schema_version = "1"
        project_root = $script:ProjectRoot
        var_dir = $script:VarDir
        runtime_mode = "development"
        python = [ordered]@{
            executable = $script:Python
            version = $pythonVersion
            environment_path = $script:CondaPrefix
            environment_type = "conda"
            runtime_fingerprint = [string]$identity.runtime_fingerprint
            report = $identity
        }
        uv = [ordered]@{ executable = $script:Uv; version = $script:UvVersion }
        node = [ordered]@{ executable = $env:JIEJIAN_NODE_EXECUTABLE; version = $env:JIEJIAN_NODE_VERSION }
        pnpm = [ordered]@{ executable = $env:JIEJIAN_PNPM_EXECUTABLE; version = $env:JIEJIAN_PNPM_VERSION }
        playwright = [ordered]@{ executable = $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE; browsers_path = $env:PLAYWRIGHT_BROWSERS_PATH }
        frontend = [ordered]@{
            dist = $env:JIEJIAN_FRONTEND_DIST
            dependencies = $env:JIEJIAN_FRONTEND_DEPENDENCIES
            build_state = $script:FrontendBuildState
        }
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $receiptPath) -Force | Out-Null
    $temporary = "$receiptPath.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [IO.File]::WriteAllText($temporary, ($receipt | ConvertTo-Json -Depth 12 -Compress), $script:Utf8NoBom)
        if (Test-Path -LiteralPath $receiptPath -PathType Leaf) { Remove-Item -LiteralPath $receiptPath -Force }
        [IO.File]::Move($temporary, $receiptPath)
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
    Write-Host ("源码运行环境回执：{0}" -f $receiptPath) -ForegroundColor Green
}

function Prepare-SourceRuntime($Toolchain) {
    Prepare-Chromium
    Prepare-SourceFrontend $Toolchain
    Write-PrepareStatus "database" "start"
    Prepare-Database
    Write-PrepareStatus "database" "done"
    Write-SourceReceipt
}

function Invoke-DevelopmentStart {
    if ($CommandArguments.Count -gt 0) {
        Fail-Development "start" "dev.ps1 start 不接受额外参数" "直接调用 scripts/start.ps1 并传入受支持的产品启动参数"
    }
    $shellName = if ($PSEdition -eq "Core") { "pwsh.exe" } else { "powershell.exe" }
    $shell = Join-Path $PSHOME $shellName
    if (-not (Test-Path -LiteralPath $shell -PathType Leaf)) {
        Fail-Development "start" "无法定位当前 PowerShell 产品启动入口" "修复 PowerShell 后直接运行 start.cmd"
    }
    $arguments = @(
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $script:ProjectRoot "scripts\start.ps1"),
        "-Mode", "Gui",
        "-VarDir", $script:VarDir
    )
    if ($ForcePrepare) { $arguments += "-ForcePrepare" }
    & $shell @arguments | Out-Host
    return [int]$LASTEXITCODE
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

function Invoke-Schema {
    Exit-PrepareLock
    if ($CommandArguments.Count -gt 0) {
        Fail-Development "schema" "dev.ps1 schema 不接受位置参数" "使用 .\scripts\dev.ps1 schema 或追加 -Update"
    }
    $arguments = @($script:Python, "-B", "-m", "product.protocols.schema")
    if ($Update) { $arguments += "--update" }
    Invoke-External "schema" $arguments
}

function Invoke-FrontendTest($Toolchain) {
    Remove-LegacyFrontendArtifacts
    $inputs = @(Get-FrontendSourceInputs)
    $fingerprint = Get-FrontendDigest $inputs
    Prepare-FrontendWorkspace $Toolchain $inputs $fingerprint
    $workspace = Get-FrontendWorkspace
    Invoke-External "frontend-editor" @(
        $script:Node,
        (Join-Path $script:ProjectRoot "scripts\editor\verify-controlled-workspace-resolver.cjs"),
        $workspace,
        $script:ProjectRoot,
        $script:VarDir
    )
    $savedCacheDir = $env:JIEJIAN_FRONTEND_CACHE_DIR
    Push-Location -LiteralPath $workspace
    try {
        $env:JIEJIAN_FRONTEND_CACHE_DIR = [IO.Path]::GetFullPath((Join-Path $script:VarDir "cache\vite"))
        Invoke-External "frontend-test" (@($script:PnpmRunner + @("test")) + $CommandArguments)
    } finally {
        if ($null -eq $savedCacheDir) { Remove-Item Env:JIEJIAN_FRONTEND_CACHE_DIR -ErrorAction SilentlyContinue }
        else { $env:JIEJIAN_FRONTEND_CACHE_DIR = $savedCacheDir }
        Pop-Location
    }
}

function Invoke-DevelopmentCli {
    Exit-PrepareLock
    Invoke-External "cli" (@(
        $script:Python,
        "-B",
        "-m",
        "product.backend.cli",
        "--var-dir",
        $script:VarDir
    ) + $CommandArguments)
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
        Invoke-External "uv-sync" @($script:Uv, "sync", "--frozen", "--all-groups", "--reinstall-package", "jiejian")
    } finally { Pop-Location }
    Set-StateValue "sync_digest" (Get-CombinedDigest @(Get-ProjectSyncInputs))
    Set-StateValue "package_topology_digest" (Get-PathSetDigest @(Get-ProjectPackageTopologyInputs))
    Confirm-DevelopmentIdentity
    Save-State
}

function Invoke-Package($Toolchain) {
    Prepare-SourceFrontend $Toolchain
    Prepare-Chromium
    $dist = Join-Path $script:VarDir "runtime\release-artifacts"
    $frontend = Join-Path $script:VarDir "runtime\frontend"
    if (-not (Test-Path -LiteralPath (Join-Path $frontend "index.html") -PathType Leaf)) {
        Fail-Development "wheel" "可选发布构建缺少已准备的前端入口" "执行 .\scripts\dev.ps1 prepare 后重试"
    }
    New-Item -ItemType Directory -Path $dist -Force | Out-Null
    Get-ChildItem -LiteralPath $dist -Filter "jiejian-*.whl" -File -ErrorAction SilentlyContinue | Remove-Item -Force
    $savedPackageFrontend = $env:JIEJIAN_PACKAGE_FRONTEND_DIR
    $env:JIEJIAN_PACKAGE_FRONTEND_DIR = [IO.Path]::GetFullPath($frontend)
    Push-Location -LiteralPath $script:ProjectRoot
    try { Invoke-External "wheel" @($script:Uv, "build", "--wheel", "--out-dir", $dist) }
    finally {
        Pop-Location
        if ($null -eq $savedPackageFrontend) { Remove-Item Env:JIEJIAN_PACKAGE_FRONTEND_DIR -ErrorAction SilentlyContinue }
        else { $env:JIEJIAN_PACKAGE_FRONTEND_DIR = $savedPackageFrontend }
    }
    $wheels = @(Get-ChildItem -LiteralPath $dist -Filter "jiejian-*.whl" -File)
    if ($wheels.Count -ne 1) { Fail-Development "wheel" "发布构建没有形成唯一 Wheel" "检查 uv build 输出" }
    Write-Host ("发布资源已生成：{0}" -f $wheels[0].FullName) -ForegroundColor Green
}

try {
    [Console]::InputEncoding = $script:Utf8NoBom
    [Console]::OutputEncoding = $script:Utf8NoBom
    $OutputEncoding = $script:Utf8NoBom
    if ($Update -and $Command -ne "schema") {
        Fail-Development "arguments" "-Update 只允许与 schema 命令一起使用" "使用 .\scripts\dev.ps1 schema -Update"
    }
    if ($Command -eq "start") {
        exit (Invoke-DevelopmentStart)
    }
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
        "prepare" { Prepare-SourceRuntime $toolchain }
        "cli" { Invoke-DevelopmentCli }
        "test" { Invoke-DevelopmentTest }
        "frontend-test" { Invoke-FrontendTest $toolchain }
        "schema" { Invoke-Schema }
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
