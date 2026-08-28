# 界鉴源码启动准备：Chromium、数据库、前端回执和受控运行时编排。

function Get-DownloadActivityToken([string]$Path) {
    [long]$length = 0
    [long]$latestWriteTicks = 0
    [int]$count = 0
    if (Test-Path -LiteralPath $Path -PathType Container) {
        foreach ($file in @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue)) {
            $count++
            $length += [long]$file.Length
            if ($file.LastWriteTimeUtc.Ticks -gt $latestWriteTicks) { $latestWriteTicks = $file.LastWriteTimeUtc.Ticks }
        }
    }
    return ("{0}|{1}|{2}" -f $count, $length, $latestWriteTicks)
}

function Stop-ExternalProcessTree([Diagnostics.Process]$Process) {
    if ($null -eq $Process -or $Process.HasExited) { return }
    # 下载器会通过 Python 启动 Node 子进程，超时时必须回收整棵进程，避免孤儿进程继续占用 prepare lock。
    $taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
    & $taskkill /PID $Process.Id /T /F 2>$null | Out-Null
    $treeStopExitCode = $LASTEXITCODE
    if ($treeStopExitCode -ne 0) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit()
    } elseif (-not $Process.WaitForExit(5000)) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit()
    }
}

function Invoke-ExternalWithProgressTimeout(
    [string]$Stage,
    [string[]]$Invocation,
    [string]$ProgressPath,
    [ValidateRange(1, 3600)][int]$NoProgressTimeoutSeconds,
    [string]$Recovery
) {
    if ($Invocation.Count -lt 1) { Fail-Development $Stage "缺少外部命令" "检查开发脚本参数" }
    $executable = $Invocation[0]
    [string[]]$arguments = if ($Invocation.Count -gt 1) { @($Invocation[1..($Invocation.Count - 1)]) } else { @() }
    $process = Start-Process -FilePath $executable -ArgumentList $arguments -NoNewWindow -PassThru
    $activity = Get-DownloadActivityToken $ProgressPath
    $idle = [Diagnostics.Stopwatch]::StartNew()
    try {
        while (-not $process.WaitForExit(1000)) {
            $current = Get-DownloadActivityToken $ProgressPath
            if ($current -ne $activity) {
                $activity = $current
                $idle.Restart()
            } elseif ($idle.Elapsed.TotalSeconds -ge $NoProgressTimeoutSeconds) {
                Stop-ExternalProcessTree $process
                Fail-Development $Stage (
                    "网络下载连续 {0} 秒没有写入新数据，已停止本次等待" -f $NoProgressTimeoutSeconds
                ) $Recovery
            }
        }
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            Fail-Development $Stage ("外部命令返回 {0}" -f $process.ExitCode) $Recovery
        }
    } finally {
        $idle.Stop()
        if (-not $process.HasExited) { Stop-ExternalProcessTree $process }
        $process.Dispose()
    }
}

function Prepare-Chromium {
    Write-PrepareStatus "browser" "start"
    $probe = "from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); x=Path(p.chromium.executable_path).resolve(); p.stop(); print(x); raise SystemExit(0 if x.is_file() else 1)"
    $path = (& $script:Python -B -c $probe 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($path)) {
        Write-Host "正在准备 Playwright Chromium……" -ForegroundColor Cyan
        $downloadRoot = Join-Path $script:DevelopmentRoot "cache\downloads\playwright"
        New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
        $processEnvironment = [Environment]::GetEnvironmentVariables("Process")
        $temporaryEnvironment = @{}
        foreach ($name in @("TEMP", "TMP")) {
            $temporaryEnvironment[$name] = [pscustomobject]@{
                exists = $processEnvironment.Contains($name)
                value = [Environment]::GetEnvironmentVariable($name, "Process")
            }
            [Environment]::SetEnvironmentVariable($name, $downloadRoot, "Process")
        }
        try {
            Invoke-ExternalWithProgressTimeout "playwright" @($script:Python, "-B", "-m", "playwright", "install", "chromium") $downloadRoot 60 "检查网络，或在能正常访问 Playwright CDN 的真实用户 PowerShell 中重新运行 .\scripts\dev.ps1 prepare -ForcePrepare；完成后再继续"
        } finally {
            foreach ($name in @("TEMP", "TMP")) {
                $record = $temporaryEnvironment[$name]
                if ($record.exists) { [Environment]::SetEnvironmentVariable($name, [string]$record.value, "Process") }
                else { [Environment]::SetEnvironmentVariable($name, $null, "Process") }
            }
        }
        $path = (& $script:Python -B -c $probe 2>$null | Out-String).Trim()
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { Fail-Development "playwright" "Chromium 可执行文件探针失败" "检查网络和 var/development/tools/playwright 后重试" }
    $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE = [IO.Path]::GetFullPath($path)
    Write-PrepareStatus "browser" "done"
}

function Prepare-Database {
    Write-PrepareStatus "database" "start"
    Invoke-External "migration" @(
        $script:Python,
        "-B",
        "-c",
        "import sys; from pathlib import Path; from product.backend.infra.storage import default_database_path, upgrade_database; upgrade_database(default_database_path(Path(sys.argv[1])))",
        $script:VarDir
    )
    Write-PrepareStatus "database" "done"
}

function Write-SourceReceipt {
    $identity = Read-DevelopmentIdentity
    if ($null -eq $identity -or -not $identity.ok) { Fail-Development "python-identity" "无法为源码启动形成可信环境回执" "执行 .\scripts\dev.ps1 sync" }
    $pythonVersion = (& $script:Python -S -B -c "import platform; print(platform.python_version())" 2>$null | Out-String).Trim()
    $receiptPath = Join-Path $script:VarDir "runtime\source\receipt.json"
    $receipt = [ordered]@{
        schema_version = "1"; project_root = $script:ProjectRoot; var_dir = $script:VarDir; runtime_mode = "development"
        python = [ordered]@{ executable = $script:Python; version = $pythonVersion; environment_path = $script:CondaPrefix; environment_type = "conda"; runtime_fingerprint = [string]$identity.runtime_fingerprint; report = $identity }
        uv = [ordered]@{ executable = $script:Uv; version = $script:UvVersion }
        node = [ordered]@{ executable = $env:JIEJIAN_NODE_EXECUTABLE; version = $env:JIEJIAN_NODE_VERSION }
        pnpm = [ordered]@{ executable = $env:JIEJIAN_PNPM_EXECUTABLE; version = $env:JIEJIAN_PNPM_VERSION }
        playwright = [ordered]@{ executable = $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE; browsers_path = $env:PLAYWRIGHT_BROWSERS_PATH }
        frontend = [ordered]@{ dist = $env:JIEJIAN_FRONTEND_DIST; dependencies = $env:JIEJIAN_FRONTEND_DEPENDENCIES; build_state = $script:FrontendBuildState }
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $receiptPath) -Force | Out-Null
    $temporary = "$receiptPath.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [IO.File]::WriteAllText($temporary, ($receipt | ConvertTo-Json -Depth 12 -Compress), $script:Utf8NoBom)
        if (Test-Path -LiteralPath $receiptPath -PathType Leaf) { Remove-Item -LiteralPath $receiptPath -Force }
        [IO.File]::Move($temporary, $receiptPath)
    } finally { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
    Write-Host ("源码运行环境回执：{0}" -f $receiptPath) -ForegroundColor Green
}

function Prepare-SourceRuntime($Toolchain) {
    Prepare-Chromium
    Prepare-SourceFrontend $Toolchain
    Prepare-Database
    Write-SourceReceipt
}
