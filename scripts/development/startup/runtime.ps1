# 启动命令与失败边界
# 记录外部命令与退出码、控制等待动画、形成面向用户的可恢复失败
# 不准备任何工具或依赖，不实现 Conda、uv、Node、pnpm、数据库或业务服务逻辑。

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
        "browser-download" = "浏览器下载与安装"
        "browser-verify" = "浏览器可执行文件核验"
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
    Stop-WaitIndicator
    if ($null -ne $script:DisplayStageTimer) { Complete-DisplayStage "失败" }
    $displayCode = "STARTUP_" + (($Stage -replace '[^a-zA-Z0-9]+', '_').Trim('_').ToUpperInvariant())
    $displayStage = Get-StageDisplayName $Stage
    $script:StartupPanelKeys = ""
    Set-StartupStatus "启动未完成" ("{0}未完成" -f $displayStage) $Diagnostic
    Close-StartupPanel
    # 恢复命令和日志路径不能截断，退出前留下可复制的完整文本。
    Write-Host ("建议：{0}" -f $Recovery) -ForegroundColor Yellow
    Write-Host ("日志：{0}" -f ([IO.Path]::GetFullPath($script:LogPath))) -ForegroundColor Gray
    Write-Host ("错误代码：{0}（退出码 {1}）" -f $displayCode, $Code) -ForegroundColor Red
    exit $Code
}

function Set-PrepareDisplayTask([string]$Token) {
    switch ($Token) {
        "toolchain" { if ($script:DisplayStageIndex -ne 1) { Start-DisplayStage 1 "准备工具链" } }
        "python" { if ($script:DisplayStageIndex -ne 2) { Start-DisplayStage 2 "准备 Python" } }
        "browser" { if ($script:DisplayStageIndex -ne 3) { Start-DisplayStage 3 "准备浏览器" } }
        "frontend-dependencies" { if ($script:DisplayStageIndex -ne 4) { Start-DisplayStage 4 "准备界面" } }
        "frontend-build" { if ($script:DisplayStageIndex -ne 4) { Start-DisplayStage 4 "准备界面" } }
        "database" { if ($script:DisplayStageIndex -ne 5) { Start-DisplayStage 5 "检查本地数据" } }
    }
    if ($script:DisplayInteractive -and -not [Console]::IsOutputRedirected) {
        Stop-WaitIndicator
        Start-WaitIndicator $Token
    }
}

function Complete-PrepareDisplayTask([string]$Token) {
    switch ($Token) {
        "toolchain" { Write-DisplayResult "工具链" "完成" $true; Complete-DisplayStage }
        "python" { Write-DisplayResult "Python 环境" "完成" $true; Complete-DisplayStage }
        "browser" { Write-DisplayResult "Chromium" "完成" $true; Complete-DisplayStage }
        "frontend-dependencies" { Write-DisplayResult "界面依赖" "完成" $false }
        "frontend-build" { Write-DisplayResult "界面构建" "完成" $true; Complete-DisplayStage }
        "database" { Write-DisplayResult "数据库准备" "完成" $false }
    }
}

function Handle-PrepareStatus([string]$Line) {
    $match = [regex]::Match(
        $Line,
        '^__JIEJIAN_PREPARE_STATUS__:(toolchain|python|browser|frontend-dependencies|frontend-build|database):(start|done)$'
    )
    if (-not $match.Success) { return $false }
    $token = $match.Groups[1].Value
    $state = $match.Groups[2].Value
    # Windows PowerShell 将 x.5 转 int 时可能向最近整数舍入；显式向下取整才能保持 start/done 成对。
    $expectedTokenIndex = [int]([Math]::Floor([double]$script:PrepareStatusIndex / 2.0))
    $expectedToken = [string]$script:PrepareStatusOrder[$expectedTokenIndex]
    $expectedState = if ($script:PrepareStatusIndex % 2 -eq 0) { "start" } else { "done" }
    if ($token -ne $expectedToken -or $state -ne $expectedState) { return $false }
    $script:PrepareStatusState[$token] = $state
    $script:PrepareStatusIndex += 1
    if ($state -eq "start") { Set-PrepareDisplayTask $token }
    else { Complete-PrepareDisplayTask $token }
    return $true
}

# 外部 stdout/stderr 只写启动日志；Python 状态事件是服务就绪事实的唯一来源。
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
    $prepareFailure = $null
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
                    if ($Stage -eq "source-prepare") { [void](Handle-PrepareStatus $line) }
                    if ($Stage -eq "source-prepare" -and $line.StartsWith("__JIEJIAN_PREPARE_FAILURE__:") -and $line.Length -le 4096) {
                        try { $prepareFailure = $line.Substring("__JIEJIAN_PREPARE_FAILURE__:".Length) | ConvertFrom-Json } catch { }
                    }
                    if ($Stage -eq "source-prepare" -and $line -in @("__JIEJIAN_BROWSER_PHASE__:download", "__JIEJIAN_BROWSER_PHASE__:verify")) {
                        Stop-WaitIndicator
                        $verifying = $line.EndsWith(":verify")
                        $script:StartupPanelTitle = if ($verifying) { "核验浏览器安装" } else { "下载并安装浏览器" }
                        $script:StartupPanelDetail = if ($verifying) { "下载已结束，正在确认浏览器可执行文件。" } else { "首次准备需要下载；到达 100% 后还需完成安装核验。" }
                        if ($script:StartupPanelActive) { Write-StartupPanel }
                        Start-WaitIndicator $(if ($verifying) { "browser-verify" } else { "browser-download" })
                    }
                    if ($line -in @("__JIEJIAN_SERVE_STATUS__:still-starting", "__JIEJIAN_SERVE_STATUS__:ready-browser-opened", "__JIEJIAN_SERVE_STATUS__:ready-browser-open-failed", "__JIEJIAN_SERVE_STATUS__:startup-failed")) {
                        if ($line.EndsWith("still-starting")) {
                            Set-StartupStatus "正在启动" "界鉴启动时间较长，仍在准备，请稍候" "尚未收到服务就绪确认；可以继续等待或退出。"
                            Start-WaitIndicator "serve"
                        } elseif (-not $script:ServeReadyObserved -and $line.EndsWith("ready-browser-opened")) {
                            $script:ServeReadyObserved = $true
                            Stop-WaitIndicator
                            Set-StartupStatus "已就绪" "界鉴网页已打开" ("服务运行中 · http://127.0.0.1:{0}/ · 此窗口管理后台服务。" -f $Port)
                        } elseif (-not $script:ServeReadyObserved -and $line.EndsWith("ready-browser-open-failed")) {
                            $script:ServeReadyObserved = $true
                            Stop-WaitIndicator
                            Set-StartupStatus "已就绪" "界鉴已经启动，但未能自动打开网页" ("请在浏览器访问 http://127.0.0.1:{0}/" -f $Port)
                        } elseif ($line.EndsWith("startup-failed")) {
                            $script:ServeStartupFailed = $true
                            Stop-WaitIndicator
                            Set-StartupStatus "启动未完成" "界鉴服务在就绪前停止" "请查看下方失败原因与恢复办法。"
                        }
                    }
                    if ($Stage -eq "serve" -and $script:ServeReadyObserved) {
                        switch ($line) {
                            "__JIEJIAN_GUI_STATUS__:controls-ready" {
                                $script:StartupPanelKeys = "Ctrl+C / Q 退出    G 重新打开界面"
                                if ($script:StartupPanelActive) { Write-StartupPanel }
                                else { Write-Host "[G] 重新打开 GUI    [Ctrl+C / Q] 退出界鉴" -ForegroundColor Cyan }
                            }
                            "__JIEJIAN_GUI_STATUS__:stopping" {
                                $script:StartupPanelKeys = ""
                                Set-StartupStatus "正在退出" "正在关闭界鉴服务" "等待当前任务与所属进程完成清理。"
                            }
                            "__JIEJIAN_GUI_STATUS__:opened" { Set-StartupStatus "已就绪" "已发送界面打开请求" ("服务运行中 · http://127.0.0.1:{0}/" -f $Port) }
                            "__JIEJIAN_GUI_STATUS__:open-failed" { Set-StartupStatus "已就绪" "未能打开界面" ("可重试，或访问 http://127.0.0.1:{0}/" -f $Port) }
                            "__JIEJIAN_GUI_STATUS__:input-unavailable" {
                                $script:StartupPanelKeys = "Ctrl+C 退出"
                                Set-StartupStatus "已就绪" "终端快捷键不可用" ("请访问 http://127.0.0.1:{0}/" -f $Port)
                            }
                        }
                    }
                } |
                Out-Null
        }
        $code = $LASTEXITCODE
        if ($Stage -eq "serve" -and $script:ServeStartupFailed -and $code -eq 0) {
            $code = 50
        }
    } finally {
        if ($waitIndicatorStarted) { Stop-WaitIndicator }
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($code -ne 0) {
        if ($Stage -eq "source-prepare" -and $null -ne $prepareFailure -and $prepareFailure.stage -match '^[a-z-]{1,64}$') {
            Fail-Start $FailureCode ([string]$prepareFailure.stage) ([string]$prepareFailure.message) ([string]$prepareFailure.recovery)
        }
        if ([string]::IsNullOrWhiteSpace($Recovery)) { $Recovery = Get-RecoveryCommand }
        Fail-Start $FailureCode $Stage "外部命令返回 $code" $Recovery
    }
}
