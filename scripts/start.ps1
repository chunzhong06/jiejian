#Requires -Version 5.1
# =============================================================================
# Windows 一键启动编排
#
# 定位
#   start.cmd 与当前仓库 editable 源码、受控依赖及本地控制面之间的一键启动边界
#
# 职责
#   准备 Conda/uv/editable 源码｜按指纹构建前端｜诊断并启动本地控制面
#
# 边界
#   Wheel 不参与普通启动；全部运行产物只进入 var，失败保留稳定退出码并清理子进程。
#
# 调用链
#   start.cmd / user shell → scripts/start.ps1 → scripts/dev.ps1 prepare → editable package CLI
# =============================================================================

[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$VarDir = "",
    [ValidateSet("Interactive", "Gui", "Cli", "Prepare")]
    [string]$Mode = "Interactive",
    [switch]$ForcePrepare,
    [Parameter(DontShow = $true)][switch]$DisplaySpinnerProcess,
    [Parameter(DontShow = $true)][string]$DisplaySpinnerStage = "startup",
    [Parameter(DontShow = $true)][long]$DisplaySpinnerStartedAt = 0,
    [Parameter(DontShow = $true)][switch]$DisplaySpinnerAscii
)

$ErrorActionPreference = "Stop"
$script:ModeExplicit = $PSBoundParameters.ContainsKey("Mode")
$script:FinalMode = $Mode
$script:ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($VarDir)) {
    $VarDir = Join-Path $script:ProjectRoot "var"
} elseif (-not [IO.Path]::IsPathRooted($VarDir)) {
    $VarDir = Join-Path $script:ProjectRoot $VarDir
}
$script:VarDir = [IO.Path]::GetFullPath($VarDir)
$script:LogDir = Join-Path $script:VarDir "logs\startup"
$script:StartupDir = Join-Path $script:VarDir "cache\startup"
$script:StatePath = Join-Path $script:StartupDir "prepare-state.json"
$script:LogPath = Join-Path $script:LogDir ("{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
$script:ToolchainPath = Join-Path $script:ProjectRoot "product\config\toolchain.json"
$script:StartupLogInitialized = $false
$script:FailureStage = "startup"
$script:FailureCode = 0
$script:CondaExecutable = $null
$script:UvExecutable = $null
$script:PythonRunner = $null
$script:PackageRunner = $null
$script:PythonExecutable = $null
$script:PythonEnvironmentType = $null
$script:PythonEnvironmentPath = $null
$script:UvVersion = $null
$script:DownloadTemp = $null
$script:NodeVersion = $null
$script:PnpmVersion = $null
$script:NodeExecutable = $null
$script:PnpmExecutable = $null
$script:PnpmRunner = $null
$script:CorepackExecutable = $null
$script:NodeArchitecture = $null
$script:NodeRequirement = $null
$script:PnpmRequirement = $null
$script:ToolchainFingerprint = $null
$script:NodeRuntimeDetail = $null
$script:PnpmRuntimeDetail = $null
$script:CondaVersion = $null
$script:PythonVersion = $null
$script:PythonFingerprint = $null
$script:NodeDependenciesFingerprint = $null
$script:PythonDependenciesDetail = $null
$script:ChromiumDetail = $null
$script:MigrationDetail = $null
$script:FrontendDependenciesDetail = $null
$script:FrontendBuildDetail = $null
$script:ChromiumExecutable = $null
$script:PythonEnvironmentReport = $null
$script:ServeReadyObserved = $false
$script:ServeStartupFailed = $false
$script:CliEntryMode = "Shell"
$script:PrepareLock = $null
$script:FrontendDist = $null
$script:PrepareState = [pscustomobject]@{
    schema_version = "1"
    phases = [pscustomobject]@{}
}
$script:SavedBytecode = $env:PYTHONDONTWRITEBYTECODE
$script:SavedUvProjectEnvironment = $env:UV_PROJECT_ENVIRONMENT
$script:SavedUvCacheDir = $env:UV_CACHE_DIR
$script:SavedUvPythonInstallDir = $env:UV_PYTHON_INSTALL_DIR
$script:SavedPythonUtf8 = $env:PYTHONUTF8
$script:SavedPythonIoEncoding = $env:PYTHONIOENCODING
$script:SavedPythonNoUserSite = $env:PYTHONNOUSERSITE
$script:SavedPythonPath = $env:PYTHONPATH
$script:SavedPythonHome = $env:PYTHONHOME
$script:SavedJiejianPythonExecutable = $env:JIEJIAN_PYTHON_EXECUTABLE
$script:SavedJiejianPythonEnvironmentPath = $env:JIEJIAN_PYTHON_ENVIRONMENT_PATH
$script:SavedJiejianPythonEnvironmentType = $env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE
$script:SavedJiejianNodeExecutable = $env:JIEJIAN_NODE_EXECUTABLE
$script:SavedJiejianNodeVersion = $env:JIEJIAN_NODE_VERSION
$script:SavedJiejianPnpmExecutable = $env:JIEJIAN_PNPM_EXECUTABLE
$script:SavedJiejianPnpmVersion = $env:JIEJIAN_PNPM_VERSION
$script:SavedJiejianPlaywrightExecutable = $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE
$script:SavedJiejianFrontendDependencies = $env:JIEJIAN_FRONTEND_DEPENDENCIES
$script:SavedPath = $env:PATH
$script:SavedCorepackHome = $env:COREPACK_HOME
$script:SavedCorepackDownloadPrompt = $env:COREPACK_ENABLE_DOWNLOAD_PROMPT
$script:SavedJiejianCorepackExecutable = $env:JIEJIAN_COREPACK_EXECUTABLE
$script:SavedPnpmHome = $env:PNPM_HOME
$script:SavedNpmConfigCache = $env:npm_config_cache
$script:SavedPlaywrightBrowsersPath = $env:PLAYWRIGHT_BROWSERS_PATH
$script:OriginalLocation = (Get-Location).Path
$script:DisplayStageName = $null
$script:DisplayStageTimer = $null
$script:DisplayStageSkipped = $false
$script:DisplayStageIndex = 0
$script:DisplayInteractive = $false
$script:DisplayUnicode = $false
$script:DisplayTrueColor = $false
$script:WaitIndicatorProcess = $null
$script:PrepareStatusOrder = @("toolchain", "python", "browser", "frontend-dependencies", "frontend-build", "database")
$script:PrepareStatusIndex = 0
$script:PrepareStatusState = @{}

$script:Utf8Encoding = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
[Console]::InputEncoding = $script:Utf8Encoding
[Console]::OutputEncoding = $script:Utf8Encoding
$OutputEncoding = [Console]::OutputEncoding

try {
    $script:DisplayInteractive = -not [Console]::IsInputRedirected -and
        -not [Console]::IsOutputRedirected
    $supportsVirtualTerminal = $false
    try { $supportsVirtualTerminal = [bool]$Host.UI.SupportsVirtualTerminal } catch { $supportsVirtualTerminal = $false }
    $script:DisplayUnicode = $script:DisplayInteractive -and
        [Console]::OutputEncoding.CodePage -eq 65001 -and
        $Host.UI.RawUI.WindowSize.Width -ge 72 -and
        $supportsVirtualTerminal
    $hasTerminalHint = -not [string]::IsNullOrWhiteSpace([string]$env:WT_SESSION) -or
        -not [string]::IsNullOrWhiteSpace([string]$env:COLORTERM) -or
        -not [string]::IsNullOrWhiteSpace([string]$env:ANSICON) -or
        [string]$env:ConEmuANSI -eq "ON" -or
        [string]$env:TERM_PROGRAM -match "^(vscode|WezTerm|Hyper)$" -or
        [string]$env:TERM -match "(xterm|ansi|cygwin|msys|vt100)"
    $script:DisplayTrueColor = $script:DisplayUnicode -and (
        $supportsVirtualTerminal -or $hasTerminalHint
    )
} catch {
    $script:DisplayInteractive = $false
    $script:DisplayUnicode = $false
    $script:DisplayTrueColor = $false
}



# 上下文变量初始化后再加载职责模块；源码准备由 dev.ps1 独占准备锁并返回可信回执。
foreach ($module in @("presentation.ps1", "runtime.ps1", "source.ps1", "product.ps1")) {
    . (Join-Path $PSScriptRoot "startup\$module")
}

if ($DisplaySpinnerProcess) {
    try { Invoke-WaitIndicatorProcess $DisplaySpinnerStage ([bool]$DisplaySpinnerAscii) $DisplaySpinnerStartedAt } catch { }
    exit 0
}

try {
    if ($script:FinalMode -eq "Interactive" -and -not $script:DisplayInteractive) {
        Fail-Start 40 "mode" "Interactive 模式需要可交互的输入和输出；请显式使用 -Mode Gui、-Mode Cli 或 -Mode Prepare" "使用 -Mode Gui、-Mode Cli 或 -Mode Prepare"
    }
    Set-Location -LiteralPath $script:ProjectRoot
    Write-Banner
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONNOUSERSITE = "1"
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $script:PrepareStatusIndex = 0
    $script:PrepareStatusState = @{}
    Start-DisplayStage 1 "准备工具链"
    Write-Stage "source-prepare" "准备当前仓库的受控源码运行环境"
    Prepare-SourceRuntime
    $frontendStatus = if ($script:FrontendBuildDetail -eq "reused") { "指纹命中，已复用" } else { "指纹变化，已构建" }
    Write-Startup "项目根: $script:ProjectRoot`n运行目录: $script:VarDir`n模式: source/$script:FinalMode`n日志: $script:LogPath`nuv=$script:UvVersion`n前端=$script:FrontendBuildDetail"

    # prepare 已经真实闭合工具链、Python、浏览器和界面；此处只进入本地数据核验，不重放前四阶段。
    if ($script:DisplayStageIndex -ne 5) { Start-DisplayStage 5 "检查本地数据" }
    Write-Stage "doctor" "运行环境诊断"
    Set-Location -LiteralPath $script:ProjectRoot
    Invoke-Package @("--var-dir", $script:VarDir, "--json", "doctor") "doctor" 42
    Write-Stage "frontend" "确认 var/runtime/frontend 源码构建"
    Confirm-SourceFrontend
    Write-DisplayResult "环境诊断" "完成" $false
    Write-DisplayResult "前端资源" "完成" $false $script:FrontendDist
    Write-DisplayResult "本地数据" "完成" $false "已迁移并校验"
    Write-DisplayResult "构建状态" "完成" $true $frontendStatus
    Complete-DisplayStage
    Write-RuntimeSummary

    Start-DisplayStage 6 "启动界鉴"
    if ($script:FinalMode -eq "Interactive") {
        $script:FinalMode = Select-StartupMode
    }
    if ($script:FinalMode -eq "Prepare") {
        Write-Stage "prepare" "确认准备完成"
        Write-Startup "准备完成: $script:VarDir"
        Write-DisplayResult "启动条件" "完成" $true ("运行目录：{0}" -f $script:VarDir)
        Complete-DisplayStage
        exit 0
    }
    if ($script:FinalMode -eq "Cli") {
        if ($script:CliEntryMode -eq "Guide") {
            Write-Stage "guide" "进入命令行引导"
            Invoke-CliShell $true
            Write-DisplayResult "命令行引导" "已退出" $true
        } else {
            Write-Stage "cli" "进入命令行会话"
            Invoke-CliShell
            Write-DisplayResult "命令行" "已退出" $true
        }
        Complete-DisplayStage
        exit 0
    }
    # --- 启动环节：把控制权交给当前仓库的统一 serve 入口 ---
    Write-Stage "serve" "启动本地控制面"
    Invoke-Package @(
        "--var-dir", $script:VarDir,
        "serve", "--open",
        "--frontend-dir", $script:FrontendDist
    ) "serve" 50
    Write-DisplayResult "本地服务" "已停止" $true
    Complete-DisplayStage
    exit 0
} catch {
    if ($script:FailureCode -gt 0) {
        exit $script:FailureCode
    }
    Fail-Start (Get-StageFailureCode $script:FailureStage) $script:FailureStage ("启动编排失败: " + $_.Exception.Message) (Get-RecoveryCommand)
} finally {
    # --- 阶段：恢复调用者环境并精确清理本轮临时资源 ---
    Stop-WaitIndicator
    if ($script:DownloadTemp -and (Test-Path -LiteralPath $script:DownloadTemp)) {
        Remove-Item -LiteralPath $script:DownloadTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($null -eq $script:SavedBytecode) { Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue } else { $env:PYTHONDONTWRITEBYTECODE = $script:SavedBytecode }
    if ($null -eq $script:SavedUvProjectEnvironment) { Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue } else { $env:UV_PROJECT_ENVIRONMENT = $script:SavedUvProjectEnvironment }
    if ($null -eq $script:SavedUvCacheDir) { Remove-Item Env:UV_CACHE_DIR -ErrorAction SilentlyContinue } else { $env:UV_CACHE_DIR = $script:SavedUvCacheDir }
    if ($null -eq $script:SavedUvPythonInstallDir) { Remove-Item Env:UV_PYTHON_INSTALL_DIR -ErrorAction SilentlyContinue } else { $env:UV_PYTHON_INSTALL_DIR = $script:SavedUvPythonInstallDir }
    if ($null -eq $script:SavedPythonUtf8) { Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue } else { $env:PYTHONUTF8 = $script:SavedPythonUtf8 }
    if ($null -eq $script:SavedPythonIoEncoding) { Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue } else { $env:PYTHONIOENCODING = $script:SavedPythonIoEncoding }
    if ($null -eq $script:SavedPythonNoUserSite) { Remove-Item Env:PYTHONNOUSERSITE -ErrorAction SilentlyContinue } else { $env:PYTHONNOUSERSITE = $script:SavedPythonNoUserSite }
    if ($null -eq $script:SavedPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $script:SavedPythonPath }
    if ($null -eq $script:SavedPythonHome) { Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue } else { $env:PYTHONHOME = $script:SavedPythonHome }
    if ($null -eq $script:SavedJiejianPythonExecutable) { Remove-Item Env:JIEJIAN_PYTHON_EXECUTABLE -ErrorAction SilentlyContinue } else { $env:JIEJIAN_PYTHON_EXECUTABLE = $script:SavedJiejianPythonExecutable }
    if ($null -eq $script:SavedJiejianPythonEnvironmentPath) { Remove-Item Env:JIEJIAN_PYTHON_ENVIRONMENT_PATH -ErrorAction SilentlyContinue } else { $env:JIEJIAN_PYTHON_ENVIRONMENT_PATH = $script:SavedJiejianPythonEnvironmentPath }
    if ($null -eq $script:SavedJiejianPythonEnvironmentType) { Remove-Item Env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE -ErrorAction SilentlyContinue } else { $env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE = $script:SavedJiejianPythonEnvironmentType }
    if ($null -eq $script:SavedJiejianNodeExecutable) { Remove-Item Env:JIEJIAN_NODE_EXECUTABLE -ErrorAction SilentlyContinue } else { $env:JIEJIAN_NODE_EXECUTABLE = $script:SavedJiejianNodeExecutable }
    if ($null -eq $script:SavedJiejianNodeVersion) { Remove-Item Env:JIEJIAN_NODE_VERSION -ErrorAction SilentlyContinue } else { $env:JIEJIAN_NODE_VERSION = $script:SavedJiejianNodeVersion }
    if ($null -eq $script:SavedJiejianPnpmExecutable) { Remove-Item Env:JIEJIAN_PNPM_EXECUTABLE -ErrorAction SilentlyContinue } else { $env:JIEJIAN_PNPM_EXECUTABLE = $script:SavedJiejianPnpmExecutable }
    if ($null -eq $script:SavedJiejianPnpmVersion) { Remove-Item Env:JIEJIAN_PNPM_VERSION -ErrorAction SilentlyContinue } else { $env:JIEJIAN_PNPM_VERSION = $script:SavedJiejianPnpmVersion }
    if ($null -eq $script:SavedJiejianPlaywrightExecutable) { Remove-Item Env:JIEJIAN_PLAYWRIGHT_EXECUTABLE -ErrorAction SilentlyContinue } else { $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE = $script:SavedJiejianPlaywrightExecutable }
    if ($null -eq $script:SavedJiejianFrontendDependencies) { Remove-Item Env:JIEJIAN_FRONTEND_DEPENDENCIES -ErrorAction SilentlyContinue } else { $env:JIEJIAN_FRONTEND_DEPENDENCIES = $script:SavedJiejianFrontendDependencies }
    if ($null -eq $script:SavedPath) { Remove-Item Env:PATH -ErrorAction SilentlyContinue } else { $env:PATH = $script:SavedPath }
    if ($null -eq $script:SavedCorepackHome) { Remove-Item Env:COREPACK_HOME -ErrorAction SilentlyContinue } else { $env:COREPACK_HOME = $script:SavedCorepackHome }
    if ($null -eq $script:SavedCorepackDownloadPrompt) { Remove-Item Env:COREPACK_ENABLE_DOWNLOAD_PROMPT -ErrorAction SilentlyContinue } else { $env:COREPACK_ENABLE_DOWNLOAD_PROMPT = $script:SavedCorepackDownloadPrompt }
    if ($null -eq $script:SavedJiejianCorepackExecutable) { Remove-Item Env:JIEJIAN_COREPACK_EXECUTABLE -ErrorAction SilentlyContinue } else { $env:JIEJIAN_COREPACK_EXECUTABLE = $script:SavedJiejianCorepackExecutable }
    if ($null -eq $script:SavedPnpmHome) { Remove-Item Env:PNPM_HOME -ErrorAction SilentlyContinue } else { $env:PNPM_HOME = $script:SavedPnpmHome }
    if ($null -eq $script:SavedNpmConfigCache) { Remove-Item Env:npm_config_cache -ErrorAction SilentlyContinue } else { $env:npm_config_cache = $script:SavedNpmConfigCache }
    if ($null -eq $script:SavedPlaywrightBrowsersPath) { Remove-Item Env:PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue } else { $env:PLAYWRIGHT_BROWSERS_PATH = $script:SavedPlaywrightBrowsersPath }
    Set-Location -LiteralPath $script:OriginalLocation
}
