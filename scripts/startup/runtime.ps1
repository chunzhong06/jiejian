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
# 统一终止启动：记录可恢复诊断，并用稳定退出码结束当前脚本。
function Fail-Start([int]$Code, [string]$Stage, [string]$Diagnostic, [string]$Recovery) {
    $script:FailureStage = $Stage
    $script:FailureCode = $Code
    Write-Startup ("失败阶段: {0}`n诊断: {1}`n恢复命令: {2}`n日志: {3}" -f $Stage, $Diagnostic, $Recovery, $script:LogPath)
    if ($null -ne $script:DisplayStageTimer) { Complete-DisplayStage "失败" }
    $cross = if ($script:DisplayUnicode) { "×" } else { "FAILED" }
    $branch = if ($script:DisplayUnicode) { "  └─" } else { "  `--" }
    $displayCode = "STARTUP_" + (($Stage -replace '[^a-zA-Z0-9]+', '_').Trim('_').ToUpperInvariant())
    Write-Host ""
    Write-Host ("{0} 启动未完成" -f $cross) -ForegroundColor Red
    Write-Host ""
    Write-Host "  失败阶段" -ForegroundColor Red
    Write-Host ("{0} {1}" -f $branch, $Stage) -ForegroundColor Red
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
    Wait-StartupFailureInput
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

# 前端工具链必须同时满足版本和可执行性，避免构建阶段才暴露环境漂移。
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

# 只识别环境声明指定的 Conda 名称，不根据 PATH 猜测任意 Python。
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
        $requirementsFile = Join-Path $script:VarDir "cache\python-dependencies.txt"
        [IO.Directory]::CreateDirectory((Split-Path -Parent $requirementsFile)) | Out-Null
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllLines($requirementsFile, [string[]]$requirements, $utf8NoBom)
        Invoke-External "python-dependencies" $script:PythonRunner @("-m", "pip", "--isolated", "install", "--requirement", $requirementsFile) 40
    } else {
        Write-Startup "[python_dependencies] 跳过：指纹命中且环境存在"
        Write-DisplaySubtask "已复用 Python 依赖缓存" $true
    }
}

# uv 路径只作为明确的环境方案返回，不与 Conda 准备结果混用。
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

# uv 同步保持锁文件语义；失败时不静默改用另一套依赖解析器。
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
    $script:PackageRunner = @($script:UvExecutable, "run", "--locked", "--no-sync", "python", "-B", "-m", "product.backend.cli")
    $script:PythonEnvironmentType = "uv"
    $script:PythonEnvironmentPath = [IO.Path]::GetFullPath($env:UV_PROJECT_ENVIRONMENT)
    $script:UvVersion = $version
    if (-not $SkipSync) {
        Invoke-External "lock" @($script:UvExecutable) @("lock", "--check") 22 (Get-RecoveryCommand)
        Invoke-External "uv-sync" @($script:UvExecutable) @("sync", "--locked", "--all-groups", "--no-install-project") 21
    } else {
        Write-Startup "[python_dependencies] 跳过：指纹命中且 uv 环境存在"
        Write-DisplaySubtask "已复用 Python 依赖缓存" $true
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

# 运行时探针验证当前仓库导入路径，防止旧 wheel 抢占源码。
function Test-PythonEnvironment {
    if ($null -eq $script:PythonRunner -or $script:PythonRunner.Count -lt 1) { return $false }
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
            Write-DisplaySubtask "已复用 Python 依赖缓存" $true
        } elseif ($environmentReady -and $null -eq $pythonState) {
            # jiejian_env 已具备第三方运行依赖时只重建本地准备状态。
            $script:PythonFingerprint = $fingerprint
            Write-Startup "[python_dependencies] 跳过：固定 jiejian_env 环境探针通过"
            Write-DisplaySubtask "已验证并复用 jiejian_env" $true
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
                Write-DisplaySubtask "已复用 Python 依赖缓存" $true
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

# 浏览器探针只验证产品需要的 Chromium，不启动目标检查。
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
        Set-PhaseState "playwright" $fingerprint @{
            python_dependencies = $PythonFingerprint
            platform = $env:OS
            environment_type = $script:PythonEnvironmentType
        }
    } elseif (-not $hit) {
        Write-Startup "[playwright] 跳过：现有 Chromium 探针通过，重建准备状态"
        Write-DisplaySubtask "已验证并复用浏览器缓存" $true
        Set-PhaseState "playwright" $fingerprint @{
            python_dependencies = $PythonFingerprint
            platform = $env:OS
            environment_type = $script:PythonEnvironmentType
        }
    } else { Write-Startup "[playwright] 跳过：指纹命中且 Chromium 探针通过"; Write-DisplaySubtask "已复用浏览器缓存" $true }
}
