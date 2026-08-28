# =============================================================================
# 源码仓库运行环境接入
#
# 定位
#   start.cmd 与 scripts/dev.ps1 生成的受控源码运行回执之间的信任边界
#
# 职责
#   触发 Conda/uv/editable 源码准备｜校验回执绝对路径｜恢复主进程与子进程环境
#
# 边界
#   不安装 Wheel，不从源码目录读取运行产物；开发工具复用 var/development，前端副本只来自本轮 VarDir。
# =============================================================================

function Get-SourceReceiptPath {
    return [IO.Path]::GetFullPath((Join-Path $script:VarDir "runtime\source\receipt.json"))
}

function Invoke-SourcePreparation {
    $shellName = if ($PSEdition -eq "Core") { "pwsh.exe" } else { "powershell.exe" }
    $shell = Join-Path $PSHOME $shellName
    if (-not (Test-Path -LiteralPath $shell -PathType Leaf)) {
        Fail-Start 40 "source-prepare" "无法定位当前 PowerShell 入口" "修复 PowerShell 后重新运行 start.cmd"
    }
    $arguments = @(
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $script:ProjectRoot "scripts\dev.ps1"),
        "prepare",
        "-VarDir", $script:VarDir
    )
    if ($ForcePrepare) { $arguments += "-ForcePrepare" }
    Invoke-External "source-prepare" @($shell) $arguments 40 (
        ".\scripts\dev.ps1 sync -VarDir `"{0}`"" -f $script:VarDir
    )
}

function Test-ExactPath([string]$Actual, [string]$Expected) {
    if ([string]::IsNullOrWhiteSpace($Actual)) { return $false }
    try {
        return [IO.Path]::GetFullPath($Actual).Equals(
            [IO.Path]::GetFullPath($Expected),
            [StringComparison]::OrdinalIgnoreCase
        )
    } catch { return $false }
}

function Import-SourceReceipt {
    $receiptPath = Get-SourceReceiptPath
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
        Fail-Start 40 "source-prepare" "源码准备没有生成运行环境回执" (Get-RecoveryCommand)
    }
    try {
        $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Fail-Start 40 "source-prepare" "源码运行环境回执不是有效 JSON" (Get-RecoveryCommand)
    }
    $expectedFrontend = Join-Path $script:VarDir "runtime\frontend"
    $identity = $receipt.python.report
    $valid = $receipt.schema_version -eq "1" -and
        $receipt.runtime_mode -eq "development" -and
        (Test-ExactPath ([string]$receipt.project_root) $script:ProjectRoot) -and
        (Test-ExactPath ([string]$receipt.var_dir) $script:VarDir) -and
        (Test-ExactPath ([string]$receipt.frontend.dist) $expectedFrontend) -and
        $identity.ok -eq $true -and
        $identity.project_distribution.editable -eq $true -and
        (Test-ExactPath ([string]$identity.project_distribution.source_root) $script:ProjectRoot)
    if (-not $valid) {
        Fail-Start 40 "source-prepare" "源码运行环境回执与当前仓库或 editable 安装不一致" (Get-RecoveryCommand)
    }

    $requiredFiles = @(
        [string]$receipt.python.executable,
        [string]$receipt.uv.executable,
        [string]$receipt.playwright.executable,
        (Join-Path ([string]$receipt.frontend.dist) "index.html")
    )
    if ($requiredFiles | Where-Object { [string]::IsNullOrWhiteSpace($_) -or -not (Test-Path -LiteralPath $_ -PathType Leaf) }) {
        Fail-Start 40 "source-prepare" "源码运行环境回执引用的必要产物缺失" (Get-RecoveryCommand)
    }

    $script:PythonExecutable = [IO.Path]::GetFullPath([string]$receipt.python.executable)
    $script:PythonEnvironmentPath = [IO.Path]::GetFullPath([string]$receipt.python.environment_path)
    $script:PythonEnvironmentType = [string]$receipt.python.environment_type
    $script:PythonVersion = [string]$receipt.python.version
    $script:PythonFingerprint = [string]$receipt.python.runtime_fingerprint
    $script:PythonEnvironmentReport = $identity
    $script:PythonRunner = @($script:PythonExecutable, "-B")
    $script:PackageRunner = @($script:PythonExecutable, "-B", "-m", "product.backend.cli")
    $script:UvExecutable = [IO.Path]::GetFullPath([string]$receipt.uv.executable)
    $script:UvVersion = [string]$receipt.uv.version
    $script:NodeExecutable = [string]$receipt.node.executable
    $script:NodeVersion = [string]$receipt.node.version
    $script:PnpmExecutable = [string]$receipt.pnpm.executable
    $script:PnpmVersion = [string]$receipt.pnpm.version
    $script:ChromiumExecutable = [IO.Path]::GetFullPath([string]$receipt.playwright.executable)
    $script:ChromiumDetail = "已确认 · $script:ChromiumExecutable"
    $script:FrontendDist = [IO.Path]::GetFullPath([string]$receipt.frontend.dist)
    $script:FrontendDependenciesDetail = [string]$receipt.frontend.dependencies
    $script:FrontendBuildDetail = [string]$receipt.frontend.build_state
    $script:PythonDependenciesDetail = "uv.lock · editable 当前源码 · 已确认"

    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONNOUSERSITE = "1"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    $env:UV_PROJECT_ENVIRONMENT = $script:PythonEnvironmentPath
    $env:UV_CACHE_DIR = Join-Path $script:DevelopmentRoot "cache\uv"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $script:DevelopmentRoot "tools\python\installations"
    $env:PLAYWRIGHT_BROWSERS_PATH = [string]$receipt.playwright.browsers_path
    $env:JIEJIAN_VAR_DIR = $script:VarDir
    $env:JIEJIAN_PROJECT_ROOT = $script:ProjectRoot
    $env:JIEJIAN_RUNTIME_MODE = "development"
    $env:JIEJIAN_RUNTIME_FINGERPRINT = $script:PythonFingerprint
    $env:JIEJIAN_PYTHON_EXECUTABLE = $script:PythonExecutable
    $env:JIEJIAN_PYTHON_ENVIRONMENT_PATH = $script:PythonEnvironmentPath
    $env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE = $script:PythonEnvironmentType
    $env:JIEJIAN_UV_EXECUTABLE = $script:UvExecutable
    $env:JIEJIAN_UV_VERSION = $script:UvVersion
    $env:JIEJIAN_TOOLCHAIN_MANIFEST = $script:ToolchainPath
    $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE = $script:ChromiumExecutable
    $env:JIEJIAN_FRONTEND_DIST = $script:FrontendDist
    $env:JIEJIAN_FRONTEND_DEPENDENCIES = $script:FrontendDependenciesDetail
    $env:JIEJIAN_FRONTEND_BUILD_STATE = $script:FrontendBuildDetail
    if (-not [string]::IsNullOrWhiteSpace($script:NodeExecutable)) {
        $env:JIEJIAN_NODE_EXECUTABLE = $script:NodeExecutable
        $env:JIEJIAN_NODE_VERSION = $script:NodeVersion
    }
    if (-not [string]::IsNullOrWhiteSpace($script:PnpmExecutable)) {
        $env:JIEJIAN_PNPM_EXECUTABLE = $script:PnpmExecutable
        $env:JIEJIAN_PNPM_VERSION = $script:PnpmVersion
    }
}

function Prepare-SourceRuntime {
    Invoke-SourcePreparation
    Import-SourceReceipt
}

function Confirm-SourceFrontend {
    $index = Join-Path $script:FrontendDist "index.html"
    $expected = Join-Path $script:VarDir "runtime\frontend"
    if (-not (Test-ExactPath $script:FrontendDist $expected) -or -not (Test-Path -LiteralPath $index -PathType Leaf)) {
        Fail-Start 44 "frontend-build" "源码启动前端不属于 var/runtime/frontend 或入口缺失" (Get-RecoveryCommand)
    }
}
