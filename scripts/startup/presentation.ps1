# 启动展示：统一进度、等待动画、日志和顶层失败文本。
# 展示层不得吞掉实际失败码，也不把详细命令输出直接暴露给普通用户。
function Write-Startup([string]$Message) {
    if (-not (Test-Path -LiteralPath $script:LogDir -PathType Container)) {
        New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null
    }
    [IO.File]::AppendAllText($script:LogPath, $Message + [Environment]::NewLine, $script:Utf8Encoding)
}

function Write-Banner {
    Write-Host ""
    if ($script:DisplayUnicode) {
        @(
            "   ██╗██╗███████╗     ██╗██╗ █████╗ ███╗   ██╗",
            "   ██║██║██╔════╝     ██║██║██╔══██╗████╗  ██║",
            "   ██║██║█████╗       ██║██║███████║██╔██╗ ██║",
            "██ ██║██║██╔══╝    ██ ██║██║██╔══██║██║╚██╗██║",
            "╚███╔╝██║███████╗  ╚███╔╝██║██║  ██║██║ ╚████║",
            " ╚══╝ ╚═╝╚══════╝   ╚══╝ ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝"
        ) | ForEach-Object { Write-Host $_ -ForegroundColor Cyan }
        Write-Host ""
        Write-Host "         界鉴 · 安全意图一致性验证" -ForegroundColor Gray
    } else {
        Write-Host "JIEJIAN" -ForegroundColor Cyan
        Write-Host "界鉴 - 安全意图一致性验证" -ForegroundColor Gray
    }
}

function Select-StartupMode {
    # 返回稳定内部模式名，避免展示文案成为脚本路由契约。

    $items = @(
        [pscustomobject]@{ mode = "Gui"; label = "图形界面" },
        [pscustomobject]@{ mode = "Cli"; label = "命令行" },
        [pscustomobject]@{ mode = "Prepare"; label = "仅完成环境准备" }
    )
    $selected = 0
    Write-Host ""
    Write-Host "界鉴已经准备完成" -ForegroundColor Cyan
    Write-Host ""
    $menuTop = [Console]::CursorTop
    foreach ($item in $items) { Write-Host ("  {0,-24}" -f $item.label) }
    while ($true) {
        [Console]::SetCursorPosition(0, $menuTop)
        for ($index = 0; $index -lt $items.Count; $index += 1) {
            $marker = if ($index -eq $selected) { ">" } else { " " }
            $color = if ($index -eq $selected) { "Cyan" } else { "Gray" }
            Write-Host ("{0} {1,-24}" -f $marker, $items[$index].label) -ForegroundColor $color
        }
        $key = [Console]::ReadKey($true).Key
        switch ($key) {
            "UpArrow" { $selected = ($selected - 1 + $items.Count) % $items.Count }
            "DownArrow" { $selected = ($selected + 1) % $items.Count }
            "Enter" { return $items[$selected].mode }
        }
    }
}

function Write-CliWelcome {
    # 子 shell 只继承本轮环境，欢迎信息不暗示用户配置已被修改。

    Write-Host ""
    Write-Host "界鉴命令行已经准备完成" -ForegroundColor Cyan
    Write-Host ("VarDir  {0}" -f $script:VarDir) -ForegroundColor Gray
    Write-Host ""
    Write-Host "常用命令" -ForegroundColor Gray
    Write-Host "  jiejian doctor" -ForegroundColor DarkGray
    Write-Host "  jiejian project --help" -ForegroundColor DarkGray
    Write-Host "  jiejian recording --help" -ForegroundColor DarkGray
    Write-Host "  jiejian run --help" -ForegroundColor DarkGray
    Write-Host "  exit" -ForegroundColor DarkGray
    Write-Host ""
}

function Wait-StartupFailureInput {
    # start.cmd 双击入口需要保留错误；自动化和直接脚本调用仍立即返回退出码。
    if (-not $script:WaitOnFailure -or [Console]::IsInputRedirected -or [Console]::IsOutputRedirected) {
        return
    }
    Write-Host "按 Enter 关闭窗口" -ForegroundColor DarkGray
    while ([Console]::ReadKey($true).Key -ne "Enter") { }
}

function Start-DisplayStage([int]$Index, [string]$Name) {
    $script:DisplayStageName = $Name
    $script:DisplayStageIndex = $Index
    $script:DisplayStageTimer = [Diagnostics.Stopwatch]::StartNew()
    $script:DisplayStageSkipped = $true
    if ($Index -gt 1) { Write-Host "" }
    Write-Host ("[{0}/6] {1}" -f $Index, $Name) -ForegroundColor Blue
}

function Complete-DisplayStage([string]$Status = "") {
    if ($null -eq $script:DisplayStageTimer) { return }
    $script:DisplayStageTimer.Stop()
    if ($Status -eq "失败") {
        Write-DisplayResult "当前任务" "失败" $true
    } else {
        Write-Host ("      · 耗时 {0:N0} ms" -f $script:DisplayStageTimer.Elapsed.TotalMilliseconds) -ForegroundColor DarkGray
    }
    $script:DisplayStageName = $null
    $script:DisplayStageTimer = $null
    $script:DisplayStageSkipped = $false
}

function Write-DisplaySubtask([string]$Message, [bool]$Weak = $false) {
    if ($null -eq $script:DisplayStageTimer) { return }
    $branch = if ($script:DisplayUnicode) {
        if ($Weak) { "         └─" } else { "      ├─" }
    } else {
        if ($Weak) { "         `--" } else { "      |--" }
    }
    $color = if ($Weak) { "DarkGray" } else { "Gray" }
    Write-Host ("{0} {1}" -f $branch, $Message) -ForegroundColor $color
}

function Get-DisplayCellWidth([string]$Text) {
    $width = 0
    if ($null -eq $Text) { return $width }
    foreach ($character in $Text.ToCharArray()) {
        $code = [int][char]$character
        $wide = (
            ($code -ge 0x1100 -and $code -le 0x115F) -or
            ($code -ge 0x2329 -and $code -le 0x232A) -or
            ($code -ge 0x2E80 -and $code -le 0xA4CF) -or
            ($code -ge 0xAC00 -and $code -le 0xD7A3) -or
            ($code -ge 0xF900 -and $code -le 0xFAFF) -or
            ($code -ge 0xFE10 -and $code -le 0xFE6F) -or
            ($code -ge 0xFF00 -and $code -le 0xFF60) -or
            ($code -ge 0xFFE0 -and $code -le 0xFFE6)
        )
        $width += if ($wide) { 2 } else { 1 }
    }
    return $width
}

function Format-DisplayNameCell([string]$Name, [int]$TargetWidth = 32) {
    $padding = [Math]::Max(1, $TargetWidth - (Get-DisplayCellWidth $Name))
    return $Name + (" " * $padding)
}

function Write-DisplayResult(
    [string]$Name,
    [string]$Status = "完成",
    [bool]$Last = $false,
    [string]$Detail = ""
) {
    if ($null -eq $script:DisplayStageTimer) { return }
    $script:DisplayStageSkipped = $false
    $branch = if ($script:DisplayUnicode) { if ($Last) { "      └─" } else { "      ├─" } } else { if ($Last) { "      `--" } else { "      |--" } }
    $marker = switch ($Status) {
        "完成" { if ($script:DisplayUnicode) { "✓" } else { "OK" } }
        "失败" { if ($script:DisplayUnicode) { "×" } else { "FAILED" } }
        "跳过" { "SKIP" }
        default { $Status }
    }
    $color = if ($Status -eq "失败") { "Red" } elseif ($Status -eq "跳过") { "DarkCyan" } else { "Cyan" }
    $nameCell = Format-DisplayNameCell $Name
    Write-Host ("{0} {1} {2}" -f $branch, $nameCell, $marker) -ForegroundColor $color
    if (-not [string]::IsNullOrWhiteSpace($Detail)) {
        $detailBranch = if ($script:DisplayUnicode) { if ($Last) { "         └─" } else { "      │  └─" } } else { if ($Last) { "         `--" } else { "      |  `--" } }
        Write-Host ("{0} {1}" -f $detailBranch, $Detail) -ForegroundColor DarkGray
    }
}

function Get-WaitIndicatorLabel([string]$Stage) {
    switch ($Stage) {
        { $_ -in @("conda", "uv", "lock", "python-dependencies", "python") } { return "正在准备 Python" }
        "playwright" { return "正在准备浏览器" }
        { $_ -in @("doctor", "migration") } { return "正在准备数据" }
        { $_ -in @("frontend-install", "frontend-build", "frontend") } { return "正在准备界面" }
        "serve" { return "正在启动界面" }
        default { return "正在处理" }
    }
}

function Start-WaitIndicator([string]$Stage) {
    if (-not $script:DisplayInteractive -or [Console]::IsOutputRedirected) { return }
    # 动画是可降级的展示子进程，启动失败不得改变产品准备或服务退出语义。
    try {
        Stop-WaitIndicator
        $shell = (Get-Process -Id $PID -ErrorAction Stop).Path
        $quotedScript = '"' + $PSCommandPath.Replace('"', '""') + '"'
        $arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File $quotedScript -DisplaySpinnerProcess -DisplaySpinnerStage $Stage"
        if (-not $script:DisplayUnicode) { $arguments += " -DisplaySpinnerAscii" }
        $script:WaitIndicatorProcess = Start-Process -FilePath $shell -ArgumentList $arguments -NoNewWindow -PassThru -ErrorAction Stop
    } catch {
        $script:WaitIndicatorProcess = $null
        try { [Console]::Write(("`r{0}..." -f (Get-WaitIndicatorLabel $Stage))) } catch { }
    }
}

function Stop-WaitIndicator {
    if ($null -ne $script:WaitIndicatorProcess) {
        # 主流程任何出口都回收动画进程，避免控制台关闭后残留后台 PowerShell。
        try {
            if (-not $script:WaitIndicatorProcess.HasExited) {
                Stop-Process -Id $script:WaitIndicatorProcess.Id -Force -ErrorAction SilentlyContinue
                $null = $script:WaitIndicatorProcess.WaitForExit(500)
            }
            $script:WaitIndicatorProcess.Dispose()
        } catch { }
        $script:WaitIndicatorProcess = $null
    }
    if ($script:DisplayInteractive -and -not [Console]::IsOutputRedirected) {
        try {
            $width = [Math]::Max(40, [Math]::Min(160, $Host.UI.RawUI.WindowSize.Width - 1))
            [Console]::Write(("`r" + (" " * $width) + "`r"))
        } catch { try { [Console]::Write(("`r" + (" " * 100) + "`r")) } catch { } }
    }
}

function Invoke-WaitIndicatorProcess([string]$Stage, [bool]$Ascii) {
    $frames = if ($Ascii) { @("|", "/", "-", "\") } else { @("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏") }
    $label = Get-WaitIndicatorLabel $Stage
    $index = 0
    while ($true) {
        [Console]::Write(("`r{0} {1}" -f $frames[$index % $frames.Count], $label))
        $index += 1
        Start-Sleep -Milliseconds 90
    }
}

function Get-RecoveryCommand {
    return "powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -ForcePrepare -PrepareOnly -VarDir `"$script:VarDir`""
}
