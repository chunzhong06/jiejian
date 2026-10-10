# 启动展示：统一进度、等待动画、日志和顶层失败文本。
# 展示层不得吞掉实际失败码，也不把详细命令输出直接暴露给普通用户。
. (Join-Path $PSScriptRoot "panel.ps1")
function Write-Startup([string]$Message) {
    if (-not (Test-Path -LiteralPath $script:LogDir -PathType Container)) {
        New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null
    }
    if (-not $script:StartupLogInitialized) {
        # 只登记本次创建的日志；历史保留由同一维护服务按归属记录处理。
        $relative = "logs/startup/" + [IO.Path]::GetFileName($script:LogPath)
        $registry = Join-Path $script:VarDir "runtime\generated-files"
        New-Item -ItemType Directory -Path $registry -Force | Out-Null
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $key = ([BitConverter]::ToString($sha.ComputeHash($script:Utf8Encoding.GetBytes($relative))) -replace '-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
        $record = [ordered]@{ schema_version="1"; kind="generated-file"; producer="startup-log"; path=$relative }
        [IO.File]::WriteAllText((Join-Path $registry ($key + ".json")), ($record | ConvertTo-Json -Compress), $script:Utf8Encoding)
        $script:StartupLogInitialized = $true
    }
    [IO.File]::AppendAllText($script:LogPath, $Message + [Environment]::NewLine, $script:Utf8Encoding)
}

function Write-Banner {
    $script:StartupPanelClock = [Diagnostics.Stopwatch]::StartNew()
    if ($script:ProjectRoot) {
        $versionFile = Join-Path $script:ProjectRoot "product\backend\__init__.py"
        if (Test-Path -LiteralPath $versionFile) {
            $version = [regex]::Match([IO.File]::ReadAllText($versionFile), '__version__\s*=\s*"([0-9.]+)"')
            if ($version.Success) { $script:StartupPanelVersion = $version.Groups[1].Value }
        }
    }
    # GUI / Prepare 可占用固定区域；交互菜单和 CLI 保留正常终端输出，不抢它们的光标。
    $script:StartupPanelActive = $script:DisplayInteractive -and $script:DisplayUnicode -and
        $script:FinalMode -notin @("Cli", "Interactive")
    if ($script:StartupPanelActive) { Write-StartupPanel }
    else {
        Write-Host ""
        Write-Host ("界鉴  JIEJIAN  {0}" -f $script:StartupPanelVersion) -ForegroundColor Blue
        Write-Host "让权限要求与实际行为对应起来" -ForegroundColor Gray
    }
}

function Read-StartupMenu([string]$Title, [object[]]$Items) {
    # 标题、选项和操作提示分区绘制；方向键只覆盖选项行。
    $selected = 0
    Write-Host ""
    Write-Host $Title -ForegroundColor Blue
    Write-Host ""
    try {
        $menuTop = [Console]::CursorTop
        for ($index = 0; $index -lt $Items.Count; $index += 1) {
            $marker = if ($index -eq $selected) { ">" } else { " " }
            $color = if ($index -eq $selected) { "Blue" } else { "Gray" }
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
                    $color = if ($index -eq $selected) { "Blue" } else { "Gray" }
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
        [pscustomobject]@{ value = "Status"; label = "工作台模式（推荐）" },
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
    Write-Host "界鉴命令行已经准备完成" -ForegroundColor Blue
    Write-Host ("VarDir  {0}" -f $script:VarDir) -ForegroundColor Gray
    Write-Host ""
    Write-Host "第一次使用？" -ForegroundColor Gray
    Write-Host "  jiejian status" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "常用命令" -ForegroundColor Gray
    Write-Host "  jiejian system doctor" -ForegroundColor DarkGray
    Write-Host "  jiejian check --help" -ForegroundColor DarkGray
    Write-Host "  jiejian result --help" -ForegroundColor DarkGray
    Write-Host "  jiejian --help" -ForegroundColor DarkGray
    Write-Host ""
}

function Start-DisplayStage([int]$Index, [string]$Name) {
    Stop-WaitIndicator
    $script:DisplayStageName = $Name
    $script:DisplayStageIndex = $Index
    $script:DisplayStageTimer = [Diagnostics.Stopwatch]::StartNew()
    $script:DisplayStageSkipped = $true
    $script:StartupPanelStates[$Index] = "running"
    $script:StartupPanelTitle = $Name
    $script:StartupPanelDetail = switch ($Index) {
        1 { "检查本机运行工具，已有环境将直接复用。" }
        2 { "核对应用运行所需的依赖。" }
        3 { "准备界鉴专用浏览器。" }
        4 { "核对界面资源，只有发生变化时才重新构建。" }
        5 { "检查当前运行目录中的数据。" }
        6 { "等待本地服务就绪，随后自动打开界面。" }
    }
    if ($script:StartupPanelActive) { Write-StartupPanel; return }
    if ($Index -gt 1) { Write-Host "" }
    Write-Host ("[{0}/6] {1}" -f $Index, $Name) -ForegroundColor Blue
}

function Complete-DisplayStage([string]$Status = "") {
    Stop-WaitIndicator
    if ($null -eq $script:DisplayStageTimer) { return }
    $script:DisplayStageTimer.Stop()
    if ($script:StartupPanelStatus -notin @("已停止", "准备完成")) {
        $script:StartupPanelStates[$script:DisplayStageIndex] = if ($Status -eq "失败") { "failed" } else { "done" }
    }
    if ($script:StartupPanelActive) {
        # 服务驻留到退出的时间不能算作启动耗时；ready 事件已单独冻结时钟。
        Write-StartupPanel
        $script:DisplayStageName = $null
        $script:DisplayStageTimer = $null
        return
    }
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
    Stop-WaitIndicator
    if ($null -eq $script:DisplayStageTimer) { return }
    $script:DisplayStageSkipped = $false
    if ($script:StartupPanelActive) {
        if ($Status -eq "失败") { $script:StartupPanelStates[$script:DisplayStageIndex] = "failed" }
        # 详细路径与工具信息继续进日志，面板仅保留当前任务的解释。
        if ($Detail) { Write-Startup ("{0}: {1} · {2}" -f $Name, $Status, $Detail) }
        Write-StartupPanel
        return
    }
    $branch = if ($script:DisplayUnicode) { if ($Last) { "      └─" } else { "      ├─" } } else { if ($Last) { "      `--" } else { "      |--" } }
    $marker = switch ($Status) {
        "完成" { if ($script:DisplayUnicode) { "✓" } else { "OK" } }
        "失败" { if ($script:DisplayUnicode) { "×" } else { "FAILED" } }
        "跳过" { "SKIP" }
        default { $Status }
    }
    $color = if ($Status -eq "失败") { "Red" } elseif ($Status -eq "跳过") { "Gray" } else { "Blue" }
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
        "browser-download" { return "正在下载并安装浏览器" }
        "browser-verify" { return "正在核验浏览器安装" }
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
        # 面板中的各步骤共用启动起点；动画子进程重启不能重置总耗时。
        if ($script:StartupPanelActive -and $null -ne $script:StartupPanelClock) {
            $startedAt -= [long][Math]::Floor($script:StartupPanelClock.Elapsed.TotalMilliseconds)
        }
        $eventName = "Local\JiejianWait-{0}-{1}" -f $PID, [guid]::NewGuid().ToString("N")
        $createdNew = $false
        $script:WaitIndicatorStopEvent = [Threading.EventWaitHandle]::new(
            $false,
            [Threading.EventResetMode]::ManualReset,
            $eventName,
            [ref]$createdNew
        )
        if (-not $createdNew) { throw "等待动画停止事件名称发生冲突" }
        $arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File $quotedScript -DisplaySpinnerProcess -DisplaySpinnerStage $Stage -DisplaySpinnerStartedAt $startedAt -DisplaySpinnerStopEvent $eventName"
        if ($script:StartupPanelActive) { $arguments += " -DisplaySpinnerPanel" }
        if (-not $script:DisplayUnicode) { $arguments += " -DisplaySpinnerAscii" }
        $script:WaitIndicatorProcess = Start-Process -FilePath $shell -ArgumentList $arguments -NoNewWindow -PassThru -ErrorAction Stop
    } catch {
        if ($null -ne $script:WaitIndicatorStopEvent) {
            try { $script:WaitIndicatorStopEvent.Dispose() } catch { }
        }
        $script:WaitIndicatorStopEvent = $null
        $script:WaitIndicatorProcess = $null
        $script:WaitIndicatorFallbackActive = $true
        try { [Console]::Write(("`r{0}..." -f (Get-WaitIndicatorLabel $Stage))) } catch { }
    }
}

function Clear-WaitIndicatorLine {
    if ($script:DisplayInteractive -and -not [Console]::IsOutputRedirected) {
        try {
            $width = [Math]::Max(40, [Math]::Min(160, $Host.UI.RawUI.WindowSize.Width - 1))
            [Console]::Write(("`r" + (" " * $width) + "`r"))
        } catch { try { [Console]::Write(("`r" + (" " * 100) + "`r")) } catch { } }
    }
}

function Stop-WaitIndicator {
    $process = $script:WaitIndicatorProcess
    $stopEvent = $script:WaitIndicatorStopEvent
    $hadVisibleOutput = $null -ne $process -or $script:WaitIndicatorFallbackActive
    $exited = $null -eq $process
    if ($null -ne $process) {
        # 先协商停止；只有子进程在期限内未退出时才强杀，且清行前必须确认退出。
        try {
            if (-not $process.HasExited) {
                if ($null -ne $stopEvent) { try { $null = $stopEvent.Set() } catch { } }
                $exited = $process.WaitForExit(2000)
                if (-not $exited) {
                    Stop-Process -Id $process.Id -Force -ErrorAction Stop
                    $process.WaitForExit()
                    $exited = $process.HasExited
                }
            } else {
                $process.WaitForExit()
                $exited = $true
            }
        } catch {
            $exited = $process.HasExited
        }
    }
    if ($exited -and $hadVisibleOutput) { Clear-WaitIndicatorLine }
    if ($null -ne $process) { try { $process.Dispose() } catch { } }
    if ($null -ne $stopEvent) { try { $stopEvent.Dispose() } catch { } }
    $script:WaitIndicatorProcess = $null
    $script:WaitIndicatorStopEvent = $null
    $script:WaitIndicatorFallbackActive = $false
}

function Invoke-WaitIndicatorProcess([string]$Stage, [bool]$Ascii, [long]$StartedAt = 0, [string]$StopEventName = "", [bool]$Panel = $false) {
    if ([string]::IsNullOrWhiteSpace($StopEventName)) { return }
    try { $stopEvent = [Threading.EventWaitHandle]::OpenExisting($StopEventName) }
    catch { return }
    try {
        $frames = if ($Ascii) { @("|", "/", "-", "\") } else { @("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏") }
        $label = Get-WaitIndicatorLabel $Stage
        $index = 0
        # 快速探针在首帧出现前结束；收到停止信号后不再写任何一帧。
        if ($stopEvent.WaitOne(130)) { return }
        while ($true) {
            $elapsed = if ($StartedAt -gt 0) { [Math]::Max(0, [int][Math]::Floor(([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - $StartedAt) / 1000)) } else { 0 }
            $text = "{0} {1} {2}s" -f $frames[$index % $frames.Count], $label, $elapsed
            if ($Panel) {
                $text = "{0} 启动已用 {1} 秒 · {2}" -f $frames[$index % $frames.Count], $elapsed, $label
                $terminalWidth = [Console]::WindowWidth
                $width = [Math]::Max(1, [Math]::Min(88, $terminalWidth - 6))
                $margin = " " * [Math]::Max(0, [int][Math]::Floor(($terminalWidth - $width) / 2))
                $escape = [char]27
                $color = if (-not $script:DisplayTrueColor) { "37" } else { "38;2;" + $script:StartupPanelPalette.Muted }
                [Console]::Write(("`r{0}[2K{1}{0}[{2}m{3}{0}[0m" -f $escape, $margin, $color, (Format-StartupLine $text $width "Ctrl+C 退出")))
            } else { [Console]::Write(("`r" + $text)) }
            $index += 1
            if ($stopEvent.WaitOne(120)) { break }
        }
    } finally {
        $stopEvent.Dispose()
    }
}

function Get-RecoveryCommand {
    return ".\start.cmd -Mode Prepare -VarDir `"$script:VarDir`""
}
