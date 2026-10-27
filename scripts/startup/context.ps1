# 初始化源码启动状态；环境快照和恢复由共用会话库负责。

function Initialize-StartupContext([string]$Root, [string]$RuntimeRoot, [string]$EntryMode) {
    $script:FinalMode = $EntryMode
    $script:ProjectRoot = $Root
    $script:DevelopmentRoot = [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot "var\development"))
    if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
        $RuntimeRoot = Join-Path $script:ProjectRoot "var"
    } elseif (-not [IO.Path]::IsPathRooted($RuntimeRoot)) {
        $RuntimeRoot = Join-Path $script:ProjectRoot $RuntimeRoot
    }
    $script:VarDir = [IO.Path]::GetFullPath($RuntimeRoot)
    $script:LogDir = Join-Path $script:VarDir "logs\startup"
    $script:LogPath = Join-Path $script:LogDir ("{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
    $script:ToolchainPath = Join-Path $script:ProjectRoot "product\config\toolchain.json"
    $script:StartupLogInitialized = $false
    $script:FailureStage = "startup"
    $script:FailureCode = 0
    $script:UvExecutable = $null
    $script:PackageRunner = $null
    $script:PythonExecutable = $null
    $script:PythonEnvironmentType = $null
    $script:PythonEnvironmentPath = $null
    $script:UvVersion = $null
    $script:NodeVersion = $null
    $script:PnpmVersion = $null
    $script:NodeExecutable = $null
    $script:PnpmExecutable = $null
    $script:PythonFingerprint = $null
    $script:FrontendDependenciesDetail = $null
    $script:FrontendBuildDetail = $null
    $script:ChromiumExecutable = $null
    $script:ServeReadyObserved = $false
    $script:ServeStartupFailed = $false
    $script:CliEntryMode = "Shell"
    $script:FrontendDist = $null
    $script:DisplayStageName = $null
    $script:DisplayStageTimer = $null
    $script:DisplayStageSkipped = $false
    $script:DisplayStageIndex = 0
    $script:DisplayInteractive = $false
    $script:DisplayUnicode = $false
    $script:DisplayTrueColor = $false
    $script:WaitIndicatorProcess = $null
    $script:WaitIndicatorStopEvent = $null
    $script:WaitIndicatorFallbackActive = $false
    $script:PrepareStatusOrder = @("toolchain", "python", "browser", "frontend-dependencies", "frontend-build", "database")
    $script:PrepareStatusIndex = 0
    $script:PrepareStatusState = @{}

    $script:Utf8Encoding = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
    [Console]::InputEncoding = $script:Utf8Encoding
    [Console]::OutputEncoding = $script:Utf8Encoding

    try {
        $script:DisplayInteractive = -not [Console]::IsInputRedirected -and
            -not [Console]::IsOutputRedirected
        $supportsVirtualTerminal = $false
        try { $supportsVirtualTerminal = [bool]$Host.UI.SupportsVirtualTerminal } catch { $supportsVirtualTerminal = $false }
        $script:DisplayUnicode = $script:DisplayInteractive -and
            [Console]::OutputEncoding.CodePage -eq 65001 -and
            $Host.UI.RawUI.WindowSize.Width -ge 44 -and
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
}
