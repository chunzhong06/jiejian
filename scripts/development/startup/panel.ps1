# 启动面板只投影现有阶段与就绪事实；光标由主进程和已协商停止的等待进程轮流持有。
$script:StartupPanelActive = $false
$script:StartupPanelRows = 0
$script:StartupPanelWidth = 0
$script:StartupPanelStates = @{}
$script:StartupPanelStatus = "正在启动"
$script:StartupPanelTitle = "正在准备界鉴"
$script:StartupPanelDetail = "准备完成后将自动打开应用界面。"
$script:StartupPanelKeys = "Ctrl+C 退出"
$script:StartupPanelClock = $null
$script:StartupPanelReadySeconds = $null
$script:StartupPanelVersion = ""
$script:StartupPanelArtRows = 0
$startupBrand = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../../../product/launcher/windows/brand.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$script:StartupPanelArt = @($startupBrand.art)
# 与网页的蓝紫强调色同源表达；文字按层级降亮度，错误仍保留语义色。
$script:StartupPanelPalette = @{ Accent = "186;196;249"; Muted = "166;173;192"; Danger = "237;163;169" }
$script:StartupPanelArtColors = @($startupBrand.colors | ForEach-Object { $_ -join ';' })
$script:StartupPanelLabels = @("运行工具", "Python 环境", "浏览器", "应用界面", "本地数据", "界鉴服务")

function Format-StartupLine([string]$Text, [int]$Width, [string]$Right = "") {
    # 不让诊断文本中的控制字符移动光标；长内容完整保留在日志，面板按显示单元截断。
    $Text = [regex]::Replace($Text, '\x1b\[[0-9;?]*[ -/]*[@-~]|[\x00-\x1f\x7f]', ' ')
    $available = [Math]::Max(0, $Width - (Get-DisplayCellWidth $Right) - $(if ($Right) { 2 } else { 0 }))
    if ((Get-DisplayCellWidth $Text) -gt $available) {
        $clipped = ""
        foreach ($character in $Text.ToCharArray()) {
            if ((Get-DisplayCellWidth ($clipped + $character)) -gt ($available - 3)) { break }
            $clipped += $character
        }
        $Text = $clipped + $(if ($available -ge 3) { "..." } else { "" })
    }
    if (-not $Right) { return $Text }
    return $Text + (" " * [Math]::Max(2, $Width - (Get-DisplayCellWidth $Text) - (Get-DisplayCellWidth $Right))) + $Right
}

function Get-StartupPanelLines([int]$Width, [int]$Height = 0) {
    # 艺术字按整组显示宽度居中；小窗口保留完整状态面板，避免标题挤掉错误和退出入口。
    $script:StartupPanelArtRows = 0
    $artWidth = ($script:StartupPanelArt | ForEach-Object { Get-DisplayCellWidth $_ } | Measure-Object -Maximum).Maximum
    if ($script:DisplayUnicode -and $Width -ge $artWidth -and $Height -ge 26) {
        $padding = " " * [Math]::Max(0, [int][Math]::Floor(($Width - $artWidth) / 2))
        foreach ($line in $script:StartupPanelArt) { $padding + $line }
        ""
        $script:StartupPanelArtRows = 7
    }
    $brand = "界鉴  JIEJIAN"
    if ($script:StartupPanelVersion) { $brand += "  " + $script:StartupPanelVersion }
    Format-StartupLine $brand $Width $script:StartupPanelStatus
    "让权限要求与实际行为对应起来"
    ""
    Format-StartupLine $script:StartupPanelTitle $Width
    Format-StartupLine $script:StartupPanelDetail $Width
    ""
    # 项目与状态按同一紧凑列宽居中，避免宽终端把配对信息推向两端。
    $stageWidth = [Math]::Min(40, $Width)
    $stageMargin = " " * [Math]::Max(0, [int][Math]::Floor(($Width - $stageWidth) / 2))
    for ($index = 1; $index -le 6; $index++) {
        $state = $script:StartupPanelStates[$index]
        $mark = "·"; $label = "等待"
        switch ($state) {
            "running" { $mark = "›"; $label = "处理中" }
            "done" { $mark = "✓"; $label = "已就绪" }
            "failed" { $mark = "×"; $label = "未完成" }
            "stopped" { $mark = "·"; $label = "已停止" }
            "unused" { $mark = "·"; $label = "未启动" }
        }
        if (-not $script:DisplayUnicode) {
            $mark = switch ($state) { "running" { ">" }; "done" { "+" }; "failed" { "!" }; default { "-" } }
        }
        $stageMargin + (Format-StartupLine ("{0}  {1}" -f $mark, $script:StartupPanelLabels[$index - 1]) $stageWidth $label)
    }
    ""
    $(if ($script:DisplayUnicode) { "─" } else { "-" }) * $Width
    $elapsed = if ($null -ne $script:StartupPanelReadySeconds) {
        $label = if ($script:StartupPanelStatus -eq "准备完成") { "准备用时" } else { "启动用时" }
        "{0} {1:N1} 秒" -f $label, $script:StartupPanelReadySeconds
    } elseif ($null -ne $script:StartupPanelClock) {
        "启动已用 {0:N0} 秒" -f [Math]::Floor($script:StartupPanelClock.Elapsed.TotalSeconds)
    } else { "" }
    # 父进程和等待动画共用这一行；重绘前先交还输出权，面板不保留另一份静态计时。
    Format-StartupLine $elapsed $Width $script:StartupPanelKeys
}

function Write-StartupPanel {
    if (-not $script:StartupPanelActive) { return }
    Stop-WaitIndicator
    try {
        $terminalWidth = [Console]::WindowWidth
        $width = [Math]::Min(88, $terminalWidth - 6)
        if ($width -lt 38 -or [Console]::WindowHeight -lt 19) {
            Close-StartupPanel
            Write-Host $script:StartupPanelTitle
            Write-Host $script:StartupPanelDetail
            return
        }
        $margin = " " * [Math]::Max(0, [int][Math]::Floor(($terminalWidth - $width) / 2))
        $escape = [char]27
        # 宽度变化时旧行可能已被终端重新折行；重新建立锚点，避免误擦调用者历史。
        if ($script:StartupPanelRows -gt 0 -and $terminalWidth -eq $script:StartupPanelWidth) {
            [Console]::Write(("`r{0}[{1}A" -f $escape, ($script:StartupPanelRows - 1)))
        } else { [Console]::Write("`r`n") }
        $lines = @(Get-StartupPanelLines $width ([Console]::WindowHeight))
        $output = New-Object Text.StringBuilder
        for ($index = 0; $index -lt $lines.Count; $index++) {
            $logical = $index - $script:StartupPanelArtRows
            $color = "38;2;" + $script:StartupPanelPalette.Muted
            if ($logical -eq 0 -or $logical -eq 3) { $color = "38;2;" + $script:StartupPanelPalette.Accent }
            if ($logical -eq 4 -and $script:StartupPanelStatus -eq "启动未完成") { $color = "38;2;" + $script:StartupPanelPalette.Danger }
            if ($logical -ge 6 -and $logical -lt 12 -and $script:StartupPanelStates[$logical - 5] -eq "running") { $color = "38;2;" + $script:StartupPanelPalette.Accent }
            if ($script:StartupPanelArtRows -gt 0 -and $index -lt 6) { $color = "38;2;" + $script:StartupPanelArtColors[$index] }
            if (-not $script:DisplayTrueColor) { $color = if ($logical -lt 0) { "94" } elseif ($logical -eq 0 -or $logical -eq 3) { "97" } else { "37" } }
            [void]$output.Append(("{0}[2K{1}{0}[{2}m{3}{0}[0m" -f $escape, $margin, $color, $lines[$index]))
            if ($index -lt ($lines.Count - 1)) { [void]$output.Append("`r`n") }
        }
        [Console]::Write($output.ToString())
        $script:StartupPanelRows = $lines.Count
        $script:StartupPanelWidth = $terminalWidth
    } catch {
        $script:StartupPanelActive = $false
        $script:StartupPanelRows = 0
        Write-Host $script:StartupPanelTitle
        Write-Host $script:StartupPanelDetail
    }
}

function Set-StartupStatus([string]$Status, [string]$Title, [string]$Detail) {
    Stop-WaitIndicator
    $script:StartupPanelStatus = $Status
    $script:StartupPanelTitle = $Title
    $script:StartupPanelDetail = $Detail
    if ($Status -in @("已就绪", "准备完成")) {
        $script:StartupPanelStates[6] = if ($Status -eq "已就绪") { "done" } else { "unused" }
        if ($null -eq $script:StartupPanelReadySeconds -and $null -ne $script:StartupPanelClock) {
            $script:StartupPanelReadySeconds = $script:StartupPanelClock.Elapsed.TotalSeconds
            $script:StartupPanelClock.Stop()
            if ($null -ne $script:DisplayStageTimer) { $script:DisplayStageTimer.Stop() }
        }
    }
    if ($Status -eq "准备完成") { $script:StartupPanelKeys = "" }
    if ($Status -eq "已停止") { $script:StartupPanelStates[6] = "stopped"; $script:StartupPanelKeys = "" }
    if ($script:StartupPanelActive) { Write-StartupPanel }
    else { Write-Host $Title; if ($Detail) { Write-Host $Detail -ForegroundColor Gray } }
}

function Close-StartupPanel {
    Stop-WaitIndicator
    if ($script:StartupPanelActive) { [Console]::Write("`r`n") }
    $script:StartupPanelActive = $false
    $script:StartupPanelRows = 0
}
