# 启动展示：统一进度、等待动画、日志和顶层失败文本。
# 展示层不得吞掉实际失败码，也不把详细命令输出直接暴露给普通用户。
function Write-Startup([string]$Message) {
    if (-not (Test-Path -LiteralPath $script:LogDir -PathType Container)) {
        New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null
    }
    if (-not $script:StartupLogInitialized) {
        # 新日志写入前只保留最近十九份历史，连同本轮日志最多二十份。
        @(Get-ChildItem -LiteralPath $script:LogDir -Filter "*.log" -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc, Name -Descending |
            Select-Object -Skip 19) | ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
            }
        $script:StartupLogInitialized = $true
    }
    [IO.File]::AppendAllText($script:LogPath, $Message + [Environment]::NewLine, $script:Utf8Encoding)
}

function Write-Banner {
    Write-Host ""
    if ($script:DisplayUnicode) {
        $lines = @(
            "     ██╗██╗███████╗       ██╗██╗ █████╗ ███╗   ██╗",
            "     ██║██║██╔════╝       ██║██║██╔══██╗████╗  ██║",
            "     ██║██║█████╗         ██║██║███████║██╔██╗ ██║",
            "██   ██║██║██╔══╝    ██   ██║██║██╔══██║██║╚██╗██║",
            "╚█████╔╝██║███████╗  ╚█████╔╝██║██║  ██║██║ ╚████║",
            " ╚════╝ ╚═╝╚══════╝   ╚════╝ ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝"
        )
        $colors = @(
            @(0, 102, 153),
            @(0, 126, 174),
            @(0, 151, 194),
            @(32, 174, 211),
            @(82, 197, 226),
            @(145, 222, 239)
        )
        for ($index = 0; $index -lt $lines.Count; $index += 1) {
            if ($script:DisplayTrueColor) {
                $escape = [char]27
                $rgb = $colors[$index]
                Write-Host ("{0}[38;2;{1};{2};{3}m{4}{0}[0m" -f $escape, $rgb[0], $rgb[1], $rgb[2], $lines[$index])
            } else {
                Write-Host $lines[$index] -ForegroundColor Cyan
            }
        }
        Write-Host ""
        Write-Host "         界鉴 · 安全意图一致性验证" -ForegroundColor Gray
    } else {
        Write-Host "JIEJIAN" -ForegroundColor Cyan
        Write-Host "界鉴 - 安全意图一致性验证" -ForegroundColor Gray
    }
}

function Read-StartupMenu([string]$Title, [object[]]$Items) {
    # 标题、选项和操作提示分区绘制；方向键只覆盖选项行。
    $selected = 0
    Write-Host ""
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ""
    try {
        $menuTop = [Console]::CursorTop
        for ($index = 0; $index -lt $Items.Count; $index += 1) {
            $marker = if ($index -eq $selected) { ">" } else { " " }
            $color = if ($index -eq $selected) { "Cyan" } else { "Gray" }
            $line = ("{0} {1}" -f $marker, $Items[$index].label)
            Write-Host $line -ForegroundColor $color
        }
        Write-Host ""
        if ($script:DisplayUnicode) {
            Write-Host "↑ ↓ 选择    Enter 确认" -ForegroundColor DarkGray
        } else {
            Write-Host "方向键选择    Enter 确认" -ForegroundColor DarkGray
        }
        $afterFooter = [Console]::CursorTop
        while ($true) {
            $key = [Console]::ReadKey($true).Key
            switch ($key) {
                "UpArrow" { $selected = ($selected - 1 + $Items.Count) % $Items.Count }
                "DownArrow" { $selected = ($selected + 1) % $Items.Count }
                "Enter" {
                    if (-not $script:DisplayTrueColor) {
                        [Console]::SetCursorPosition(0, $afterFooter)
                    }
                    return $Items[$selected].value
                }
            }
            if ($script:DisplayTrueColor) {
                # Windows Terminal 通过同一 VT 输出流保存和恢复光标，避免 RawUI 坐标与 ConPTY 状态脱节后追加菜单。
                $escape = [char]27
                [Console]::Write(("{0}[s{0}[{1}A{0}[1G" -f $escape, ($Items.Count + 2)))
                for ($index = 0; $index -lt $Items.Count; $index += 1) {
                    $marker = if ($index -eq $selected) { ">" } else { " " }
                    $colorCode = if ($index -eq $selected) { 96 } else { 37 }
                    $line = ("{0} {1}" -f $marker, $Items[$index].label)
                    [Console]::Write(("{0}[2K{0}[{1}m{2}{0}[0m" -f $escape, $colorCode, $line))
                    if ($index -lt ($Items.Count - 1)) { [Console]::Write("`r`n") }
                }
                [Console]::Write(("{0}[u" -f $escape))
            } else {
                [Console]::SetCursorPosition(0, $menuTop)
                for ($index = 0; $index -lt $Items.Count; $index += 1) {
                    $marker = if ($index -eq $selected) { ">" } else { " " }
                    $color = if ($index -eq $selected) { "Cyan" } else { "Gray" }
                    Write-Host ("{0} {1}" -f $marker, $Items[$index].label) -ForegroundColor $color
                }
                [Console]::SetCursorPosition(0, $afterFooter)
            }
        }
    } catch {
        # RawUI 不可靠时只输出一次编号列表；无效输入只重问编号。
        Write-Host "当前终端改用编号选择，输入编号后按 Enter 确认。" -ForegroundColor DarkGray
        for ($index = 0; $index -lt $Items.Count; $index += 1) {
            Write-Host ("{0}. {1}" -f ($index + 1), $Items[$index].label) -ForegroundColor Gray
        }
        while ($true) {
            $answer = Read-Host ("请输入 1-{0}" -f $Items.Count)
            $number = 0
            if ([int]::TryParse($answer, [ref]$number) -and $number -ge 1 -and $number -le $Items.Count) {
                return $Items[$number - 1].value
            }
        }
    }
}

function Select-StartupMode {
    # 展示文案与内部路由值分离；返回可回到第一层，不增加新的公共 Mode。
    $startupItems = @(
        [pscustomobject]@{ value = "Gui"; label = "图形界面" },
        [pscustomobject]@{ value = "Cli"; label = "命令行" },
        [pscustomobject]@{ value = "Prepare"; label = "仅完成环境准备" }
    )
    $cliItems = @(
        [pscustomobject]@{ value = "Guide"; label = "引导模式（推荐）" },
        [pscustomobject]@{ value = "Shell"; label = "普通命令行" },
        [pscustomobject]@{ value = "Back"; label = "返回" }
    )
    while ($true) {
        $mode = Read-StartupMenu "界鉴已经准备完成" $startupItems
        if ($mode -ne "Cli") { return $mode }
        $cliMode = Read-StartupMenu "请选择命令行方式" $cliItems
        if ($cliMode -eq "Back") { continue }
        $script:CliEntryMode = $cliMode
        return "Cli"
    }
}

function Write-CliWelcome {
    # 子 shell 只继承本轮环境，欢迎信息不暗示用户配置已被修改。

    Write-Host ""
    Write-Host "界鉴命令行已经准备完成" -ForegroundColor Cyan
    Write-Host ("VarDir  {0}" -f $script:VarDir) -ForegroundColor Gray
    Write-Host ""
    Write-Host "第一次使用？" -ForegroundColor Gray
    Write-Host "  jiejian guide" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "常用命令" -ForegroundColor Gray
    Write-Host "  jiejian doctor" -ForegroundColor DarkGray
    Write-Host "  jiejian run --help" -ForegroundColor DarkGray
    Write-Host "  jiejian report --help" -ForegroundColor DarkGray
    Write-Host "  jiejian --help" -ForegroundColor DarkGray
    Write-Host ""
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
        { $_ -in @("node", "node-search") } { return "正在查找 Node.js" }
        { $_ -in @("pnpm", "pnpm-check") } { return "正在检查 pnpm" }
        { $_ -in @("conda", "uv", "python-search") } { return "正在查找 Python 环境" }
        { $_ -in @("python", "python-version", "python-verify") } { return "正在验证 Python 环境" }
        { $_ -in @("lock", "uv-sync", "python-dependencies") } { return "正在准备 Python 依赖" }
        "source-prepare" { return "正在准备工具链" }
        "toolchain" { return "正在准备工具链" }
        "python" { return "正在同步 Python 依赖" }
        "browser" { return "正在准备浏览器" }
        "chromium-check" { return "正在检查 Chromium" }
        { $_ -in @("playwright", "chromium-prepare") } { return "正在准备 Chromium" }
        { $_ -in @("doctor", "database-check") } { return "正在检查本地数据" }
        { $_ -in @("migration", "database-upgrade") } { return "正在升级本地数据" }
        { $_ -in @("frontend-install", "frontend-dependencies") } { return "正在准备界面依赖" }
        { $_ -in @("frontend-build", "frontend") } { return "正在构建界面" }
        "database" { return "正在检查本地数据" }
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
        $spinnerScript = Join-Path $script:ProjectRoot "scripts\start.ps1"
        $quotedScript = '"' + $spinnerScript.Replace('"', '""') + '"'
        $startedAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        $arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File $quotedScript -DisplaySpinnerProcess -DisplaySpinnerStage $Stage -DisplaySpinnerStartedAt $startedAt"
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

function Invoke-WaitIndicatorProcess([string]$Stage, [bool]$Ascii, [long]$StartedAt = 0) {
    $frames = if ($Ascii) { @("|", "/", "-", "\") } else { @("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏") }
    $label = Get-WaitIndicatorLabel $Stage
    $index = 0
    # 快速探针在首帧出现前结束，避免终端闪烁。
    Start-Sleep -Milliseconds 130
    while ($true) {
        $elapsed = if ($StartedAt -gt 0) { [Math]::Max(0, [int][Math]::Floor(([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - $StartedAt) / 1000)) } else { 0 }
        [Console]::Write(("`r{0} {1} {2}s" -f $frames[$index % $frames.Count], $label, $elapsed))
        $index += 1
        Start-Sleep -Milliseconds 90
    }
}

function Get-RecoveryCommand {
    return ".\start.cmd -Mode Prepare -ForcePrepare -VarDir `"$script:VarDir`""
}
