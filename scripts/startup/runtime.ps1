# =============================================================================
# 启动命令与失败边界
#
# 定位
#   start.ps1 对外部准备命令、产品 CLI 和稳定失败信息的公共执行层
#
# 职责
#   记录外部命令与退出码｜控制等待动画｜形成面向用户的可恢复失败
#
# 边界
#   不准备任何工具或依赖，不实现 Conda、uv、Node、pnpm、数据库或业务服务逻辑。
# =============================================================================

function Get-StageDisplayName([string]$Stage) {
    $names = @{
        "arguments" = "启动参数"
        "mode" = "启动方式"
        "preflight" = "源码运行资源"
        "source-prepare" = "源码运行环境"
        "prepare-lock" = "运行环境准备锁"
        "conda" = "Python 环境"
        "uv" = "Python 环境"
        "python" = "Python 环境"
        "python-dependencies" = "Python 依赖"
        "node" = "Node.js 环境"
        "pnpm" = "pnpm 环境"
        "playwright" = "浏览器环境"
        "doctor" = "运行环境诊断"
        "migration" = "本地数据准备"
        "frontend-install" = "前端依赖"
        "frontend-build" = "前端构建"
        "serve" = "本地服务"
        "cli" = "命令行界面"
    }
    if ($names.ContainsKey($Stage)) { return $names[$Stage] }
    return $Stage
}

function Fail-Start([int]$Code, [string]$Stage, [string]$Diagnostic, [string]$Recovery) {
    $script:FailureStage = $Stage
    $script:FailureCode = $Code
    Write-Startup ("失败阶段: {0}`n诊断: {1}`n恢复命令: {2}`n日志: {3}" -f $Stage, $Diagnostic, $Recovery, $script:LogPath)
    if ($null -ne $script:DisplayStageTimer) { Complete-DisplayStage "失败" }
    $cross = if ($script:DisplayUnicode) { "×" } else { "FAILED" }
    $branch = if ($script:DisplayUnicode) { "  └─" } else { "  `--" }
    $displayCode = "STARTUP_" + (($Stage -replace '[^a-zA-Z0-9]+', '_').Trim('_').ToUpperInvariant())
    $displayStage = Get-StageDisplayName $Stage
    Write-Host ""
    Write-Host ("{0} 启动未完成" -f $cross) -ForegroundColor Red
    Write-Host ""
    Write-Host "  失败阶段" -ForegroundColor Red
    Write-Host ("{0} {1}" -f $branch, $displayStage) -ForegroundColor Red
    Write-Host ""
    Write-Host "  原因" -ForegroundColor Red
    Write-Host ("{0} {1}" -f $branch, $Diagnostic) -ForegroundColor Red
    Write-Host ""
    Write-Host "  如何解决" -ForegroundColor Yellow
    Write-Host ("{0} {1}" -f $branch, $Recovery) -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  日志" -ForegroundColor Gray
    Write-Host ("{0} {1}" -f $branch, ([IO.Path]::GetFullPath($script:LogPath))) -ForegroundColor Gray
    Write-Host ""
    Write-Host "  错误代码" -ForegroundColor Red
    Write-Host ("{0} {1}（退出码 {2}）" -f $branch, $displayCode, $Code) -ForegroundColor Red
    Write-Host ""
    exit $Code
}

# 外部 stdout/stderr 只写启动日志；serve ready 标记例外，用来终止动画并提示安全退出。
function Invoke-External(
    [string]$Stage,
    [object[]]$Command,
    [object[]]$Arguments,
    [int]$FailureCode = 40,
    [string]$Recovery = "",
    [bool]$EchoOutput = $false
) {
    $script:DisplayStageSkipped = $false
    $script:FailureStage = $Stage
    $fullCommand = @($Command) + @($Arguments)
    Write-Startup ("[{0}] & {1} {2}" -f $Stage, $fullCommand[0], (($fullCommand | Select-Object -Skip 1) -join " "))
    [object[]]$invokeArguments = @()
    if ($fullCommand.Count -gt 1) {
        $invokeArguments = @($fullCommand[1..($fullCommand.Count - 1)])
    }
    $previousErrorActionPreference = $ErrorActionPreference
    $waitIndicatorStarted = $false
    try {
        $ErrorActionPreference = "Continue"
        if (-not $EchoOutput) {
            Start-WaitIndicator $Stage
            $waitIndicatorStarted = $true
        }
        if ($EchoOutput) {
            & $fullCommand[0] @invokeArguments 2>&1 |
                ForEach-Object {
                    $line = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { [string]$_ }
                    [IO.File]::AppendAllText($script:LogPath, $line + [Environment]::NewLine, $script:Utf8Encoding)
                    Write-Host $line
                } |
                Out-Null
        } else {
            & $fullCommand[0] @invokeArguments 2>&1 |
                ForEach-Object {
                    $line = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { [string]$_ }
                    [IO.File]::AppendAllText($script:LogPath, $line + [Environment]::NewLine, $script:Utf8Encoding)
                    if (-not $script:ServeReadyObserved -and $line.StartsWith("__JIEJIAN_SERVE_READY__:")) {
                        $script:ServeReadyObserved = $true
                        Stop-WaitIndicator
                        Write-Host ""
                        if ($line.EndsWith("browser-opened")) {
                            Write-Host "界鉴网页已打开。" -ForegroundColor Cyan
                        } else {
                            Write-Host "界鉴服务已启动，但未能自动打开网页。" -ForegroundColor Yellow
                            Write-Host "请在浏览器访问 http://127.0.0.1:8765/" -ForegroundColor Gray
                        }
                        Write-Host "请使用网页右上角“退出界鉴”，或在此终端按 Ctrl+C 安全退出。" -ForegroundColor Gray
                        Write-Host "此终端会保持运行，用于管理服务、Worker 和浏览器资源。" -ForegroundColor DarkGray
                    }
                } |
                Out-Null
        }
        $code = $LASTEXITCODE
    } finally {
        if ($waitIndicatorStarted) { Stop-WaitIndicator }
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($code -ne 0) {
        if ([string]::IsNullOrWhiteSpace($Recovery)) { $Recovery = Get-RecoveryCommand }
        Fail-Start $FailureCode $Stage "外部命令返回 $code" $Recovery
    }
}
