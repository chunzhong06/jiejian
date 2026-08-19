#Requires -Version 5.1
# =============================================================================
# Windows 一键启动编排
#
# 定位
#   start.cmd 与界鉴 Python、Playwright、前端运行环境之间的首次准备和启动边界
#
# 职责
#   选择 Conda 或 uv｜执行迁移和环境诊断｜构建前端并启动本地控制面
#
# 边界
#   只准备本地运行依赖与产品进程；失败必须保留稳定退出码并完成子进程清理。
#
# 调用链
#   start.cmd / user shell → scripts/start.ps1 → package CLI / pnpm / Playwright
# =============================================================================

[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$VarDir = "",
    [switch]$PrepareOnly,
    [switch]$ForcePrepare,
    [Parameter(DontShow = $true)][switch]$DisplaySpinnerProcess,
    [Parameter(DontShow = $true)][string]$DisplaySpinnerStage = "startup",
    [Parameter(DontShow = $true)][switch]$DisplaySpinnerAscii
)

$ErrorActionPreference = "Stop"
$script:ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($VarDir)) {
    $VarDir = Join-Path $script:ProjectRoot "var"
} elseif (-not [IO.Path]::IsPathRooted($VarDir)) {
    $VarDir = Join-Path $script:ProjectRoot $VarDir
}
$script:VarDir = [IO.Path]::GetFullPath($VarDir)
$script:LogDir = Join-Path $script:VarDir "logs"
$script:StartupDir = Join-Path $script:VarDir "startup"
$script:StatePath = Join-Path $script:StartupDir "prepare-state.json"
$script:LogPath = Join-Path $script:LogDir ("startup-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$script:FailureStage = "startup"
$script:FailureCode = 0
$script:CondaExecutable = $null
$script:UvExecutable = $null
$script:PythonRunner = $null
$script:PackageRunner = $null
$script:PythonEnvironmentType = $null
$script:PythonEnvironmentPath = $null
$script:UvVersion = $null
$script:DownloadTemp = $null
$script:NodeVersion = $null
$script:PnpmVersion = $null
$script:CondaVersion = $null
$script:PythonVersion = $null
$script:PythonFingerprint = $null
$script:NodeDependenciesFingerprint = $null
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
$script:OriginalLocation = (Get-Location).Path
$script:DisplayStageName = $null
$script:DisplayStageTimer = $null
$script:DisplayStageSkipped = $false
$script:DisplayStageIndex = 0
$script:DisplayInteractive = $false
$script:DisplayUnicode = $false
$script:WaitIndicatorProcess = $null

$script:Utf8Encoding = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
[Console]::InputEncoding = $script:Utf8Encoding
[Console]::OutputEncoding = $script:Utf8Encoding
$OutputEncoding = [Console]::OutputEncoding

try {
    $script:DisplayInteractive = -not [Console]::IsOutputRedirected
    $script:DisplayUnicode = $script:DisplayInteractive -and
        [Console]::OutputEncoding.CodePage -eq 65001 -and
        $Host.UI.RawUI.WindowSize.Width -ge 72
} catch {
    $script:DisplayInteractive = $false
    $script:DisplayUnicode = $false
}



# 上下文变量初始化后再加载四个职责模块，确保 dot-source 只共享本轮启动状态。
foreach ($module in @("presentation.ps1", "state.ps1", "runtime.ps1", "product.ps1")) {
    . (Join-Path $PSScriptRoot "startup\$module")
}

if ($DisplaySpinnerProcess) {
    try { Invoke-WaitIndicatorProcess $DisplaySpinnerStage ([bool]$DisplaySpinnerAscii) } catch { }
    exit 0
}

try {
    # --- 启动环节：检查运行环境 ---
    Set-Location -LiteralPath $script:ProjectRoot
    Write-Banner
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    Start-DisplayStage 1 "检查运行环境"
    Write-Stage "preflight" "检查 Node.js 与 pnpm"
    Test-NodeAndPnpm
    Write-DisplayResult "Node.js" "完成" $false $script:NodeVersion
    Write-DisplayResult "pnpm" "完成" $false $script:PnpmVersion
    Write-DisplayResult "PowerShell" "完成" $true $PSVersionTable.PSVersion.ToString()
    New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null
    Load-PrepareState
    Write-Startup "项目根: $script:ProjectRoot`n运行目录: $script:VarDir`n模式: $(if($PrepareOnly){'PrepareOnly'}else{'serve'})`n日志: $script:LogPath`nNode=$script:NodeVersion pnpm=$script:PnpmVersion"
    Complete-DisplayStage "完成"
    # --- 启动环节：准备 Python ---
    Start-DisplayStage 2 "准备 Python"
    Write-Stage "python" "选择并准备 Python 环境"
    $pythonFingerprint = Prepare-PythonDependencies
    $criticalFacts = @{
        powershell = $PSVersionTable.PSVersion.ToString()
        python = $script:PythonVersion
        node = $script:NodeVersion
        pnpm = $script:PnpmVersion
        environment_type = $script:PythonEnvironmentType
        environment_path = $script:PythonEnvironmentPath
        conda_version = $script:CondaVersion
        uv_version = $script:UvVersion
    }
    $criticalFingerprint = Get-StageFingerprint @() $criticalFacts
    if (Test-PhaseHit "critical_runtime" $criticalFingerprint) {
        Write-Startup "[critical_runtime] 跳过：运行时身份指纹命中"
    } else {
        Set-PhaseState "critical_runtime" $criticalFingerprint $criticalFacts
    }
    Write-PythonEnvironment
    Write-DisplayResult "Python" "完成" $false $script:PythonVersion
    Write-DisplayResult "Python 依赖" "完成" $false
    Write-DisplayResult "运行环境" "完成" $true ("{0} · {1}" -f $script:PythonEnvironmentType, $script:PythonEnvironmentPath)
    Complete-DisplayStage
    Start-DisplayStage 3 "准备浏览器"
    Write-Stage "playwright" "安装或校验 Chromium"
    Prepare-Playwright $pythonFingerprint
    Write-DisplayResult "Chromium" "完成" $true
    Complete-DisplayStage
    # --- 启动环节：准备数据 ---
    Start-DisplayStage 4 "准备数据"
    Write-Stage "doctor" "运行环境诊断"
    Invoke-Package @("--var-dir", $script:VarDir, "doctor", "--json") "doctor" 42
    Write-DisplayResult "环境诊断" "完成" $false
    Write-Stage "migration" "升级 VarDir 数据库"
    Prepare-Migration
    $databaseRevision = Get-DatabaseRevision (Join-Path $script:VarDir "jiejian.db")
    Write-DisplayResult "本地数据" "完成" $true ("修订 {0}" -f $databaseRevision)
    Complete-DisplayStage
    Start-DisplayStage 5 "准备界面"
    Write-Stage "frontend" "按指纹安装并构建前端"
    Prepare-Frontend
    Write-DisplayResult "前端依赖" "完成" $false ("pnpm {0}" -f $script:PnpmVersion)
    Write-DisplayResult "前端资源" "完成" $true
    Complete-DisplayStage "完成"
    Start-DisplayStage 6 "启动界鉴"
    if ($PrepareOnly) {
        Write-Stage "prepare" "确认准备完成"
        Write-Startup "准备完成: $script:VarDir"
        Write-DisplayResult "启动条件" "完成" $true ("运行目录：{0}" -f $script:VarDir)
        Complete-DisplayStage
        exit 0
    }
    # --- 启动环节：把控制权交给正式 serve 入口 ---
    Write-Stage "serve" "启动本地控制面"
    Invoke-Package @(
        "--var-dir", $script:VarDir,
        "serve", "--open",
        "--frontend-dir", (Join-Path $script:ProjectRoot "product\frontend\dist")
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
    Set-Location -LiteralPath $script:OriginalLocation
}
