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
    [ValidateRange(1, 2147483647)][int]$NoProgressTimeoutSeconds,
    [string]$Recovery
) {
    if ($Invocation.Count -lt 1) { Fail-Development $Stage "缺少外部命令" "检查开发脚本参数" }
    $executable = $Invocation[0]
    [string[]]$arguments = if ($Invocation.Count -gt 1) { @($Invocation[1..($Invocation.Count - 1)]) } else { @() }
    # Windows PowerShell 5.1 的 Start-Process 回读可能丢失退出码；直接拥有 Process 句柄直到收口。
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $executable
    $startInfo.Arguments = $arguments -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    # 显式回读两条流：继承控制台句柄的孙进程输出不会经过源码启动器的 PowerShell 日志管道。
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
    $startInfo.StandardErrorEncoding = New-Object Text.UTF8Encoding($false)
    $process = [Diagnostics.Process]::Start($startInfo)
    $streams = @(
        @{ reader = $process.StandardOutput; pending = $process.StandardOutput.ReadLineAsync(); done = $false },
        @{ reader = $process.StandardError; pending = $process.StandardError.ReadLineAsync(); done = $false }
    )
    $activity = Get-DownloadActivityToken $ProgressPath
    $idle = [Diagnostics.Stopwatch]::StartNew()
    try {
        while ($true) {
            $reported = $false
            foreach ($stream in $streams) {
                while (-not $stream.done -and $stream.pending.IsCompleted) {
                    $line = $stream.pending.GetAwaiter().GetResult()
                    if ($null -eq $line) { $stream.done = $true; break }
                    Write-Output ("[{0}] {1}" -f $Stage, $line)
                    $reported = $true
                    $stream.pending = $stream.reader.ReadLineAsync()
                }
            }
            if ($process.HasExited -and $streams[0].done -and $streams[1].done) { break }
            $current = Get-DownloadActivityToken $ProgressPath
            # 首字节尚未到达时，下载器仍会输出重试和切换地址；不能仅以临时文件判定卡死。
            if ($reported -or $current -ne $activity) {
                $activity = $current
                $idle.Restart()
            } elseif ($idle.Elapsed.TotalSeconds -ge $NoProgressTimeoutSeconds) {
                Stop-ExternalProcessTree $process
                Fail-Development $Stage (
                    "下载器连续 {0} 秒没有文件进度或输出，已停止本次等待" -f $NoProgressTimeoutSeconds
                ) $Recovery
            }
            [void]$process.WaitForExit(200)
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
        [Console]::Out.WriteLine("__JIEJIAN_BROWSER_PHASE__:download")
        Write-Host "正在准备 Playwright Chromium……" -ForegroundColor Cyan
        $downloadRoot = Join-Path $script:DevelopmentRoot "cache\downloads\playwright"
        New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
        $processEnvironment = [Environment]::GetEnvironmentVariables("Process")
        $temporaryEnvironment = @{}
        foreach ($name in @("TEMP", "TMP", "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT")) {
            $temporaryEnvironment[$name] = [pscustomobject]@{
                exists = $processEnvironment.Contains($name)
                value = [Environment]::GetEnvironmentVariable($name, "Process")
            }
        }
        try {
            [int]$socketTimeout = 120000
            $configuredTimeout = [Environment]::GetEnvironmentVariable("PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT", "Process")
            if (-not [string]::IsNullOrWhiteSpace($configuredTimeout)) {
                if (-not [int]::TryParse($configuredTimeout, [ref]$socketTimeout) -or $socketTimeout -lt 0) {
                    Fail-Development "browser-download" "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT 应为非负整数，单位为毫秒" "修正当前终端中的下载超时设置后重新运行 start.cmd"
                }
            } else {
                $env:PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT = [string]$socketTimeout
            }
            # Playwright 的 0 表示沿用其默认 30 秒；外层多留一分钟供重试输出及安装收尾。
            $watchdogSeconds = [int][Math]::Ceiling($(if ($socketTimeout -eq 0) { 30000 } else { $socketTimeout }) / 1000.0) + 60
            $env:TEMP = $downloadRoot
            $env:TMP = $downloadRoot
            Write-Output "[browser-download] 下载输出将写入启动日志；慢连接会按下载器的超时和重试策略继续。"
            Invoke-ExternalWithProgressTimeout "browser-download" @($script:Python, "-B", "-m", "playwright", "install", "chromium") $downloadRoot $watchdogSeconds "查看启动日志中的 [browser-download] 输出；使用代理时核对 cdn.playwright.dev 和 storage.googleapis.com 的连接，必要时为当前终端设置 HTTPS_PROXY 后重新运行 start.cmd。已完成的依赖会继续复用"
        } finally {
            foreach ($name in @("TEMP", "TMP", "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT")) {
                $record = $temporaryEnvironment[$name]
                if ($record.exists) { [Environment]::SetEnvironmentVariable($name, [string]$record.value, "Process") }
                else { Remove-Item -LiteralPath ("Env:" + $name) -ErrorAction SilentlyContinue }
            }
        }
        [Console]::Out.WriteLine("__JIEJIAN_BROWSER_PHASE__:verify")
        $path = (& $script:Python -B -c $probe 2>$null | Out-String).Trim()
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { Fail-Development "browser-verify" "浏览器安装命令已结束，但尚未找到所需的 Chromium 可执行文件；下载 100% 不代表安装就绪" "查看本次启动日志中的 Playwright 输出，检查安装目录访问权限后重试 start.cmd" }
    $env:JIEJIAN_PLAYWRIGHT_EXECUTABLE = [IO.Path]::GetFullPath($path)
    Write-PrepareStatus "browser" "done"
}

function Prepare-Database {
    Write-PrepareStatus "database" "start"
    Invoke-External "migration" @(
        $script:Python,
        "-B",
        "-c",
        "import sys; from pathlib import Path; from product.backend.infrastructure.storage import default_database_path, prepare_database; prepare_database(default_database_path(Path(sys.argv[1])))",
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
    # prepare lock 仍持有；登记完成之前不能让清理器看见未受保护的新环境。
    Invoke-External "source-assets" @($script:Python, "-B", "-c", "import sys; from pathlib import Path; from product.backend.infrastructure.maintenance.inventory import register_startup_assets; register_startup_assets(Path(sys.argv[1]), Path(sys.argv[2]))", $script:VarDir, $script:DevelopmentRoot)
    Write-Host ("源码运行环境回执：{0}" -f $receiptPath) -ForegroundColor Green
}

function Prepare-SourceRuntime($Toolchain) {
    Prepare-Chromium
    Prepare-SourceFrontend $Toolchain
    Prepare-Database
    Write-SourceReceipt
}
