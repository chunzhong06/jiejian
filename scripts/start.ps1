#Requires -Version 5.1
# =============================================================================
# Windows 一键启动编排
#
# 定位
#   start.cmd 与预构建 Wheel、uv 私有 Python、Chromium 及本地控制面之间的正式启动边界
#
# 职责
#   校验固定发布资源｜准备版本化私有运行时｜诊断迁移并启动本地控制面
#
# 边界
#   不调用 Conda、Node、pnpm 或前端构建；失败必须保留稳定退出码并完成子进程清理。
#
# 调用链
#   start.cmd / user shell → scripts/start.ps1 → 已安装 package CLI / Playwright
# =============================================================================

[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$VarDir = "",
    [ValidateSet("Interactive", "Gui", "Cli", "Prepare")]
    [string]$Mode = "Interactive",
    [switch]$ForcePrepare,
    [Parameter(DontShow = $true)][switch]$DisplaySpinnerProcess,
    [Parameter(DontShow = $true)][string]$DisplaySpinnerStage = "startup",
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
$script:ReleaseLaunchRoot = Join-Path $script:VarDir "runtime\launch\release"
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

$script:Utf8Encoding = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
[Console]::InputEncoding = $script:Utf8Encoding
[Console]::OutputEncoding = $script:Utf8Encoding
$OutputEncoding = [Console]::OutputEncoding

try {
    $script:DisplayInteractive = -not [Console]::IsInputRedirected -and
        -not [Console]::IsOutputRedirected
    $script:DisplayUnicode = $script:DisplayInteractive -and
        [Console]::OutputEncoding.CodePage -eq 65001 -and
        $Host.UI.RawUI.WindowSize.Width -ge 72
    $supportsVirtualTerminal = $false
    try { $supportsVirtualTerminal = [bool]$Host.UI.SupportsVirtualTerminal } catch { $supportsVirtualTerminal = $false }
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



# 上下文变量初始化后再加载职责模块，正式启动只调用发布环境准备能力。
foreach ($module in @("presentation.ps1", "state.ps1", "runtime.ps1", "release.ps1", "product.ps1")) {
    . (Join-Path $PSScriptRoot "startup\$module")
}

if ($DisplaySpinnerProcess) {
    try { Invoke-WaitIndicatorProcess $DisplaySpinnerStage ([bool]$DisplaySpinnerAscii) } catch { }
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
    Enter-ReleasePrepareLock

    # 正式启动的准备锁先于工具、状态、数据库和缓存读写，避免并发修改同一运行时。
    Start-DisplayStage 1 "检查运行环境"
    Write-Stage "preflight" "检查正式发布资源与固定工具链"
    Load-PrepareState
    $toolchain = Read-ReleaseToolchain
    $null = Get-ReleaseWheel
    Resolve-ReleaseUv $toolchain
    Write-DisplayResult "固定工具链" "完成" $false ("uv {0}" -f $script:UvVersion)
    Write-DisplayResult "前端资源" "完成" $false "Wheel 内预构建资源"
    Write-DisplayResult "Node.js / pnpm" "跳过" $false "正式运行不需要"
    Write-DisplayResult "PowerShell" "完成" $true $PSVersionTable.PSVersion.ToString()
    Write-Startup "项目根: $script:ProjectRoot`n运行目录: $script:VarDir`n模式: release/$script:FinalMode`n日志: $script:LogPath`nuv=$script:UvVersion`nNode/pnpm=正式运行不需要"
    Complete-DisplayStage "完成"

    Start-DisplayStage 2 "准备 Python"
    Write-Stage "python" "准备 uv 私有 Python 与安装 Wheel"
    Prepare-ReleasePython $toolchain
    Write-PythonEnvironment
    Write-DisplayResult "Python" "完成" $false $script:PythonVersion
    Write-DisplayResult "Python 依赖" "完成" $false $script:PythonDependenciesDetail
    Write-DisplayResult "运行环境" "完成" $true ("{0} · {1}" -f $script:PythonEnvironmentType, $script:PythonEnvironmentPath)
    Complete-DisplayStage
    Start-DisplayStage 3 "准备浏览器"
    Write-Stage "playwright" "准备或校验正式 Chromium"
    Prepare-ReleaseChromium
    Write-DisplayResult "Chromium" "完成" $true $script:ChromiumDetail
    Complete-DisplayStage
    Write-RuntimeSummary

    Start-DisplayStage 4 "准备数据"
    Write-Stage "doctor" "运行环境诊断"
    Set-Location -LiteralPath $script:ReleaseLaunchRoot
    Invoke-Package @("--var-dir", $script:VarDir, "doctor", "--json") "doctor" 42
    Write-DisplayResult "环境诊断" "完成" $false
    Write-Stage "migration" "升级本地数据库"
    Prepare-Migration
    Write-DisplayResult "本地数据" "完成" $true $script:MigrationDetail
    Complete-DisplayStage

    Start-DisplayStage 5 "准备界面"
    Write-Stage "frontend" "确认预构建前端与运行时引用"
    Confirm-ReleaseFrontend
    Write-ReleaseRuntimeState
    Write-DisplayResult "前端资源" "完成" $false $script:FrontendDist
    Write-DisplayResult "运行时状态" "完成" $true "保留当前与上一版本引用"
    Complete-DisplayStage "完成"
    Exit-ReleasePrepareLock

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
    # --- 启动环节：把控制权交给正式 serve 入口 ---
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
    Exit-ReleasePrepareLock
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
