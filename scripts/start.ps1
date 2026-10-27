#Requires -Version 5.1
# 源码启动入口：准备受控环境并将服务生命周期交给产品 CLI。

[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$VarDir = "",
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [ValidateSet("Interactive", "Gui", "Cli", "Prepare")]
    [string]$Mode = "Gui",
    [ValidateSet("Managed", "System")][string]$Browser = "Managed",
    [switch]$ForcePrepare,
    [Parameter(DontShow = $true)][switch]$DisplaySpinnerProcess,
    [Parameter(DontShow = $true)][string]$DisplaySpinnerStage = "startup",
    [Parameter(DontShow = $true)][long]$DisplaySpinnerStartedAt = 0,
    [Parameter(DontShow = $true)][string]$DisplaySpinnerStopEvent = "",
    [Parameter(DontShow = $true)][switch]$DisplaySpinnerAscii,
    [Parameter(DontShow = $true)][switch]$DisplaySpinnerPanel
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "development/session.ps1")
Save-CallerEnvironment
try {
    . (Join-Path $PSScriptRoot "development/startup/context.ps1")
    Initialize-StartupContext (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path $VarDir $Mode
    $OutputEncoding = [Console]::OutputEncoding

    # 上下文变量初始化后再加载职责模块；源码准备由 dev.ps1 独占准备锁并返回可信回执。
    foreach ($module in @("presentation.ps1", "runtime.ps1", "source.ps1", "product.ps1")) {
        . (Join-Path $PSScriptRoot "development/startup\$module")
    }

    if ($DisplaySpinnerProcess) {
        try { Invoke-WaitIndicatorProcess $DisplaySpinnerStage ([bool]$DisplaySpinnerAscii) $DisplaySpinnerStartedAt $DisplaySpinnerStopEvent ([bool]$DisplaySpinnerPanel) } catch { }
        exit 0
    }
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
    Invoke-Package @("--var-dir", $script:VarDir, "--json", "system", "doctor") "doctor" 42
    Write-Stage "frontend" "确认 var/runtime/frontend 源码构建"
    Confirm-SourceFrontend
    Write-DisplayResult "环境诊断" "完成" $false
    Write-DisplayResult "前端资源" "完成" $false $script:FrontendDist
    Write-DisplayResult "本地数据" "完成" $false "已初始化并校验"
    Write-DisplayResult "构建状态" "完成" $true $frontendStatus
    Complete-DisplayStage

    Start-DisplayStage 6 "启动界鉴"
    if ($script:FinalMode -eq "Interactive") {
        $script:FinalMode = Select-StartupMode
    }
    if ($script:FinalMode -eq "Prepare") {
        Write-Stage "prepare" "确认准备完成"
        Write-Startup "准备完成: $script:VarDir"
        Write-DisplayResult "启动条件" "完成" $true ("运行目录：{0}" -f $script:VarDir)
        Set-StartupStatus "准备完成" "环境已经准备好" "本次只准备环境，没有启动应用服务。"
        Complete-DisplayStage
        exit 0
    }
    if ($script:FinalMode -eq "Cli") {
        if ($script:CliEntryMode -eq "Status") {
            Write-Stage "status" "打开命令行工作台"
            Invoke-CliShell $true
            Write-DisplayResult "命令行工作台" "已退出" $true
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
        "serve", "--open", "--browser", $Browser.ToLowerInvariant(), "--port", [string]$Port,
        "--frontend-dir", $script:FrontendDist,
        "--official-sample-root", (Join-Path $script:ProjectRoot "samples\web\digital_gallery")
    ) "serve" 50
    Write-DisplayResult "本地服务" "已停止" $true
    Set-StartupStatus "已停止" "界鉴已停止" "本次服务已退出，保存的资料仍保留在运行目录。"
    Complete-DisplayStage
    exit 0
} catch {
    if ($script:FailureCode -gt 0) {
        exit $script:FailureCode
    }
    if (Get-Command Fail-Start -ErrorAction SilentlyContinue) {
        Fail-Start (Get-StageFailureCode $script:FailureStage) $script:FailureStage ("启动编排失败: " + $_.Exception.Message) (Get-RecoveryCommand)
    } else {
        [Console]::Error.WriteLine("启动组件加载失败：" + $_.Exception.Message)
        exit 40
    }
} finally {
    # --- 阶段：恢复调用者环境并精确清理本轮临时资源 ---
    try {
        if (Get-Command Stop-WaitIndicator -ErrorAction SilentlyContinue) { Stop-WaitIndicator }
        if (Get-Command Close-StartupPanel -ErrorAction SilentlyContinue) { Close-StartupPanel }
    } finally { Restore-CallerEnvironment }

}
