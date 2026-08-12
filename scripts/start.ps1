#Requires -Version 5.1
# =============================================================================
# Windows 一键启动编排
#
# 定位
#   start.cmd 与界鉴 Python、Playwright、前端运行环境之间的首次准备和启动边界
#
# 职责
#   选择 Conda 或 uv｜执行迁移和环境诊断｜构建前端并启动本地控制面
#
# 调用链
#   start.cmd / user shell → scripts/start.ps1 → package CLI / pnpm / Playwright
# =============================================================================

[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$VarDir = "",
    [switch]$PrepareOnly,
    [switch]$ForcePrepare
)

$ErrorActionPreference = "Stop"
$script:ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($VarDir)) {
    $VarDir = Join-Path $script:ProjectRoot "var"
} elseif (-not [IO.Path]::IsPathRooted($VarDir)) {
    $VarDir = Join-Path $script:ProjectRoot $VarDir
}
$script:VarDir = [IO.Path]::GetFullPath($VarDir)
$script:LogDir = Join-Path $script:VarDir "logs"
$script:StartupDir = Join-Path $script:VarDir "startup"
$script:StatePath = Join-Path $script:StartupDir "prepare-state.json"
$script:LogPath = Join-Path $script:LogDir ("startup-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$script:FailureStage = "startup"
$script:FailureCode = 0
$script:CondaExecutable = $null
$script:UvExecutable = $null
$script:PythonRunner = $null
$script:PackageRunner = $null
$script:PythonEnvironmentType = $null
$script:PythonEnvironmentPath = $null
$script:UvVersion = $null
$script:DownloadTemp = $null
$script:NodeVersion = $null
$script:PnpmVersion = $null
$script:CondaVersion = $null
$script:PythonVersion = $null
$script:PythonFingerprint = $null
$script:NodeDependenciesFingerprint = $null
$script:PrepareState = [pscustomobject]@{
    schema_version = "1"
    phases = [pscustomobject]@{}
}
$script:SavedBytecode = $env:PYTHONDONTWRITEBYTECODE
$script:SavedUvProjectEnvironment = $env:UV_PROJECT_ENVIRONMENT
$script:SavedUvCacheDir = $env:UV_CACHE_DIR
$script:SavedUvPythonInstallDir = $env:UV_PYTHON_INSTALL_DIR
$script:SavedPythonUtf8 = $env:PYTHONUTF8
$script:SavedPythonIoEncoding = $env:PYTHONIOENCODING
$script:OriginalLocation = (Get-Location).Path
$script:DisplayStageName = $null
$script:DisplayStageTimer = $null
$script:DisplayStageSkipped = $false

$script:Utf8Encoding = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
[Console]::InputEncoding = $script:Utf8Encoding
[Console]::OutputEncoding = $script:Utf8Encoding
$OutputEncoding = [Console]::OutputEncoding

function Write-Startup([string]$Message) {
    if (-not (Test-Path -LiteralPath $script:LogDir -PathType Container)) {
        New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null
    }
    [IO.File]::AppendAllText($script:LogPath, $Message + [Environment]::NewLine, $script:Utf8Encoding)
    if ($Message -match '^\[[^]]+\] 跳过') {
        Write-Host ("  {0}" -f $Message) -ForegroundColor DarkCyan
    } elseif ($Message -match '^准备完成') {
        Write-Host $Message -ForegroundColor Cyan
    }
}

function Write-Banner {
    Write-Host ""
    Write-Host "  界鉴 / JIEJIAN" -ForegroundColor Cyan
    Write-Host "  安全意图差分验证与交付门禁" -ForegroundColor Gray
    Write-Host "" -ForegroundColor DarkBlue
}

function Start-DisplayStage([string]$Name) {
    $script:DisplayStageName = $Name
    $script:DisplayStageTimer = [Diagnostics.Stopwatch]::StartNew()
    $script:DisplayStageSkipped = $true
    Write-Host ("[进行中] {0}" -f $Name) -ForegroundColor Blue
}

function Complete-DisplayStage([string]$Status = "") {
    if ($null -eq $script:DisplayStageTimer) { return }
    $script:DisplayStageTimer.Stop()
    if ([string]::IsNullOrWhiteSpace($Status)) { $Status = if ($script:DisplayStageSkipped) { "跳过" } else { "完成" } }
    $color = if ($Status -eq "失败") { "Red" } elseif ($Status -eq "跳过") { "DarkCyan" } else { "Cyan" }
    Write-Host ("[{0}] {1} · {2:N0} ms" -f $Status, $script:DisplayStageName, $script:DisplayStageTimer.Elapsed.TotalMilliseconds) -ForegroundColor $color
    $script:DisplayStageName = $null
    $script:DisplayStageTimer = $null
    $script:DisplayStageSkipped = $false
}

function Get-RecoveryCommand {
    return "powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -ForcePrepare -PrepareOnly -VarDir `"$script:VarDir`""
}

function Load-PrepareState {
    if (-not (Test-Path -LiteralPath $script:StatePath -PathType Leaf)) {
        Write-Startup "准备状态缺失，执行冷准备"
        return
    }
    try {
        $loaded = Get-Content -LiteralPath $script:StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($loaded.schema_version -ne "1" -or $null -eq $loaded.phases) {
            throw "invalid prepare state"
        }
        $script:PrepareState = $loaded
    } catch {
        Write-Startup "准备状态损坏或版本未知，安全执行冷准备"
        Write-Host "准备状态损坏或版本未知，安全执行冷准备" -ForegroundColor DarkCyan
        $script:PrepareState = [pscustomobject]@{
            schema_version = "1"
            phases = [pscustomobject]@{}
        }
    }
}

function Save-PrepareState {
    if (-not (Test-Path -LiteralPath $script:StartupDir -PathType Container)) {
        New-Item -ItemType Directory -Path $script:StartupDir -Force | Out-Null
    }
    $temporary = Join-Path $script:StartupDir ("prepare-state-{0}.tmp" -f [guid]::NewGuid().ToString("N"))
    $json = $script:PrepareState | ConvertTo-Json -Depth 10 -Compress
    [IO.File]::WriteAllText($temporary, $json, $script:Utf8Encoding)
    try {
        if (Test-Path -LiteralPath $script:StatePath -PathType Leaf) {
            $backup = Join-Path $script:StartupDir ("prepare-state-{0}.bak" -f [guid]::NewGuid().ToString("N"))
            [IO.File]::Replace([string]$temporary, [string]$script:StatePath, [string]$backup, $true)
            if (Test-Path -LiteralPath $backup -PathType Leaf) {
                Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
            }
        } else {
            [IO.File]::Move([string]$temporary, [string]$script:StatePath)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-PhaseState([string]$Stage) {
    if ($null -eq $script:PrepareState.phases) { return $null }
    $property = $script:PrepareState.phases.PSObject.Properties[$Stage]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Set-PhaseState([string]$Stage, [string]$Fingerprint, [hashtable]$Facts) {
    $script:DisplayStageSkipped = $false
    $entry = [ordered]@{
        completed = $true
        fingerprint = $Fingerprint
        facts = [pscustomobject]$Facts
    }
    $script:PrepareState.phases | Add-Member -MemberType NoteProperty -Name $Stage -Value ([pscustomobject]$entry) -Force
    Save-PrepareState
}

function Test-PhaseHit([string]$Stage, [string]$Fingerprint) {
    if ($ForcePrepare) { return $false }
    $entry = Get-PhaseState $Stage
    return $null -ne $entry -and $entry.completed -eq $true -and
        -not [string]::IsNullOrWhiteSpace([string]$entry.fingerprint) -and
        $null -ne $entry.facts -and $entry.fingerprint -eq $Fingerprint
}

function Get-FileDigest([string]$Path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try {
            return (([BitConverter]::ToString($sha.ComputeHash($stream))) -replace "-", "").ToLowerInvariant()
        } finally { $stream.Dispose() }
    } finally { $sha.Dispose() }
}

function Get-StageFingerprint([string[]]$Paths, [hashtable]$Facts) {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($path in ($Paths | Sort-Object)) {
        $full = [IO.Path]::GetFullPath($path)
        $relative = if ($full.StartsWith($script:ProjectRoot, [StringComparison]::OrdinalIgnoreCase)) {
            $full.Substring($script:ProjectRoot.Length).TrimStart("\", "/")
        } else { $full }
        if (Test-Path -LiteralPath $full -PathType Leaf) {
            $null = $lines.Add(("file|{0}|{1}" -f $relative.Replace("\", "/"), (Get-FileDigest $full)))
        } elseif (Test-Path -LiteralPath $full -PathType Container) {
            $files = @(Get-ChildItem -LiteralPath $full -Recurse -File | Sort-Object FullName)
            if ($files.Count -eq 0) { $null = $lines.Add(("empty|{0}" -f $relative.Replace("\", "/"))) }
            foreach ($file in $files) {
                $fileRelative = $file.FullName.Substring($script:ProjectRoot.Length).TrimStart("\", "/").Replace("\", "/")
                $null = $lines.Add(("file|{0}|{1}" -f $fileRelative, (Get-FileDigest $file.FullName)))
            }
        } else {
            $null = $lines.Add(("missing|{0}" -f $relative.Replace("\", "/")))
        }
    }
    foreach ($key in ($Facts.Keys | Sort-Object)) {
        $null = $lines.Add(("fact|{0}|{1}" -f $key, [string]$Facts[$key]))
    }
    $bytes = $script:Utf8Encoding.GetBytes(($lines -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (([BitConverter]::ToString($sha.ComputeHash($bytes))) -replace "-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Fail-Start([int]$Code, [string]$Stage, [string]$Diagnostic, [string]$Recovery) {
    $script:FailureStage = $Stage
    $script:FailureCode = $Code
    Write-Startup ("失败阶段: {0}`n诊断: {1}`n恢复命令: {2}`n日志: {3}" -f $Stage, $Diagnostic, $Recovery, $script:LogPath)
    if ($null -ne $script:DisplayStageTimer) { Complete-DisplayStage "失败" }
    Write-Host ("失败阶段: {0}" -f $Stage) -ForegroundColor Red
    Write-Host ("诊断: {0}" -f $Diagnostic) -ForegroundColor Red
    Write-Host ("日志: {0}" -f ([IO.Path]::GetFullPath($script:LogPath))) -ForegroundColor Gray
    Write-Host ("恢复命令: {0}" -f $Recovery) -ForegroundColor Yellow
    Write-Host ("退出码: {0}" -f $Code) -ForegroundColor Red
    exit $Code
}

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
    try {
        $ErrorActionPreference = "Continue"
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
                } |
                Out-Null
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($code -ne 0) {
        if ([string]::IsNullOrWhiteSpace($Recovery)) {
            $Recovery = Get-RecoveryCommand
        }
        Fail-Start $FailureCode $Stage "外部命令返回 $code" $Recovery
    }
}

function Test-NodeAndPnpm {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) {
        Fail-Start 30 "node" "未找到 Node.js；Vite 7 需要 Node 20.19+ 或 22.12+。" "安装 Node.js 官方 LTS 后重新执行本脚本"
    }
    $nodeVersion = (& $node.Source --version 2>$null | Out-String).Trim()
    $nodeMatch = [regex]::Match($nodeVersion, "^v(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)")
    $nodeOk = $false
    if ($nodeMatch.Success) {
        $major = [int]$nodeMatch.Groups["major"].Value
        $minor = [int]$nodeMatch.Groups["minor"].Value
        $nodeOk = (($major -eq 20 -and $minor -ge 19) -or ($major -ge 22 -and ($major -gt 22 -or $minor -ge 12)))
    }
    if ($LASTEXITCODE -ne 0 -or -not $nodeOk) {
        Fail-Start 30 "node" "Node.js 版本不满足 Vite 7 要求: $nodeVersion" "安装 Node.js 官方 LTS 后重新执行本脚本"
    }
    $script:NodeVersion = $nodeVersion
    $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
    if (-not $pnpm) {
        Fail-Start 31 "pnpm" "未找到 pnpm；Node/pnpm 是独立系统前置。" "安装 Node.js 官方 LTS，并执行 corepack enable 或安装 pnpm 后重试"
    }
    $script:PnpmVersion = (& $pnpm.Source --version 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($script:PnpmVersion)) {
        Fail-Start 31 "pnpm" "pnpm 无法执行" "执行 corepack enable 或安装 pnpm 后重试"
    }
    $script:NodeVersion = $nodeVersion
}

function Get-CondaEnvironment {
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
    Write-Startup "已读取 Conda 环境列表"
    $found = @($items | Where-Object { (Split-Path -Leaf ([string]$_)) -eq "jiejian_env" } | Select-Object -First 1)
    if ($found.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace([string]$found[0])) {
        return [string]$found[0]
    }
    return $null
}

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
    $script:PackageRunner = @($script:CondaExecutable, "run", "--no-capture-output", "--name", "jiejian_env", "jiejian")
    if (-not $SkipInstall) {
        Invoke-External "python-dependencies" @($script:CondaExecutable) @("run", "--no-capture-output", "--name", "jiejian_env", "python", "-B", "-m", "pip", "install", "--group", "dev", "--editable", $script:ProjectRoot) 40
    } else {
        Write-Startup "[python_dependencies] 跳过：指纹命中且环境存在"
    }
}

function Get-Uv {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) { return $uv.Source }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        foreach ($name in @("uv.exe", "uv.cmd")) {
            $installed = Join-Path $env:LOCALAPPDATA ("jiejian\bin\{0}" -f $name)
            if (Test-Path -LiteralPath $installed -PathType Leaf) {
                return (Resolve-Path -LiteralPath $installed).Path
            }
        }
    }
    $architecture = $env:PROCESSOR_ARCHITEW6432
    if ([string]::IsNullOrWhiteSpace($architecture)) { $architecture = $env:PROCESSOR_ARCHITECTURE }
    if ([string]::IsNullOrWhiteSpace($architecture)) {
        Fail-Start 21 "uv" "无法识别 Windows 架构" "确认 PROCESSOR_ARCHITECTURE 后重新执行本脚本"
    }
    $asset = switch ($architecture.ToUpperInvariant()) {
        "AMD64" { "uv-x86_64-pc-windows-msvc.zip"; break }
        "ARM64" { "uv-aarch64-pc-windows-msvc.zip"; break }
        default { $null }
    }
    if (-not $asset) {
        Fail-Start 21 "uv" "不支持当前 Windows 架构: $architecture" "安装支持的 AMD64/ARM64 Windows 环境后重试"
    }
    $script:DownloadTemp = Join-Path $script:VarDir ("uv-download-{0}" -f [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $script:DownloadTemp -Force | Out-Null
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $base = "https://releases.astral.sh/github/uv/releases/download/0.11.12/"
        $zip = Join-Path $script:DownloadTemp $asset
        $checksum = Join-Path $script:DownloadTemp "$asset.sha256"
        Invoke-WebRequest -Uri ($base + $asset) -OutFile $zip -UseBasicParsing
        Invoke-WebRequest -Uri ($base + "$asset.sha256") -OutFile $checksum -UseBasicParsing
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
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
            Fail-Start 21 "uv" "缺少 LOCALAPPDATA，无法安装用户级 uv" "恢复 LOCALAPPDATA 后重新执行本脚本"
        }
        $install = Join-Path $env:LOCALAPPDATA "jiejian\bin"
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
    }
}

function Setup-Uv([bool]$SkipSync = $false) {
    $script:UvExecutable = Get-Uv
    $version = (& $script:UvExecutable --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) {
        Fail-Start 21 "uv" "uv 无法执行" "修复 uv 后重新执行本脚本"
    }
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $script:VarDir "envs\uv"
    $env:UV_CACHE_DIR = Join-Path $script:VarDir "cache\uv"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $script:VarDir "python"
    $script:PythonRunner = @($script:UvExecutable, "run", "--locked", "--no-sync", "python", "-B")
    $script:PackageRunner = @($script:UvExecutable, "run", "--locked", "--no-sync", "jiejian")
    $script:PythonEnvironmentType = "uv"
    $script:PythonEnvironmentPath = [IO.Path]::GetFullPath($env:UV_PROJECT_ENVIRONMENT)
    $script:UvVersion = $version
    if (-not $SkipSync) {
        Invoke-External "lock" @($script:UvExecutable) @("lock", "--check") 22 (Get-RecoveryCommand)
        Invoke-External "uv-sync" @($script:UvExecutable) @("sync", "--locked", "--all-groups") 21
    } else {
        Write-Startup "[python_dependencies] 跳过：指纹命中且 uv 环境存在"
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
    if ($EnvironmentType -eq "Conda") {
        return Get-CommandVersion $script:CondaExecutable @("run", "--no-capture-output", "--name", "jiejian_env", "python", "--version")
    }
    return Get-CommandVersion $script:UvExecutable @("run", "--locked", "--no-sync", "python", "--version")
}

function Set-PythonRunners {
    if ($script:PythonEnvironmentType -eq "Conda") {
        $script:PythonRunner = @($script:CondaExecutable, "run", "--no-capture-output", "--name", "jiejian_env", "python", "-B")
        $script:PackageRunner = @($script:CondaExecutable, "run", "--no-capture-output", "--name", "jiejian_env", "jiejian")
    } else {
        $script:PythonRunner = @($script:UvExecutable, "run", "--locked", "--no-sync", "python", "-B")
        $script:PackageRunner = @($script:UvExecutable, "run", "--locked", "--no-sync", "jiejian")
    }
}

function Test-PythonEnvironment {
    if ($null -eq $script:PythonRunner -or $script:PythonRunner.Count -lt 1) { return $false }
    try {
        $arguments = @()
        if ($script:PythonRunner.Count -gt 1) {
            $arguments = @($script:PythonRunner[1..($script:PythonRunner.Count - 1)])
        }
        $arguments += @("--version")
        & $script:PythonRunner[0] @arguments 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

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
        if (Test-PhaseHit "python_dependencies" $fingerprint -and $condaEnvironment) {
            $script:PythonEnvironmentPath = $candidatePath
            $script:CondaVersion = $condaVersion
            Set-PythonRunners
            $script:PythonVersion = $pythonVersion
            if (Test-PythonEnvironment) {
                $script:PythonFingerprint = $fingerprint
                Write-Startup "[python_dependencies] 跳过：指纹命中且环境存在"
            } else {
                Write-Startup "[python_dependencies] 执行：缓存命中但 Python 环境探针失败"
                Setup-Conda $condaEnvironment $false $false
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
            Setup-Conda $condaEnvironment $false $false
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
        $script:PythonEnvironmentPath = [IO.Path]::GetFullPath((Join-Path $script:VarDir "envs\uv"))
        $env:UV_PROJECT_ENVIRONMENT = $script:PythonEnvironmentPath
        $env:UV_CACHE_DIR = Join-Path $script:VarDir "cache\uv"
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $script:VarDir "python"
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
    return $script:PythonFingerprint
}

function Test-Chromium {
    $probe = "from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); path=Path(p.chromium.executable_path); p.stop(); raise SystemExit(0 if path.is_file() else 1)"
    try {
        $arguments = @()
        if ($script:PythonRunner.Count -gt 1) {
            $arguments = @($script:PythonRunner[1..($script:PythonRunner.Count - 1)])
        }
        $arguments += @("-c", $probe)
        & $script:PythonRunner[0] @arguments 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Prepare-Playwright([string]$PythonFingerprint) {
    $fingerprint = Get-StageFingerprint @() @{
        python_dependencies = $PythonFingerprint
        platform = $env:OS
        environment_type = $script:PythonEnvironmentType
    }
    $hit = Test-PhaseHit "playwright" $fingerprint
    if (-not $hit -or -not (Test-Chromium)) {
        Invoke-Python @("-m", "playwright", "install", "chromium") "playwright" 41
        if (-not (Test-Chromium)) { Fail-Start 41 "playwright" "Chromium 可执行文件探针失败" (Get-RecoveryCommand) }
        Set-PhaseState "playwright" $fingerprint @{
            python_dependencies = $PythonFingerprint
            platform = $env:OS
            environment_type = $script:PythonEnvironmentType
        }
    } else { Write-Startup "[playwright] 跳过：指纹命中且 Chromium 探针通过" }
}

function Get-DatabaseRevision([string]$DatabasePath) {
    if (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) { return "missing" }
    $code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print((c.execute('select version_num from alembic_version').fetchone() or ['missing'])[0]); c.close()"
    try {
        $result = (& $script:PythonRunner[0] @($script:PythonRunner[1..($script:PythonRunner.Count - 1)] + @("-c", $code, $DatabasePath)) 2>$null | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($result)) { return "unknown" }
        return $result.Split("`n")[-1].Trim()
    } catch { return "unknown" }
}

function Prepare-Migration {
    $database = Join-Path $script:VarDir "jiejian.db"
    $migrationFiles = @((Join-Path $script:ProjectRoot "backend\alembic.ini"), (Join-Path $script:ProjectRoot "backend\migrations"))
    $fingerprint = Get-StageFingerprint $migrationFiles @{ database_path = [IO.Path]::GetFullPath($database) }
    $entry = Get-PhaseState "migration"
    $current = Get-DatabaseRevision $database
    $validCurrent = -not [string]::IsNullOrWhiteSpace([string]$current) -and $current -notin @("missing", "unknown")
    if ((Test-PhaseHit "migration" $fingerprint) -and $validCurrent -and (Test-Path -LiteralPath $database -PathType Leaf) -and $null -ne $entry.facts -and $entry.facts.revision -eq $current) {
        Write-Startup "[migration] 跳过：指纹命中且数据库 revision=$current"
        return
    }
    Invoke-Python @("-c", "import sys; from pathlib import Path; from jiejian.storage import default_database_path, upgrade_database; upgrade_database(default_database_path(Path(sys.argv[1])))", $script:VarDir) "migration" 43
    $revision = Get-DatabaseRevision $database
    if ([string]::IsNullOrWhiteSpace([string]$revision) -or $revision -in @("missing", "unknown")) {
        Fail-Start 43 "migration" "迁移完成后未能读取有效 Alembic revision" (Get-RecoveryCommand)
    }
    Set-PhaseState "migration" $fingerprint @{ database_path = [IO.Path]::GetFullPath($database); revision = $revision }
}

function Prepare-Frontend {
    $pnpm = (Get-Command pnpm).Source
    $frontend = Join-Path $script:ProjectRoot "frontend"
    $nodeFiles = @((Join-Path $frontend "package.json"), (Join-Path $frontend "pnpm-lock.yaml"))
    $nodeFingerprint = Get-StageFingerprint $nodeFiles @{ node_version = $script:NodeVersion; pnpm_version = $script:PnpmVersion }
    $script:NodeDependenciesFingerprint = $nodeFingerprint
    $nodeModules = Join-Path $frontend "node_modules"
    $nodeDependenciesRebuilt = $false
    if (-not (Test-PhaseHit "node_dependencies" $nodeFingerprint) -or -not (Test-Path -LiteralPath $nodeModules -PathType Container)) {
        Push-Location -LiteralPath $frontend
        try { Invoke-External "frontend-install" @($pnpm) @("install", "--frozen-lockfile") 44 } finally { Pop-Location }
        Set-PhaseState "node_dependencies" $nodeFingerprint @{ node_version = $script:NodeVersion; pnpm_version = $script:PnpmVersion }
        $nodeDependenciesRebuilt = $true
    } else { Write-Startup "[node_dependencies] 跳过：指纹命中且 node_modules 存在" }
    $buildFiles = @((Join-Path $frontend "src"), (Join-Path $frontend "index.html"), (Join-Path $frontend "package.json"), (Join-Path $frontend "pnpm-lock.yaml")) + @(Get-ChildItem -LiteralPath $frontend -File | Where-Object { $_.Name -like "tsconfig*.json" -or $_.Name -like "vite.config.*" } | Select-Object -ExpandProperty FullName)
    $buildFingerprint = Get-StageFingerprint $buildFiles @{ node_dependencies = $nodeFingerprint }
    $index = Join-Path $frontend "dist\index.html"
    if ($nodeDependenciesRebuilt -or -not (Test-PhaseHit "frontend_build" $buildFingerprint) -or -not (Test-Path -LiteralPath $index -PathType Leaf)) {
        Push-Location -LiteralPath $frontend
        try { Invoke-External "frontend-build" @($pnpm) @("build") 44 } finally { Pop-Location }
        if (-not (Test-Path -LiteralPath $index -PathType Leaf)) { Fail-Start 44 "frontend-build" "构建未生成 dist/index.html" (Get-RecoveryCommand) }
        Set-PhaseState "frontend_build" $buildFingerprint @{ node_dependencies = $nodeFingerprint }
    } else { Write-Startup "[frontend_build] 跳过：指纹命中且 dist/index.html 存在" }
}

function Write-PythonEnvironment {
    Write-Startup ("Python 环境: {0}`nPython 环境路径: {1}" -f $script:PythonEnvironmentType, $script:PythonEnvironmentPath)
    Write-Host ("Python 环境: {0}" -f $script:PythonEnvironmentType) -ForegroundColor Gray
    Write-Host ("Python 环境路径: {0}" -f $script:PythonEnvironmentPath) -ForegroundColor Gray
    if ($script:PythonEnvironmentType -eq "Conda") {
        Write-Startup "后续 CLI 用法: conda run --no-capture-output --name jiejian_env jiejian <命令>"
    } else {
        Write-Startup ("uv 版本: {0}`n后续 CLI 用法: & `"{1}`" run --locked --no-sync jiejian <命令>" -f $script:UvVersion, $script:UvExecutable)
        Write-Host ("uv 版本: {0}" -f $script:UvVersion) -ForegroundColor Gray
    }
}

function Invoke-Python([object[]]$Arguments, [string]$Stage, [int]$Code = 40) {
    Invoke-External $Stage $script:PythonRunner $Arguments $Code
}

function Invoke-Package([object[]]$Arguments, [string]$Stage, [int]$Code = 50) {
    Invoke-External $Stage $script:PackageRunner $Arguments $Code
}

function Write-Stage([string]$Stage, [string]$Message) {
    Write-Startup (">>> [{0}] {1}" -f $Stage, $Message)
}

function Get-StageFailureCode([string]$Stage) {
    switch ($Stage) {
        "conda" { return 20 }
        "uv" { return 21 }
        "lock" { return 22 }
        "node" { return 30 }
        "pnpm" { return 31 }
        "playwright" { return 41 }
        "doctor" { return 42 }
        "migration" { return 43 }
        "frontend-install" { return 44 }
        "frontend-build" { return 44 }
        "serve" { return 50 }
        default { return 40 }
    }
}

try {
    # --- 阶段：建立临时环境并完成运行前探针 ---
    Set-Location -LiteralPath $script:ProjectRoot
    Write-Banner
    Write-Host "项目根: $script:ProjectRoot"
    Write-Host "运行目录: $script:VarDir"
    Write-Host "模式: $(if($PrepareOnly){'PrepareOnly'}else{'serve'})$(if($ForcePrepare){' + ForcePrepare'}else{''})"
    Write-Host "日志: $script:LogPath"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    Start-DisplayStage "预检"
    Write-Stage "preflight" "检查 Node.js 与 pnpm"
    Test-NodeAndPnpm
    New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null
    Load-PrepareState
    Write-Startup "项目根: $script:ProjectRoot`n运行目录: $script:VarDir`n模式: $(if($PrepareOnly){'PrepareOnly'}else{'serve'})`n日志: $script:LogPath`nNode=$script:NodeVersion pnpm=$script:PnpmVersion"
    Complete-DisplayStage "完成"
    # --- 阶段：选择 Python 环境并准备受锁定依赖 ---
    Start-DisplayStage "环境"
    Write-Stage "python" "选择并准备 Python 环境"
    $pythonFingerprint = Prepare-PythonDependencies
    $criticalFacts = @{
        powershell = $PSVersionTable.PSVersion.ToString()
        python = $script:PythonVersion
        node = $script:NodeVersion
        pnpm = $script:PnpmVersion
        environment_type = $script:PythonEnvironmentType
        environment_path = $script:PythonEnvironmentPath
        conda_version = $script:CondaVersion
        uv_version = $script:UvVersion
    }
    $criticalFingerprint = Get-StageFingerprint @() $criticalFacts
    if (Test-PhaseHit "critical_runtime" $criticalFingerprint) {
        Write-Startup "[critical_runtime] 跳过：运行时身份指纹命中"
    } else {
        Set-PhaseState "critical_runtime" $criticalFingerprint $criticalFacts
    }
    Write-PythonEnvironment
    Complete-DisplayStage
    Start-DisplayStage "浏览器"
    Write-Stage "playwright" "安装或校验 Chromium"
    Prepare-Playwright $pythonFingerprint
    Complete-DisplayStage
    # --- 阶段：诊断、迁移并构建前端资源 ---
    Start-DisplayStage "数据"
    Write-Stage "doctor" "运行环境诊断"
    Invoke-Package @("--var-dir", $script:VarDir, "doctor", "--json") "doctor" 42
    Write-Stage "migration" "升级 VarDir 数据库"
    Prepare-Migration
    Complete-DisplayStage
    Start-DisplayStage "界面"
    Write-Stage "frontend" "按指纹安装并构建前端"
    Prepare-Frontend
    Complete-DisplayStage "完成"
    Start-DisplayStage "启动"
    if ($PrepareOnly) {
        Write-Startup "准备完成: $script:VarDir"
        $script:DisplayStageSkipped = $false
        Complete-DisplayStage
        exit 0
    }
    # --- 阶段：把控制权交给正式 serve 入口 ---
    Invoke-Package @("--var-dir", $script:VarDir, "serve", "--open") "serve" 50
    Complete-DisplayStage
    exit 0
} catch {
    if ($script:FailureCode -gt 0) {
        exit $script:FailureCode
    }
    Fail-Start (Get-StageFailureCode $script:FailureStage) $script:FailureStage ("启动编排失败: " + $_.Exception.Message) (Get-RecoveryCommand)
} finally {
    # --- 阶段：恢复调用者环境并精确清理本轮临时资源 ---
    if ($script:DownloadTemp -and (Test-Path -LiteralPath $script:DownloadTemp)) {
        Remove-Item -LiteralPath $script:DownloadTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($null -eq $script:SavedBytecode) { Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue } else { $env:PYTHONDONTWRITEBYTECODE = $script:SavedBytecode }
    if ($null -eq $script:SavedUvProjectEnvironment) { Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue } else { $env:UV_PROJECT_ENVIRONMENT = $script:SavedUvProjectEnvironment }
    if ($null -eq $script:SavedUvCacheDir) { Remove-Item Env:UV_CACHE_DIR -ErrorAction SilentlyContinue } else { $env:UV_CACHE_DIR = $script:SavedUvCacheDir }
    if ($null -eq $script:SavedUvPythonInstallDir) { Remove-Item Env:UV_PYTHON_INSTALL_DIR -ErrorAction SilentlyContinue } else { $env:UV_PYTHON_INSTALL_DIR = $script:SavedUvPythonInstallDir }
    if ($null -eq $script:SavedPythonUtf8) { Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue } else { $env:PYTHONUTF8 = $script:SavedPythonUtf8 }
    if ($null -eq $script:SavedPythonIoEncoding) { Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue } else { $env:PYTHONIOENCODING = $script:SavedPythonIoEncoding }
    Set-Location -LiteralPath $script:OriginalLocation
}
