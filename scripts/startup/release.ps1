# =============================================================================
# 正式发布运行时准备
#
# 定位
#   start.cmd 与已构建 Wheel、uv 私有 Python、Chromium 和预构建前端之间的准备边界
#
# 职责
#   固定 uv 校验｜版本化私有环境｜非 editable Wheel 安装｜运行身份与资源复核
#
# 边界
#   不调用 Conda、Node、pnpm、TypeScript 或 Vite，也不从源码目录导入产品包。
# =============================================================================

function Read-ReleaseToolchain {
    try {
        $value = Get-Content -LiteralPath $script:ToolchainPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($value.schema_version -ne "1") { throw "unsupported toolchain schema" }
        return $value
    } catch {
        Fail-Start 21 "uv" "无法读取唯一工具链清单" "重新生成完整发布包后重试"
    }
}

function Enter-ReleasePrepareLock {
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
        Fail-Start 22 "prepare-lock" "另一个界鉴准备进程正在修改运行环境" "等待另一进程完成后重新启动"
    }
}

function Exit-ReleasePrepareLock {
    if ($null -ne $script:PrepareLock) {
        $script:PrepareLock.Dispose()
        $script:PrepareLock = $null
    }
}

function Resolve-ReleaseUv($Toolchain) {
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    $key = switch ($architecture.ToUpperInvariant()) {
        "AMD64" { "x64" }
        "ARM64" { "arm64" }
        default { $null }
    }
    if ($null -eq $key) {
        Fail-Start 21 "uv" "当前 Windows 架构不受支持" "使用 AMD64 或 ARM64 Windows"
    }
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
        $downloadRoot = Join-Path $script:VarDir ("temp\downloads\uv-{0}" -f [guid]::NewGuid().ToString("N"))
        $partial = Join-Path $script:VarDir ("cache\downloads\.tmp-{0}-{1}" -f [guid]::NewGuid().ToString("N"), [string]$metadata.asset)
        New-Item -ItemType Directory -Path $install -Force | Out-Null
        New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
        New-Item -ItemType Directory -Path (Split-Path -Parent $partial) -Force | Out-Null
        try {
            $uri = "https://github.com/astral-sh/uv/releases/download/{0}/{1}" -f $version, [string]$metadata.asset
            Invoke-WebRequest -Uri $uri -OutFile $partial -UseBasicParsing
            if ((Get-FileDigest $partial) -ne [string]$metadata.sha256) {
                Fail-Start 21 "uv" "uv 归档 SHA-256 校验失败" "删除 var/cache/downloads 后重试"
            }
            Expand-Archive -LiteralPath $partial -DestinationPath $downloadRoot -Force
            $candidate = Get-ChildItem -LiteralPath $downloadRoot -Recurse -Filter "uv.exe" -File | Select-Object -First 1
            if ($null -eq $candidate) {
                Fail-Start 21 "uv" "uv 归档缺少可执行文件" "重新下载固定 uv 归档"
            }
            Copy-Item -LiteralPath $candidate.FullName -Destination $executable -Force
            $payload = [ordered]@{
                schema_version = "1"
                version = $version
                archive_sha256 = [string]$metadata.sha256
                executable_sha256 = Get-FileDigest $executable
            }
            [IO.File]::WriteAllText($receipt, ($payload | ConvertTo-Json -Compress), $script:Utf8Encoding)
        } finally {
            Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    $actual = (& $executable --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -notmatch ("^uv\s+" + [regex]::Escape($version) + "(\s|$)")) {
        Fail-Start 21 "uv" "受控 uv 版本不符合工具链清单" "删除 var/runtime/uv 后重新启动"
    }
    $script:UvExecutable = [IO.Path]::GetFullPath($executable)
    $script:UvVersion = $version
}

function Get-ReleaseWheel {
    $dist = Join-Path $script:VarDir "runtime\release-artifacts"
    $wheels = @(Get-ChildItem -LiteralPath $dist -Filter "jiejian-*.whl" -File -ErrorAction SilentlyContinue)
    if ($wheels.Count -ne 1) {
        Fail-Start 40 "release-assets" "正式启动需要唯一的预构建界鉴 Wheel" "仓库开发请执行 .\scripts\dev.ps1 package，然后重新运行 start.cmd"
    }
    $archive = $null
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
        $archive = [IO.Compression.ZipFile]::OpenRead($wheels[0].FullName)
        if ($null -eq ($archive.Entries | Where-Object { $_.FullName -eq "product/frontend/dist/index.html" } | Select-Object -First 1)) {
            Fail-Start 40 "release-assets" "界鉴 Wheel 缺少预构建前端入口" "重新执行 .\scripts\dev.ps1 package"
        }
    } catch {
        if ($script:FailureCode -eq 0) {
            Fail-Start 40 "release-assets" "无法校验界鉴 Wheel 中的预构建前端" "重新执行 .\scripts\dev.ps1 package"
        }
        throw
    } finally {
        if ($null -ne $archive) { $archive.Dispose() }
    }
    return $wheels[0]
}

function Confirm-ReleaseFrontend {
    $productOrigin = [string]$script:PythonEnvironmentReport.package_origins.product
    if ([string]::IsNullOrWhiteSpace($productOrigin)) {
        Fail-Start 44 "release-assets" "正式环境没有提供已安装 product 包来源" "删除损坏运行时后重新启动"
    }
    $frontend = Join-Path (Split-Path -Parent $productOrigin) "frontend\dist"
    $index = Join-Path $frontend "index.html"
    $environmentPrefix = [IO.Path]::GetFullPath($script:PythonEnvironmentPath).TrimEnd("\") + "\"
    $frontendPath = [IO.Path]::GetFullPath($frontend)
    if (-not $frontendPath.StartsWith($environmentPrefix, [StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-Path -LiteralPath $index -PathType Leaf)) {
        Fail-Start 44 "release-assets" "正式环境缺少 Wheel 内预构建前端" "删除损坏运行时并重新执行 .\scripts\dev.ps1 package"
    }
    $script:FrontendDist = $frontendPath
    $env:JIEJIAN_FRONTEND_DIST = $script:FrontendDist
    $env:JIEJIAN_FRONTEND_DEPENDENCIES = "预构建资源 · 已确认"
}

function Set-ReleaseEnvironment([string]$EnvironmentPath, [string]$PythonPath, [string]$BrowserPath) {
    $script:PythonEnvironmentType = "uv-private"
    $script:PythonEnvironmentPath = [IO.Path]::GetFullPath($EnvironmentPath)
    $script:PythonExecutable = [IO.Path]::GetFullPath($PythonPath)
    $script:PythonRunner = @($script:PythonExecutable, "-B")
    $script:PackageRunner = @($script:PythonExecutable, "-B", "-m", "product.backend.cli")
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONNOUSERSITE = "1"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    $env:UV_PROJECT_ENVIRONMENT = $script:PythonEnvironmentPath
    $env:UV_CACHE_DIR = Join-Path $script:VarDir "cache\uv"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $script:VarDir "runtime\python\installations"
    $env:PLAYWRIGHT_BROWSERS_PATH = $BrowserPath
    $env:JIEJIAN_VAR_DIR = $script:VarDir
    $env:JIEJIAN_PROJECT_ROOT = $script:ProjectRoot
    $env:JIEJIAN_RUNTIME_MODE = "release"
    $env:JIEJIAN_PYTHON_EXECUTABLE = $script:PythonExecutable
    $env:JIEJIAN_PYTHON_ENVIRONMENT_PATH = $script:PythonEnvironmentPath
    $env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE = "uv-private"
    $env:JIEJIAN_UV_EXECUTABLE = $script:UvExecutable
    $env:JIEJIAN_UV_VERSION = $script:UvVersion
    $env:JIEJIAN_TOOLCHAIN_MANIFEST = $script:ToolchainPath
    Remove-Item Env:JIEJIAN_NODE_EXECUTABLE -ErrorAction SilentlyContinue
    Remove-Item Env:JIEJIAN_NODE_VERSION -ErrorAction SilentlyContinue
    Remove-Item Env:JIEJIAN_PNPM_EXECUTABLE -ErrorAction SilentlyContinue
    Remove-Item Env:JIEJIAN_PNPM_VERSION -ErrorAction SilentlyContinue
}

function Read-ReleaseIdentity {
    Remove-Item Env:JIEJIAN_RUNTIME_FINGERPRINT -ErrorAction SilentlyContinue
    $probe = "import json; from product.backend.infra.runtime.environment_identity import python_environment_report; print(json.dumps(python_environment_report(), ensure_ascii=False))"
    $code = 1
    Push-Location -LiteralPath $script:ReleaseLaunchRoot
    try {
        $raw = (& $script:PythonExecutable -B -c $probe 2>&1 | Out-String).Trim()
        $code = $LASTEXITCODE
    }
    finally { Pop-Location }
    if ($code -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return $null }
    try { return $raw | ConvertFrom-Json } catch { return $null }
}

function Confirm-ReleaseIdentity {
    $report = Read-ReleaseIdentity
    if ($null -eq $report -or -not $report.ok) {
        $issues = if ($null -ne $report) { @($report.issues) -join "；" } else { "无法读取环境报告" }
        Fail-Start 40 "python" ("正式 Python 环境来源异常：" + $issues) "删除对应 var/runtime/python/release 目录后重新启动"
    }
    $env:JIEJIAN_RUNTIME_FINGERPRINT = [string]$report.runtime_fingerprint
    $code = 1
    Push-Location -LiteralPath $script:ReleaseLaunchRoot
    try {
        & $script:PythonExecutable -B -c "from product.backend.infra.runtime.environment_identity import require_python_environment; require_python_environment()" 2>$null
        $code = $LASTEXITCODE
    } finally { Pop-Location }
    if ($code -ne 0) {
        Fail-Start 40 "python" "正式环境指纹复核失败" "删除损坏的私有 Python 运行时后重试"
    }
    $script:PythonEnvironmentReport = $report
    $script:PythonVersion = [string]$report.version
}

function Prepare-ReleasePython($Toolchain) {
    $wheel = Get-ReleaseWheel
    $fingerprint = Get-StageFingerprint @(
        $script:ToolchainPath,
        (Join-Path $script:ProjectRoot "pyproject.toml"),
        (Join-Path $script:ProjectRoot "uv.lock"),
        $wheel.FullName
    ) @{
        mode = "release"
        python = [string]$Toolchain.python.supported_minor
        wheel_sha256 = Get-FileDigest $wheel.FullName
        uv = $script:UvVersion
    }
    $script:ReleaseFingerprint = $fingerprint
    $environmentPath = Join-Path $script:VarDir ("runtime\python\release\{0}" -f $fingerprint.Substring(0, 16))
    $python = Join-Path $environmentPath "Scripts\python.exe"
    $browserPath = Join-Path $script:VarDir ("runtime\playwright\release-{0}" -f $fingerprint.Substring(0, 16))
    New-Item -ItemType Directory -Path $script:ReleaseLaunchRoot -Force | Out-Null
    Set-ReleaseEnvironment $environmentPath $python $browserPath
    $stateHit = (Test-PhaseHit "release_python" $fingerprint) -and (Test-Path -LiteralPath $python -PathType Leaf)
    $identity = if ($stateHit) { Read-ReleaseIdentity } else { $null }
    if (-not $stateHit -or $null -eq $identity -or -not $identity.ok) {
        Write-Startup "[release_python] 准备 uv 私有 Python 与非 editable Wheel"
        Push-Location -LiteralPath $script:ProjectRoot
        try {
            Invoke-External "lock" @($script:UvExecutable) @("lock", "--check") 22 (Get-RecoveryCommand)
            Invoke-External "uv" @($script:UvExecutable) @(
                "sync",
                "--frozen",
                "--no-dev",
                "--no-install-project",
                "--python",
                [string]$Toolchain.python.supported_minor,
                "--managed-python"
            ) 21 (Get-RecoveryCommand)
            Invoke-External "wheel" @($script:UvExecutable) @(
                "pip",
                "install",
                "--python",
                $python,
                "--no-deps",
                "--reinstall",
                $wheel.FullName
            ) 40 (Get-RecoveryCommand)
        } finally { Pop-Location }
        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            Fail-Start 40 "python" "uv 私有环境没有生成 Python 可执行文件" "删除损坏运行时后重试"
        }
        Set-ReleaseEnvironment $environmentPath $python $browserPath
        Confirm-ReleaseIdentity
        Set-PhaseState "release_python" $fingerprint @{
            environment_path = $environmentPath
            python = $python
            wheel = $wheel.FullName
            wheel_sha256 = Get-FileDigest $wheel.FullName
            runtime_fingerprint = $env:JIEJIAN_RUNTIME_FINGERPRINT
        }
    } else {
        Write-Startup "[release_python] 跳过：Wheel、锁文件和环境身份指纹命中"
        Confirm-ReleaseIdentity
    }
    $script:PythonFingerprint = $fingerprint
    $script:PythonDependenciesDetail = "Wheel · 非 editable · 已确认"
}

function Prepare-ReleaseChromium {
    $probe = "from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); x=Path(p.chromium.executable_path).resolve(); p.stop(); print(x); raise SystemExit(0 if x.is_file() else 1)"
    $code = 1
    Push-Location -LiteralPath $script:ReleaseLaunchRoot
    try {
        $path = (& $script:PythonExecutable -B -c $probe 2>$null | Out-String).Trim()
        $code = $LASTEXITCODE
    }
    finally { Pop-Location }
    if ($code -ne 0 -or [string]::IsNullOrWhiteSpace($path)) {
        Invoke-External "playwright" @($script:PythonExecutable) @("-B", "-m", "playwright", "install", "chromium") 41 (Get-RecoveryCommand)
        Push-Location -LiteralPath $script:ReleaseLaunchRoot
        try {
            $path = (& $script:PythonExecutable -B -c $probe 2>$null | Out-String).Trim()
            $code = $LASTEXITCODE
        }
        finally { Pop-Location }
    }
    if ($code -ne 0 -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Fail-Start 41 "playwright" "Chromium 可执行文件探针失败" "检查网络与 var/runtime/playwright 后重试"
    }
    $script:ChromiumExecutable = [IO.Path]::GetFullPath($path)
    $script:ChromiumDetail = "Playwright 管理 · 已确认"
    $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE = $script:ChromiumExecutable
}

function Write-ReleaseRuntimeState {
    $path = Join-Path $script:VarDir "runtime\runtime-state.json"
    $existing = $null
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        try { $existing = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $existing = $null }
    }
    $current = @(
        $script:PythonEnvironmentPath,
        (Split-Path -Parent $script:UvExecutable),
        $env:PLAYWRIGHT_BROWSERS_PATH
    ) | ForEach-Object { [IO.Path]::GetFullPath([string]$_) } | Select-Object -Unique
    $previous = @()
    if ($null -ne $existing -and $null -ne $existing.current_paths) {
        $previous = @($existing.current_paths | Where-Object { $_ -notin $current })
    }
    $payload = [ordered]@{
        schema_version = "1"
        mode = "release"
        fingerprint = $env:JIEJIAN_RUNTIME_FINGERPRINT
        current_paths = $current
        previous_paths = @($previous | Select-Object -First 3)
        python_sha256 = Get-FileDigest $script:PythonExecutable
        chromium_sha256 = Get-FileDigest $script:ChromiumExecutable
        last_successful_usage = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    }
    $temporary = Join-Path (Split-Path -Parent $path) ("runtime-state-{0}.tmp" -f [guid]::NewGuid().ToString("N"))
    $backup = Join-Path (Split-Path -Parent $path) ("runtime-state-{0}.bak" -f [guid]::NewGuid().ToString("N"))
    [IO.File]::WriteAllText($temporary, ($payload | ConvertTo-Json -Depth 6 -Compress), $script:Utf8Encoding)
    try {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            [IO.File]::Replace([string]$temporary, [string]$path, [string]$backup, $true)
        } else {
            [IO.File]::Move([string]$temporary, [string]$path)
        }
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    }
}
