# =============================================================================
# 启动运行时准备
#
# 定位
# 为 start.ps1 提供外部工具探测、固定运行时恢复与依赖验证。
#
# 职责
# 探测 Python/Node/pnpm｜记录外部命令与退出码｜准备环境与浏览器依赖
#
# 边界
# 不吞外部退出码，不静默回退到错误 Python，也不接管服务业务逻辑。
#
# 调用链
# start.cmd → scripts/start.ps1 → 本脚本 → 固定运行时与依赖检查
# =============================================================================
# 机器阶段码保留给日志与错误代码，界面使用稳定中文名称。
function Get-StageDisplayName([string]$Stage) {
    $names = @{
        "arguments" = "启动参数"
        "mode" = "启动方式"
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

# 统一终止启动：记录可恢复诊断，并用稳定退出码结束当前脚本。
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

# 外部命令的 stdout/stderr 只进入启动日志；调用者只接收稳定成功或 Fail-Start。
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
    $invokeArguments = @()
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
        if ([string]::IsNullOrWhiteSpace($Recovery)) {
            $Recovery = Get-RecoveryCommand
        }
        Fail-Start $FailureCode $Stage "外部命令返回 $code" $Recovery
    }
}

# package.json 决定可复用版本边界；固定下载版本与校验值是下方独立的安全 allowlist。
function Read-FrontendToolRequirements {
    $packagePath = Join-Path $script:ProjectRoot "product\frontend\package.json"
    try {
        $package = Get-Content -LiteralPath $packagePath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Fail-Start 30 "node" "无法读取前端 package.json 版本真源" "修复 product\frontend\package.json 后重新执行本脚本"
    }
    $nodeRequirement = [string]$package.engines.node
    $pnpmRequirement = [string]$package.packageManager
    $nodeRange = [regex]::Match($nodeRequirement, "^\s*>=\s*(?<minimum>\d+\.\d+\.\d+)\s*<\s*(?<maximum>\d+)(?:\.\d+\.\d+)?\s*$")
    $pnpmMatch = [regex]::Match($pnpmRequirement, "^pnpm@(?<version>\d+\.\d+\.\d+)$")
    if (-not $nodeRange.Success) {
        Fail-Start 30 "node" "前端 package.json 的 Node 版本范围不可安全解析" "修复 engines.node 后重新执行本脚本"
    }
    if (-not $pnpmMatch.Success) {
        Fail-Start 31 "pnpm" "前端 package.json 的 pnpm 版本声明不可安全解析" "修复 packageManager 后重新执行本脚本"
    }
    $script:NodeRequirement = [pscustomobject]@{
        text = $nodeRequirement
        minimum = [version]$nodeRange.Groups["minimum"].Value
        maximum_major = [int]$nodeRange.Groups["maximum"].Value
    }
    $script:PnpmRequirement = $pnpmMatch.Groups["version"].Value
}

function Get-ToolVersion([string]$Executable, [string]$FailureStage) {
    try {
        $value = (& $Executable --version 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) { return $null }
        return ($value -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1).Trim()
    } catch { return $null }
}

function Test-NodeVersion([string]$Value) {
    $match = [regex]::Match($Value, "^v?(?<version>\d+\.\d+\.\d+)$")
    if (-not $match.Success -or $null -eq $script:NodeRequirement) { return $false }
    try {
        $parsed = [version]$match.Groups["version"].Value
        return $parsed -ge $script:NodeRequirement.minimum -and $parsed.Major -lt $script:NodeRequirement.maximum_major
    } catch { return $false }
}

function Get-WindowsNodeArchitecture {
    $raw = $env:PROCESSOR_ARCHITEW6432
    if ([string]::IsNullOrWhiteSpace($raw)) { $raw = $env:PROCESSOR_ARCHITECTURE }
    switch ([string]$raw.ToUpperInvariant()) {
        "AMD64" { return "x64" }
        "ARM64" { return "arm64" }
        default { return $null }
    }
}

function Get-NodeExecutableVersion([string]$Executable) {
    if ([string]::IsNullOrWhiteSpace($Executable) -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $null }
    $version = Get-ToolVersion $Executable "node"
    if (-not (Test-NodeVersion $version)) { return $null }
    return $version
}

function Get-NodeCachePath([string]$Architecture) {
    return [IO.Path]::GetFullPath((Join-Path $script:VarDir ("runtime\node\24.19.0\{0}\node.exe" -f $Architecture)))
}

function Get-NodeArchiveMetadata([string]$Architecture) {
    switch ($Architecture) {
        "x64" {
            return [pscustomobject]@{
                url = "https://nodejs.org/dist/v24.19.0/node-v24.19.0-win-x64.zip"
                hash = "57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73"
            }
        }
        "arm64" {
            return [pscustomobject]@{
                url = "https://nodejs.org/dist/v24.19.0/node-v24.19.0-win-arm64.zip"
                hash = "8502f4a50b458d4cc38ed8f2001556c2cd239d464920f74017926ccb1e1c157f"
            }
        }
        default { return $null }
    }
}

function Get-Sha256([string]$Path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try { return (([BitConverter]::ToString($sha.ComputeHash($stream))) -replace "-", "").ToLowerInvariant() }
        finally { $stream.Dispose() }
    } finally { $sha.Dispose() }
}

function Prepare-NodeRuntime([string]$Architecture) {
    $metadata = Get-NodeArchiveMetadata $Architecture
    if ($null -eq $metadata) {
        Fail-Start 30 "node" "不支持当前 Windows 架构" "使用 AMD64 或 ARM64 Windows 环境后重试"
    }
    $runtimeRoot = Join-Path $script:VarDir "runtime\node\24.19.0"
    $script:DownloadTemp = Join-Path $script:VarDir ("temp\downloads\node-{0}" -f [guid]::NewGuid().ToString("N"))
    $nodeDownloadTemp = $script:DownloadTemp
    $archive = Join-Path $script:DownloadTemp (Split-Path -Leaf ([uri]$metadata.url).AbsolutePath)
    $extract = Join-Path $script:DownloadTemp "extract"
    Start-WaitIndicator "node-search"
    try {
        New-Item -ItemType Directory -Path $script:DownloadTemp -Force | Out-Null
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $metadata.url -OutFile $archive -UseBasicParsing
        if ((Get-Sha256 $archive) -ne $metadata.hash) {
            Fail-Start 30 "node" "Node.js 官方归档校验失败" "删除 VarDir 中的临时下载后检查网络与官方归档"
        }
        # 只有校验通过后才解压和提升为可执行缓存；临时目录始终位于 VarDir。
        Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force
        $sourceRoot = Get-ChildItem -LiteralPath $extract -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "node.exe") -PathType Leaf } | Select-Object -First 1
        if ($null -eq $sourceRoot) {
            Fail-Start 30 "node" "校验后的 Node.js 归档缺少 node.exe" "删除 VarDir 中的临时下载后重新执行本脚本"
        }
        $cacheDirectory = Join-Path $runtimeRoot $Architecture
        $promotion = Join-Path $runtimeRoot (".{0}-promote-{1}" -f $Architecture, [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $promotion -Force | Out-Null
        Copy-Item -Path (Join-Path $sourceRoot.FullName "*") -Destination $promotion -Recurse -Force
        if (Test-Path -LiteralPath $cacheDirectory -PathType Container) { Remove-Item -LiteralPath $cacheDirectory -Recurse -Force }
        New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
        Move-Item -LiteralPath $promotion -Destination $cacheDirectory
        $candidate = Get-NodeCachePath $Architecture
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            Fail-Start 30 "node" "Node.js 缓存提升后缺少可执行文件" "删除 VarDir 中的 Node runtime 缓存后重试"
        }
        return $candidate
    } catch {
        if ($script:FailureCode -gt 0) { throw }
        Fail-Start 30 "node" ("Node.js 官方归档准备失败: " + $_.Exception.Message) "检查网络后重新执行本脚本"
    } finally {
        Stop-WaitIndicator
        if (Test-Path -LiteralPath $nodeDownloadTemp) {
            Remove-Item -LiteralPath $nodeDownloadTemp -Recurse -Force -ErrorAction SilentlyContinue
        }
        if ($script:DownloadTemp -eq $nodeDownloadTemp) { $script:DownloadTemp = $null }
    }
}

function Set-PrivateNodeEnvironment {
    $corepackHome = Join-Path $script:VarDir "runtime\corepack"
    $pnpmHome = Join-Path $script:VarDir "runtime\pnpm"
    $npmCache = Join-Path $script:VarDir "cache\npm"
    New-Item -ItemType Directory -Path $corepackHome, $pnpmHome, $npmCache -Force | Out-Null
    $env:COREPACK_HOME = [IO.Path]::GetFullPath($corepackHome)
    # Corepack 只能按 packageManager 非交互准备固定版本，不能把下载确认隐藏在启动界面后等待输入。
    $env:COREPACK_ENABLE_DOWNLOAD_PROMPT = "0"
    $env:PNPM_HOME = [IO.Path]::GetFullPath($pnpmHome)
    $env:npm_config_cache = [IO.Path]::GetFullPath($npmCache)
    $nodeDirectory = Split-Path -Parent $script:NodeExecutable
    $pathParts = @($nodeDirectory, $pnpmHome) + @($env:PATH -split ";") | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }
    $env:PATH = ($pathParts | Select-Object -Unique) -join ";"
}

function Resolve-PnpmRuntime {
    $frontend = Join-Path $script:ProjectRoot "product\frontend"
    $privatePnpmShim = [IO.Path]::GetFullPath((Join-Path $env:PNPM_HOME "pnpm.cmd"))
    $shimTemporary = $null
    # 系统 pnpm 可能本身就是 Corepack shim；必须先进入含 packageManager 的目录，避免探测时下载错误版本。
    Push-Location -LiteralPath $frontend
    try {
        Start-WaitIndicator "pnpm-check"
        # 上次准备生成的 shim 依赖父进程注入的 Corepack 路径；探测系统工具前先移除，避免陈旧入口遮蔽系统 pnpm。
        if (Test-Path -LiteralPath $privatePnpmShim) {
            Remove-Item -LiteralPath $privatePnpmShim -Force -ErrorAction Stop
        }
        $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($pnpm) {
            $candidate = [IO.Path]::GetFullPath($pnpm.Source)
            $version = Get-ToolVersion $candidate "pnpm"
            if ($version -eq $script:PnpmRequirement) {
                $script:PnpmExecutable = $candidate
                $script:PnpmRunner = @($candidate)
                $script:PnpmVersion = $version
                return
            }
            Write-Startup "系统 pnpm 不符合 packageManager，转用私有 Corepack runner"
        }
        $corepack = Get-Command corepack -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $corepack) {
            Fail-Start 31 "pnpm" "未找到可用的 Corepack 或符合版本的 pnpm" "确认 Node.js 自带 Corepack 可用后重新执行本脚本"
        }
        $script:CorepackExecutable = [IO.Path]::GetFullPath($corepack.Source)
        $corepackOutput = (& $script:CorepackExecutable "pnpm" "--version" 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($corepackOutput)) {
            Fail-Start 31 "pnpm" "Corepack 无法准备项目声明的 pnpm" "检查 Node.js 自带 Corepack 后重新执行本脚本"
        }
        $version = ($corepackOutput -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1).Trim()
        if ($version -ne $script:PnpmRequirement) {
            Fail-Start 31 "pnpm" "Corepack 返回的 pnpm 版本不符合 packageManager: $version" "检查 Corepack 缓存后重新执行本脚本"
        }
        # doctor 与 CLI 子进程按普通可执行文件重新发现 pnpm；ASCII shim 通过环境变量转发，避免把中文绝对路径写进批处理。
        $env:JIEJIAN_COREPACK_EXECUTABLE = $script:CorepackExecutable
        $shimTemporary = $privatePnpmShim + ".tmp-" + [guid]::NewGuid().ToString("N")
        $shimContent = "@echo off`r`ncall `"%JIEJIAN_COREPACK_EXECUTABLE%`" pnpm %*`r`n"
        [IO.File]::WriteAllText($shimTemporary, $shimContent, [Text.Encoding]::ASCII)
        Move-Item -LiteralPath $shimTemporary -Destination $privatePnpmShim -Force
        $shimTemporary = $null
        $shimVersion = Get-ToolVersion $privatePnpmShim "pnpm"
        if ($shimVersion -ne $script:PnpmRequirement) {
            Fail-Start 31 "pnpm" "pnpm 进程入口准备后无法执行" "删除 VarDir/runtime/pnpm 后重新执行本脚本"
        }
        $script:PnpmExecutable = $privatePnpmShim
        $script:PnpmRunner = @($privatePnpmShim)
        $script:PnpmVersion = $version
    } finally {
        if ($shimTemporary -and (Test-Path -LiteralPath $shimTemporary)) {
            Remove-Item -LiteralPath $shimTemporary -Force -ErrorAction SilentlyContinue
        }
        Stop-WaitIndicator
        Pop-Location
    }
}

# 前端工具链必须同时满足 package 真源和可执行性，避免构建阶段才暴露环境漂移。
function Test-NodeAndPnpm {
    Read-FrontendToolRequirements
    $cached = $null
    $cachedVersion = $null
    Start-WaitIndicator "node-search"
    try {
        $script:NodeArchitecture = Get-WindowsNodeArchitecture
        $systemNode = Get-Command node -ErrorAction SilentlyContinue | Select-Object -First 1
        $systemNodePath = if ($systemNode) { [IO.Path]::GetFullPath($systemNode.Source) } else { $null }
        $systemNodeVersion = Get-NodeExecutableVersion $systemNodePath
        if (-not $systemNodeVersion -and -not [string]::IsNullOrWhiteSpace($script:NodeArchitecture)) {
            $cached = Get-NodeCachePath $script:NodeArchitecture
            $cachedVersion = Get-NodeExecutableVersion $cached
        }
    } finally {
        Stop-WaitIndicator
    }
    if ($systemNodeVersion) {
        $script:NodeExecutable = $systemNodePath
        $script:NodeVersion = $systemNodeVersion
        $script:NodeRuntimeDetail = "$systemNodeVersion · 系统环境"
    } else {
        if ([string]::IsNullOrWhiteSpace($script:NodeArchitecture)) {
            Fail-Start 30 "node" "不支持当前 Windows 架构" "使用 AMD64 或 ARM64 Windows 环境后重试"
        }
        if ($cachedVersion) {
            $script:NodeExecutable = $cached
            $script:NodeVersion = $cachedVersion
            $script:NodeRuntimeDetail = "$cachedVersion · 界鉴私有 runtime"
        } else {
            $script:NodeExecutable = Prepare-NodeRuntime $script:NodeArchitecture
            $script:NodeVersion = Get-NodeExecutableVersion $script:NodeExecutable
            if (-not $script:NodeVersion) { Fail-Start 30 "node" "受控 Node.js runtime 探针失败" "删除 VarDir 中的 Node runtime 缓存后重试" }
            $script:NodeRuntimeDetail = "$script:NodeVersion · 界鉴私有 runtime"
        }
    }
    Set-PrivateNodeEnvironment
    Resolve-PnpmRuntime
    $toolFacts = @{
        node_version = $script:NodeVersion
        node_path = $script:NodeExecutable
        node_architecture = $script:NodeArchitecture
        pnpm_version = $script:PnpmVersion
        pnpm_path = $script:PnpmExecutable
        pnpm_runner = ($script:PnpmRunner -join " ")
        package_manager = $script:PnpmRequirement
        node_requirement = $script:NodeRequirement.text
    }
    $script:ToolchainFingerprint = Get-StageFingerprint @((Join-Path $script:ProjectRoot "product\frontend\package.json")) $toolFacts
    Set-PhaseState "toolchain" $script:ToolchainFingerprint $toolFacts
    $script:PnpmRuntimeDetail = "$script:PnpmVersion · $([IO.Path]::GetFileName($script:PnpmExecutable))"
}

# 只识别环境声明指定的 Conda 名称，不根据 PATH 猜测任意 Python。
function Get-CondaEnvironment {
    Start-WaitIndicator "python-search"
    try {
        $conda = Get-Command conda -ErrorAction SilentlyContinue
        if (-not $conda) { return $null }
        $script:CondaExecutable = $conda.Source
        $json = & $script:CondaExecutable env list --json 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            Fail-Start 20 "conda" "无法读取 Conda 环境列表" "修复 Conda 后重新执行本脚本"
        }
        try {
            $items = ($json | ConvertFrom-Json).envs
        } catch {
            Fail-Start 20 "conda" "Conda 环境列表不是有效 JSON" "修复 Conda 后重新执行本脚本"
        }
    } finally {
        Stop-WaitIndicator
    }
    Write-Startup "已读取 Conda 环境列表"
    $found = @($items | Where-Object { (Split-Path -Leaf ([string]$_)) -eq "jiejian_env" } | Select-Object -First 1)
    if ($found.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace([string]$found[0])) {
        return [string]$found[0]
    }
    return $null
}

# Conda 仅提供第三方运行依赖；产品源码始终从当前仓库直接加载。
function Setup-Conda($EnvironmentPrefix, [bool]$SkipEnvironmentUpdate = $false, [bool]$SkipInstall = $false) {
    $environmentFile = Join-Path $script:ProjectRoot "environment.yml"
    if (-not $EnvironmentPrefix) {
        Invoke-External "conda" @($script:CondaExecutable) @("env", "create", "--file", $environmentFile) 20
        $EnvironmentPrefix = Get-CondaEnvironment
    } elseif (-not $SkipEnvironmentUpdate) {
        Invoke-External "conda" @($script:CondaExecutable) @("env", "update", "--name", "jiejian_env", "--file", $environmentFile) 20
    }
    if (-not $EnvironmentPrefix) {
        Fail-Start 20 "conda" "未找到 jiejian_env" "执行 conda env create --file .\environment.yml 后重试"
    }
    $script:PythonEnvironmentType = "Conda"
    $script:PythonEnvironmentPath = [IO.Path]::GetFullPath($EnvironmentPrefix)
    $script:CondaVersion = Get-CommandVersion $script:CondaExecutable @("--version")
    $script:PythonRunner = @($script:CondaExecutable, "run", "--no-capture-output", "--name", "jiejian_env", "python", "-B")
    $script:PackageRunner = @($script:CondaExecutable, "run", "--no-capture-output", "--name", "jiejian_env", "python", "-B", "-m", "product.backend.cli")
    if (-not $SkipInstall) {
        # pyproject.toml 是依赖真源；环境只安装其中的第三方项，不安装项目本身。
        $pyproject = Join-Path $script:ProjectRoot "pyproject.toml"
        $parser = "import json,sys,tomllib; data=tomllib.load(open(sys.argv[1],'rb')); items=list(data.get('project',{}).get('dependencies',[]))+list(data.get('dependency-groups',{}).get('dev',[])); assert items and all(isinstance(item,str) and item.strip() and not item.lstrip().startswith('-') and '\n' not in item and '\r' not in item for item in items); print(json.dumps(items))"
        $pythonArguments = @($script:PythonRunner[1..($script:PythonRunner.Count - 1)]) + @("-c", $parser, $pyproject)
        $rawRequirements = (& $script:PythonRunner[0] @pythonArguments 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($rawRequirements)) {
            Fail-Start 40 "python-dependencies" "无法从 pyproject.toml 读取第三方依赖" (Get-RecoveryCommand)
        }
        try {
            $parsedRequirements = $rawRequirements | ConvertFrom-Json -ErrorAction Stop
            $requirements = @($parsedRequirements | ForEach-Object { $_ })
        } catch {
            Fail-Start 40 "python-dependencies" "pyproject.toml 依赖输出格式无效" (Get-RecoveryCommand)
        }
        if ($requirements.Count -eq 0 -or @($requirements | Where-Object { $_ -isnot [string] -or [string]::IsNullOrWhiteSpace($_) -or $_.TrimStart().StartsWith("-") }).Count -gt 0) {
            Fail-Start 40 "python-dependencies" "pyproject.toml 包含无效第三方依赖" (Get-RecoveryCommand)
        }
        # Conda 的批处理入口会把版本约束中的 < 和 > 当成重定向符；经文件传给 pip 可保留原始 PEP 508 语义。
        $requirementsFile = Join-Path $script:VarDir "cache\python\requirements.txt"
        [IO.Directory]::CreateDirectory((Split-Path -Parent $requirementsFile)) | Out-Null
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllLines($requirementsFile, [string[]]$requirements, $utf8NoBom)
        Invoke-External "python-dependencies" $script:PythonRunner @("-m", "pip", "--isolated", "install", "--requirement", $requirementsFile) 40
    } else {
        Write-Startup "[python_dependencies] 跳过：指纹命中且环境存在"
        $script:PythonDependenciesDetail = "已复用"
    }
}

# uv 路径只作为明确的环境方案返回，不与 Conda 准备结果混用。
function Get-Uv {
    $architecture = $env:PROCESSOR_ARCHITEW6432
    if ([string]::IsNullOrWhiteSpace($architecture)) { $architecture = $env:PROCESSOR_ARCHITECTURE }
    if ([string]::IsNullOrWhiteSpace($architecture)) {
        Fail-Start 21 "uv" "无法识别 Windows 架构" "确认 PROCESSOR_ARCHITECTURE 后重新执行本脚本"
    }
    $runtime = switch ($architecture.ToUpperInvariant()) {
        "AMD64" { [pscustomobject]@{ name = "x64"; asset = "uv-x86_64-pc-windows-msvc.zip" }; break }
        "ARM64" { [pscustomobject]@{ name = "arm64"; asset = "uv-aarch64-pc-windows-msvc.zip" }; break }
        default { $null }
    }
    if ($null -eq $runtime) {
        Fail-Start 21 "uv" "不支持当前 Windows 架构: $architecture" "安装支持的 AMD64/ARM64 Windows 环境后重试"
    }
    $install = Join-Path $script:VarDir ("runtime\uv\0.11.12\{0}" -f $runtime.name)
    Start-WaitIndicator "python-search"
    try {
        $uv = Get-Command uv -ErrorAction SilentlyContinue
        if ($uv) { return $uv.Source }
        foreach ($name in @("uv.exe", "uv.cmd")) {
            $installed = Join-Path $install $name
            if (Test-Path -LiteralPath $installed -PathType Leaf) {
                return (Resolve-Path -LiteralPath $installed).Path
            }
        }
    } finally {
        Stop-WaitIndicator
    }
    $script:DownloadTemp = Join-Path $script:VarDir ("temp\downloads\uv-{0}" -f [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $script:DownloadTemp -Force | Out-Null
    $uvDownloadTemp = $script:DownloadTemp
    Start-WaitIndicator "python-search"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $base = "https://releases.astral.sh/github/uv/releases/download/0.11.12/"
        $zip = Join-Path $script:DownloadTemp $runtime.asset
        $checksum = Join-Path $script:DownloadTemp ("{0}.sha256" -f $runtime.asset)
        Invoke-WebRequest -Uri ($base + $runtime.asset) -OutFile $zip -UseBasicParsing
        Invoke-WebRequest -Uri ($base + ("{0}.sha256" -f $runtime.asset)) -OutFile $checksum -UseBasicParsing
        $expected = ((Get-Content -LiteralPath $checksum -Raw) -split "\s+")[0].Trim().ToLowerInvariant()
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            $actual = ([BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($zip))) -replace "-", "").ToLowerInvariant()
        } finally {
            $sha.Dispose()
        }
        if ($actual -ne $expected) {
            Fail-Start 21 "uv" "uv 下载校验失败" "删除临时下载后检查网络与官方 release 校验文件"
        }
        New-Item -ItemType Directory -Path $install -Force | Out-Null
        Expand-Archive -LiteralPath $zip -DestinationPath $script:DownloadTemp -Force
        $candidate = Get-ChildItem -LiteralPath $script:DownloadTemp -Recurse -File | Where-Object { $_.Name -in @("uv.exe", "uv.cmd") } | Select-Object -First 1
        if (-not $candidate) {
            Fail-Start 21 "uv" "校验后的归档缺少 uv 可执行文件" "删除临时下载后重新执行本脚本"
        }
        $destination = Join-Path $install $candidate.Name
        Copy-Item -LiteralPath $candidate.FullName -Destination $destination -Force
        return (Resolve-Path -LiteralPath $destination).Path
    } catch {
        Fail-Start 21 "uv" ("uv 官方 release 下载或安装失败: " + $_.Exception.Message) "检查网络后重新执行本脚本"
    } finally {
        Stop-WaitIndicator
        if (Test-Path -LiteralPath $uvDownloadTemp) {
            Remove-Item -LiteralPath $uvDownloadTemp -Recurse -Force -ErrorAction SilentlyContinue
        }
        if ($script:DownloadTemp -eq $uvDownloadTemp) { $script:DownloadTemp = $null }
    }
}

# uv 同步保持锁文件语义；失败时不静默改用另一套依赖解析器。
function Setup-Uv([bool]$SkipSync = $false) {
    $script:UvExecutable = Get-Uv
    Start-WaitIndicator "python-verify"
    try {
        $version = (& $script:UvExecutable --version 2>&1 | Out-String).Trim()
        $versionCode = $LASTEXITCODE
    } finally {
        Stop-WaitIndicator
    }
    if ($versionCode -ne 0 -or [string]::IsNullOrWhiteSpace($version)) {
        Fail-Start 21 "uv" "uv 无法执行" "修复 uv 后重新执行本脚本"
    }
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $script:VarDir "runtime\python\env"
    $env:UV_CACHE_DIR = Join-Path $script:VarDir "cache\uv"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $script:VarDir "runtime\python\installations"
    $script:PythonRunner = @($script:UvExecutable, "run", "--locked", "--no-sync", "python", "-B")
    $script:PackageRunner = @($script:UvExecutable, "run", "--locked", "--no-sync", "python", "-B", "-m", "product.backend.cli")
    $script:PythonEnvironmentType = "uv"
    $script:PythonEnvironmentPath = [IO.Path]::GetFullPath($env:UV_PROJECT_ENVIRONMENT)
    $script:UvVersion = $version
    if (-not $SkipSync) {
        Invoke-External "lock" @($script:UvExecutable) @("lock", "--check") 22 (Get-RecoveryCommand)
        Invoke-External "uv-sync" @($script:UvExecutable) @("sync", "--locked", "--all-groups", "--no-install-project") 21
    } else {
        Write-Startup "[python_dependencies] 跳过：指纹命中且 uv 环境存在"
        $script:PythonDependenciesDetail = "已复用"
    }
    Write-Startup "uv=$version"
}

function Get-CommandVersion([string]$Command, [string[]]$Arguments) {
    try {
        $value = (& $Command @Arguments 2>$null | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($value)) { return "unknown" }
        return $value
    } catch { return "unknown" }
}

function Get-PythonVersion([string]$EnvironmentType) {
    Start-WaitIndicator "python-verify"
    try {
        if ($EnvironmentType -eq "Conda") {
            return Get-CommandVersion $script:CondaExecutable @("run", "--no-capture-output", "--name", "jiejian_env", "python", "--version")
        }
        return Get-CommandVersion $script:UvExecutable @("run", "--locked", "--no-sync", "python", "--version")
    } finally {
        Stop-WaitIndicator
    }
}

# 启动后的全部 Python 子进程复用同一个已验证解释器绝对路径。
function Set-PythonRunners {
    if ($script:PythonEnvironmentType -eq "Conda") {
        $script:PythonRunner = @($script:CondaExecutable, "run", "--no-capture-output", "--name", "jiejian_env", "python", "-B")
        $script:PackageRunner = @($script:CondaExecutable, "run", "--no-capture-output", "--name", "jiejian_env", "python", "-B", "-m", "product.backend.cli")
    } else {
        $script:PythonRunner = @($script:UvExecutable, "run", "--locked", "--no-sync", "python", "-B")
        $script:PackageRunner = @($script:UvExecutable, "run", "--locked", "--no-sync", "python", "-B", "-m", "product.backend.cli")
    }
}

# 解析一次真实解释器路径；CLI 子 shell 后续不再重复进入 Conda/uv wrapper。
function Resolve-PythonExecutable {
    $probe = "import os,sys; print(os.path.abspath(sys.executable))"
    $arguments = @()
    if ($script:PythonRunner.Count -gt 1) {
        $arguments = @($script:PythonRunner[1..($script:PythonRunner.Count - 1)])
    }
    $arguments += @("-c", $probe)
    Start-WaitIndicator "python-verify"
    try {
        try {
            $output = (& $script:PythonRunner[0] @arguments 2>$null | Out-String).Trim()
        } catch {
            Fail-Start 40 "python-dependencies" "无法解析 Python 实际可执行文件" (Get-RecoveryCommand)
        }
    } finally {
        Stop-WaitIndicator
    }
    $resolved = ($output -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1).Trim()
    if ([string]::IsNullOrWhiteSpace($resolved)) {
        $resolved = Join-Path $script:PythonEnvironmentPath "python.exe"
    }
    try { $resolved = [IO.Path]::GetFullPath($resolved) } catch { $resolved = $null }
    if ([string]::IsNullOrWhiteSpace($resolved) -or -not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        Fail-Start 40 "python-dependencies" "Python 实际可执行文件不存在" (Get-RecoveryCommand)
    }
    $script:PythonExecutable = $resolved
    $env:JIEJIAN_PYTHON_EXECUTABLE = $script:PythonExecutable
    $env:JIEJIAN_PYTHON_ENVIRONMENT_PATH = $script:PythonEnvironmentPath
    $env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE = $script:PythonEnvironmentType
    $identityProbe = "import json; from product.backend.infra.runtime.environment_identity import require_python_environment; print(json.dumps(require_python_environment(), ensure_ascii=False))"
    $identityArguments = @()
    if ($script:PythonRunner.Count -gt 1) {
        $identityArguments = @($script:PythonRunner[1..($script:PythonRunner.Count - 1)])
    }
    $identityArguments += @("-c", $identityProbe)
    try {
        $identityText = (& $script:PythonRunner[0] @identityArguments 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($identityText)) {
            Fail-Start 40 "python" "Python 环境来源检查失败：$identityText" (Get-RecoveryCommand)
        }
        $script:PythonEnvironmentReport = $identityText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        if ($script:FailureCode -gt 0) { throw }
        Fail-Start 40 "python" ("Python 环境来源检查失败：" + $_.Exception.Message) (Get-RecoveryCommand)
    }
    Write-Startup "Python 实际可执行文件: $script:PythonExecutable"
}

# 运行时探针验证当前仓库导入路径，防止旧 wheel 抢占源码。
function Test-PythonEnvironment {
    if ($null -eq $script:PythonRunner -or $script:PythonRunner.Count -lt 1) { return $false }
    Start-WaitIndicator "python-verify"
    try {
        $probe = "import alembic, fastapi, httpx, playwright, pydantic, sqlalchemy, typer, uvicorn, yaml; from product.backend.cli import main"
        $arguments = @()
        if ($script:PythonRunner.Count -gt 1) {
            $arguments = @($script:PythonRunner[1..($script:PythonRunner.Count - 1)])
        }
        $arguments += @("-c", $probe)
        & $script:PythonRunner[0] @arguments 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
    finally { Stop-WaitIndicator }
}

# 依赖准备按已冻结环境类型分派，不允许在失败后跨方案回退。
function Prepare-PythonDependencies {
    $environmentFile = Join-Path $script:ProjectRoot "environment.yml"
    $pythonFiles = @($environmentFile, (Join-Path $script:ProjectRoot "pyproject.toml"), (Join-Path $script:ProjectRoot "uv.lock"))
    $condaEnvironment = Get-CondaEnvironment
    if ($script:CondaExecutable) {
        $script:PythonEnvironmentType = "Conda"
        $condaVersion = Get-CommandVersion $script:CondaExecutable @("--version")
        $candidatePath = if ($condaEnvironment) { [IO.Path]::GetFullPath($condaEnvironment) } else { "missing" }
        $pythonVersion = Get-PythonVersion "Conda"
        $fingerprint = Get-StageFingerprint $pythonFiles @{
            environment_type = "Conda"
            environment_path = $candidatePath
            conda_version = $condaVersion
            python_version = $pythonVersion
        }
        $environmentReady = $false
        if ($condaEnvironment) {
            $script:PythonEnvironmentPath = $candidatePath
            $script:CondaVersion = $condaVersion
            Set-PythonRunners
            $script:PythonVersion = $pythonVersion
            $environmentReady = Test-PythonEnvironment
        }
        $pythonState = Get-PhaseState "python_dependencies"
        $pythonStateHit = Test-PhaseHit "python_dependencies" $fingerprint
        if ($pythonStateHit -and $environmentReady) {
            $script:PythonFingerprint = $fingerprint
            Write-Startup "[python_dependencies] 跳过：指纹命中且环境探针通过"
            $script:PythonDependenciesDetail = "已复用"
        } elseif ($environmentReady -and $null -eq $pythonState) {
            # jiejian_env 已具备第三方运行依赖时只重建本地准备状态。
            $script:PythonFingerprint = $fingerprint
            Write-Startup "[python_dependencies] 跳过：固定 jiejian_env 环境探针通过"
            $script:PythonDependenciesDetail = "已验证并复用"
            Set-PhaseState "python_dependencies" $script:PythonFingerprint @{
                environment_type = "Conda"
                environment_path = $script:PythonEnvironmentPath
                conda_version = $script:CondaVersion
                python_version = $script:PythonVersion
            }
        } else {
            Write-Startup "[python_dependencies] 执行：固定环境缺失或产品依赖探针失败"
            Setup-Conda $condaEnvironment $true $false
            $script:PythonVersion = Get-PythonVersion "Conda"
            $script:PythonFingerprint = Get-StageFingerprint $pythonFiles @{
                environment_type = "Conda"
                environment_path = $script:PythonEnvironmentPath
                conda_version = $script:CondaVersion
                python_version = $script:PythonVersion
            }
            Set-PhaseState "python_dependencies" $script:PythonFingerprint @{
                environment_type = "Conda"
                environment_path = $script:PythonEnvironmentPath
                conda_version = $script:CondaVersion
                python_version = $script:PythonVersion
            }
        }
    } else {
        $script:UvExecutable = Get-Uv
        $uvVersion = Get-CommandVersion $script:UvExecutable @("--version")
        $script:UvVersion = $uvVersion
        $script:PythonEnvironmentType = "uv"
        $script:PythonEnvironmentPath = [IO.Path]::GetFullPath((Join-Path $script:VarDir "runtime\python\env"))
        $env:UV_PROJECT_ENVIRONMENT = $script:PythonEnvironmentPath
        $env:UV_CACHE_DIR = Join-Path $script:VarDir "cache\uv"
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $script:VarDir "runtime\python\installations"
        $pythonVersion = Get-PythonVersion "uv"
        $fingerprint = Get-StageFingerprint $pythonFiles @{
            environment_type = "uv"
            environment_path = $script:PythonEnvironmentPath
            uv_version = $uvVersion
            python_version = $pythonVersion
        }
        if (Test-PhaseHit "python_dependencies" $fingerprint -and (Test-Path -LiteralPath $script:PythonEnvironmentPath -PathType Container)) {
            $script:PythonFingerprint = $fingerprint
            Set-PythonRunners
            $script:PythonVersion = $pythonVersion
            if (-not (Test-PythonEnvironment)) {
                Write-Startup "[python_dependencies] 执行：缓存命中但 Python 环境探针失败"
                Setup-Uv $false
                $script:PythonVersion = Get-PythonVersion "uv"
                $script:PythonFingerprint = Get-StageFingerprint $pythonFiles @{
                    environment_type = "uv"
                    environment_path = $script:PythonEnvironmentPath
                    uv_version = $script:UvVersion
                    python_version = $script:PythonVersion
                }
                Set-PhaseState "python_dependencies" $script:PythonFingerprint @{
                    environment_type = "uv"
                    environment_path = $script:PythonEnvironmentPath
                    uv_version = $script:UvVersion
                    python_version = $script:PythonVersion
                }
            } else {
                Write-Startup "[python_dependencies] 跳过：指纹命中且 uv 环境存在"
                $script:PythonDependenciesDetail = "已复用"
            }
        } else {
            Setup-Uv $false
            $script:PythonVersion = Get-PythonVersion "uv"
            $script:PythonFingerprint = Get-StageFingerprint $pythonFiles @{
                environment_type = "uv"
                environment_path = $script:PythonEnvironmentPath
                uv_version = $script:UvVersion
                python_version = $script:PythonVersion
            }
            Set-PhaseState "python_dependencies" $script:PythonFingerprint @{
                environment_type = "uv"
                environment_path = $script:PythonEnvironmentPath
                uv_version = $script:UvVersion
                python_version = $script:PythonVersion
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace([string]$script:PythonDependenciesDetail)) {
        $script:PythonDependenciesDetail = "已准备"
    }
    Resolve-PythonExecutable
    return $script:PythonFingerprint
}

# 浏览器探针只验证产品需要的 Chromium，不启动目标检查。
function Test-Chromium {
    $probe = "from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); path=Path(p.chromium.executable_path).resolve(); p.stop(); print(path); raise SystemExit(0 if path.is_file() else 1)"
    Start-WaitIndicator "chromium-check"
    try {
        $arguments = @()
        if ($script:PythonRunner.Count -gt 1) {
            $arguments = @($script:PythonRunner[1..($script:PythonRunner.Count - 1)])
        }
        $arguments += @("-c", $probe)
        $result = (& $script:PythonRunner[0] @arguments 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($result)) { return $false }
        $script:ChromiumExecutable = ($result -split "`r?`n" | Select-Object -Last 1).Trim()
        return Test-Path -LiteralPath $script:ChromiumExecutable -PathType Leaf
    } catch { return $false }
    finally { Stop-WaitIndicator }
}

# Playwright 缓存命中仍需通过可执行探针，指纹本身不能证明浏览器可用。
function Prepare-Playwright([string]$PythonFingerprint) {
    $fingerprint = Get-StageFingerprint @() @{
        python_dependencies = $PythonFingerprint
        platform = $env:OS
        environment_type = $script:PythonEnvironmentType
    }
    $hit = Test-PhaseHit "playwright" $fingerprint
    $chromiumReady = Test-Chromium
    if (-not $chromiumReady) {
        Invoke-Python @("-m", "playwright", "install", "chromium") "playwright" 41
        if (-not (Test-Chromium)) { Fail-Start 41 "playwright" "Chromium 可执行文件探针失败" (Get-RecoveryCommand) }
        $script:ChromiumDetail = "已准备"
        Set-PhaseState "playwright" $fingerprint @{
            python_dependencies = $PythonFingerprint
            platform = $env:OS
            environment_type = $script:PythonEnvironmentType
        }
    } elseif (-not $hit) {
        Write-Startup "[playwright] 跳过：现有 Chromium 探针通过，重建准备状态"
        $script:ChromiumDetail = "已验证并复用"
        Set-PhaseState "playwright" $fingerprint @{
            python_dependencies = $PythonFingerprint
            platform = $env:OS
            environment_type = $script:PythonEnvironmentType
        }
    } else { Write-Startup "[playwright] 跳过：指纹命中且 Chromium 探针通过"; $script:ChromiumDetail = "已复用" }
}
