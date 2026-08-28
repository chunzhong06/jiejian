# 界鉴开发总控台 Python、Conda、uv、editable 同步与开发身份职责。

function Get-ProjectPackageTopologyInputs {
    $paths = New-Object System.Collections.Generic.List[string]
    # Hatch editable 会冻结包发现结果；包目录新增、删除或移动时必须重新同步。
    foreach ($relativeRoot in @("product\backend", "product\protocols")) {
        $root = Join-Path $script:ProjectRoot $relativeRoot
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        foreach ($packageMarker in (Get-ChildItem -LiteralPath $root -Recurse -Filter "__init__.py" -File)) {
            $null = $paths.Add($packageMarker.FullName)
        }
    }
    return @($paths)
}

function Get-ProjectSyncInputs {
    return @(
        (Join-Path $script:ProjectRoot "pyproject.toml")
        (Join-Path $script:ProjectRoot "uv.lock")
    )
}

function Resolve-CondaPrefix([bool]$RequireExisting) {
    $command = Get-Command conda -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        Fail-Development "conda" "未找到 Conda" "安装或修复 Miniconda/Conda 后执行 scripts/dev.ps1 bootstrap"
    }
    $script:Conda = $command.Source
    $raw = & $script:Conda env list --json 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { Fail-Development "conda" "无法读取 Conda 环境列表" "修复 Conda 后重试" }
    try { $environments = @(($raw | ConvertFrom-Json).envs) }
    catch { Fail-Development "conda" "Conda 环境列表不是有效 JSON" "修复 Conda 后重试" }
    $prefix = $environments | Where-Object { (Split-Path -Leaf ([string]$_)) -eq "jiejian_env" } | Select-Object -First 1
    if ($RequireExisting -and [string]::IsNullOrWhiteSpace([string]$prefix)) {
        Fail-Development "conda" "尚未创建 jiejian_env" "执行 .\scripts\dev.ps1 bootstrap"
    }
    return [string]$prefix
}

function Test-CondaPython([string]$Prefix) {
    if ([string]::IsNullOrWhiteSpace($Prefix)) { return $false }
    $python = Join-Path $Prefix "python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { return $false }
    # Python 基线探针不加载 site；项目依赖半同步时仍应由后续 uv sync 自动修复。
    & $python -S -B -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" 2>$null
    return $LASTEXITCODE -eq 0
}

function Ensure-Conda([ValidateSet("auto", "force", "existing")][string]$Mode) {
    $prefix = Resolve-CondaPrefix ($Mode -eq "existing")
    $environmentDigest = Get-FileDigest $script:EnvironmentPath
    $stateDigest = [string](Get-StateValue "environment_digest")
    $ready = Test-CondaPython $prefix
    $mustUpdate = $Mode -eq "force" -or -not $ready -or $stateDigest -ne $environmentDigest
    if ($Mode -eq "existing" -and $mustUpdate) {
        Fail-Development "conda" "environment.yml 已变化或 Python 基线探针失败" "执行 .\scripts\dev.ps1 bootstrap"
    }
    if ([string]::IsNullOrWhiteSpace($prefix)) {
        Write-Host "正在创建 jiejian_env Python 基线……" -ForegroundColor Cyan
        Invoke-External "conda" @($script:Conda, "env", "create", "--file", $script:EnvironmentPath)
        $prefix = Resolve-CondaPrefix $true
    } elseif ($mustUpdate -and $Mode -ne "existing") {
        Write-Host "正在更新 jiejian_env Python 基线……" -ForegroundColor Cyan
        Invoke-External "conda" @($script:Conda, "env", "update", "--name", "jiejian_env", "--file", $script:EnvironmentPath, "--prune")
        $prefix = Resolve-CondaPrefix $true
    } elseif (-not $ready) {
        Fail-Development "conda" "jiejian_env 的 Python 基线不符合 3.13" "执行 .\scripts\dev.ps1 bootstrap"
    }
    if (-not (Test-CondaPython $prefix)) {
        Fail-Development "conda" "Conda 更新后仍未获得 CPython 3.13" "检查 environment.yml 与 Conda 输出"
    }
    $script:CondaPrefix = [IO.Path]::GetFullPath($prefix)
    $script:Python = Join-Path $script:CondaPrefix "python.exe"
    Set-StateValue "environment_digest" $environmentDigest
}

function Resolve-Uv($Toolchain) {
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    $key = switch ($architecture.ToUpperInvariant()) { "AMD64" { "x64" } "ARM64" { "arm64" } default { $null } }
    if ($null -eq $key) { Fail-Development "uv" "当前 Windows 架构不受支持" "使用 AMD64 或 ARM64 Windows" }
    $metadata = $Toolchain.uv.windows.$key
    $version = [string]$Toolchain.uv.version
    $install = Join-Path $script:DevelopmentRoot ("tools\uv\{0}\{1}" -f $version, $key)
    $executable = Join-Path $install "uv.exe"
    $receipt = Join-Path $install "receipt.json"
    $healthy = $false
    if ((Test-Path -LiteralPath $executable -PathType Leaf) -and (Test-Path -LiteralPath $receipt -PathType Leaf)) {
        try {
            $record = Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
            $healthy = $record.archive_sha256 -eq [string]$metadata.sha256 -and $record.executable_sha256 -eq (Get-FileDigest $executable)
        } catch { $healthy = $false }
    }
    if (-not $healthy) {
        New-Item -ItemType Directory -Path $install -Force | Out-Null
        $downloadRoot = Join-Path $script:DevelopmentRoot ("temp\uv-{0}" -f [guid]::NewGuid().ToString("N"))
        $partial = Join-Path $script:DevelopmentRoot ("cache\downloads\.tmp-{0}-{1}" -f [guid]::NewGuid().ToString("N"), [string]$metadata.asset)
        New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
        New-Item -ItemType Directory -Path (Split-Path -Parent $partial) -Force | Out-Null
        try {
            $uri = "https://github.com/astral-sh/uv/releases/download/{0}/{1}" -f $version, [string]$metadata.asset
            Invoke-WebRequest -Uri $uri -OutFile $partial -UseBasicParsing
            if ((Get-FileDigest $partial) -ne [string]$metadata.sha256) { Fail-Development "uv" "uv 归档 SHA-256 校验失败" "删除 var/development/cache/downloads 中对应临时文件后重试" }
            Expand-Archive -LiteralPath $partial -DestinationPath $downloadRoot -Force
            $candidate = Get-ChildItem -LiteralPath $downloadRoot -Recurse -Filter "uv.exe" -File | Select-Object -First 1
            if ($null -eq $candidate) { Fail-Development "uv" "uv 归档缺少可执行文件" "重新下载固定 uv 归档" }
            Copy-Item -LiteralPath $candidate.FullName -Destination $executable -Force
            $payload = [ordered]@{ schema_version = "1"; version = $version; archive_sha256 = [string]$metadata.sha256; executable_sha256 = Get-FileDigest $executable }
            [IO.File]::WriteAllText($receipt, ($payload | ConvertTo-Json -Compress), $script:Utf8NoBom)
        } finally {
            Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    $actual = (& $executable --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -notmatch ("^uv\s+" + [regex]::Escape($version) + "(\s|$)")) { Fail-Development "uv" "受控 uv 版本不符合工具链清单" "执行 .\scripts\dev.ps1 bootstrap 重建运行时" }
    $script:Uv = [IO.Path]::GetFullPath($executable)
    $script:UvVersion = $version
}

function Set-DevelopmentEnvironment {
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONNOUSERSITE = "1"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    $env:UV_PROJECT_ENVIRONMENT = $script:CondaPrefix
    $env:UV_CACHE_DIR = Join-Path $script:DevelopmentRoot "cache\uv"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $script:DevelopmentRoot "tools\python\installations"
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $script:DevelopmentRoot "tools\playwright"
    $env:JIEJIAN_VAR_DIR = $script:VarDir
    $env:JIEJIAN_PROJECT_ROOT = $script:ProjectRoot
    $env:JIEJIAN_RUNTIME_MODE = "development"
    $env:JIEJIAN_PYTHON_EXECUTABLE = $script:Python
    $env:JIEJIAN_PYTHON_ENVIRONMENT_PATH = $script:CondaPrefix
    $env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE = "conda"
    $env:JIEJIAN_UV_EXECUTABLE = $script:Uv
    $env:JIEJIAN_UV_VERSION = $script:UvVersion
    $env:JIEJIAN_TOOLCHAIN_MANIFEST = $script:ToolchainPath
}

function Read-DevelopmentIdentity {
    $processEnvironment = [Environment]::GetEnvironmentVariables("Process")
    $hadFingerprint = $processEnvironment.Contains("JIEJIAN_RUNTIME_FINGERPRINT")
    $savedFingerprint = if ($hadFingerprint) { [string]$processEnvironment["JIEJIAN_RUNTIME_FINGERPRINT"] } else { $null }
    try {
        # 重新计算身份时不能拿旧指纹自证，但读取动作也不能删除已经确认的父进程身份。
        Remove-Item Env:JIEJIAN_RUNTIME_FINGERPRINT -ErrorAction SilentlyContinue
        $probe = "import json; from product.backend.infra.runtime.process.identity import python_environment_report; print(json.dumps(python_environment_report(), ensure_ascii=False))"
        $raw = (& $script:Python -B -c $probe 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return $null }
        try { return $raw | ConvertFrom-Json } catch { return $null }
    } finally {
        if ($hadFingerprint) { [Environment]::SetEnvironmentVariable("JIEJIAN_RUNTIME_FINGERPRINT", $savedFingerprint, "Process") }
        else { Remove-Item Env:JIEJIAN_RUNTIME_FINGERPRINT -ErrorAction SilentlyContinue }
    }
}

function Confirm-DevelopmentIdentity {
    $report = Read-DevelopmentIdentity
    if ($null -eq $report) { Fail-Development "python-identity" "无法读取 Python 环境身份" "执行 .\scripts\dev.ps1 sync" }
    if (-not $report.ok) { Fail-Development "python-identity" ("Python 环境来源异常：" + (@($report.issues) -join "；")) "执行 .\scripts\dev.ps1 bootstrap" }
    $env:JIEJIAN_RUNTIME_FINGERPRINT = [string]$report.runtime_fingerprint
    & $script:Python -B -c "from product.backend.infra.runtime.process.identity import require_python_environment; require_python_environment()" 2>$null
    if ($LASTEXITCODE -ne 0) { Fail-Development "python-identity" "主进程环境指纹复核失败" "执行 .\scripts\dev.ps1 sync" }
    Set-StateValue "runtime_fingerprint" $env:JIEJIAN_RUNTIME_FINGERPRINT
}

function Sync-Project([bool]$ForceSync) {
    $syncDigest = Get-CombinedDigest @(Get-ProjectSyncInputs)
    $topologyDigest = Get-PathSetDigest @(Get-ProjectPackageTopologyInputs)
    Push-Location -LiteralPath $script:ProjectRoot
    try {
        Invoke-External "uv-lock" @($script:Uv, "lock", "--check")
        $stateDigest = [string](Get-StateValue "sync_digest")
        $stateTopologyDigest = [string](Get-StateValue "package_topology_digest")
        $identity = if ($stateDigest -eq $syncDigest) { Read-DevelopmentIdentity } else { $null }
        if ($ForceSync -or $stateDigest -ne $syncDigest -or $stateTopologyDigest -ne $topologyDigest -or $null -eq $identity -or -not $identity.ok) {
            Write-Host "正在按 uv.lock 精确同步项目依赖……" -ForegroundColor Cyan
            $syncArguments = @($script:Uv, "sync", "--frozen", "--all-groups")
            if ($ForceSync -or $stateTopologyDigest -ne $topologyDigest -or $null -eq $identity -or -not $identity.ok) { $syncArguments += @("--reinstall-package", "jiejian") }
            Invoke-External "uv-sync" $syncArguments
            Set-StateValue "sync_digest" $syncDigest
            Set-StateValue "package_topology_digest" $topologyDigest
        } else { Write-Host "Python 依赖指纹未变化，复用 jiejian_env。" -ForegroundColor DarkGray }
    } finally { Pop-Location }
    Confirm-DevelopmentIdentity
    Save-State
}

function Prepare-Python([ValidateSet("auto", "bootstrap", "sync")][string]$Mode) {
    Write-PrepareStatus "toolchain" "start"
    $toolchain = Read-Toolchain
    Resolve-Uv $toolchain
    Write-PrepareStatus "toolchain" "done"
    Write-PrepareStatus "python" "start"
    if ($Mode -eq "bootstrap") { Ensure-Conda "force" } elseif ($Mode -eq "sync") { Ensure-Conda "existing" } else { Ensure-Conda "auto" }
    Set-DevelopmentEnvironment
    Sync-Project ($Mode -in @("bootstrap", "sync"))
    Write-PrepareStatus "python" "done"
    return $toolchain
}

function Invoke-Update {
    $toolchain = Read-Toolchain
    Ensure-Conda "auto"
    Resolve-Uv $toolchain
    Set-DevelopmentEnvironment
    Push-Location -LiteralPath $script:ProjectRoot
    try {
        Invoke-External "uv-update" (@($script:Uv, "lock") + $CommandArguments)
        Invoke-External "uv-sync" @($script:Uv, "sync", "--frozen", "--all-groups", "--reinstall-package", "jiejian")
    } finally { Pop-Location }
    Set-StateValue "sync_digest" (Get-CombinedDigest @(Get-ProjectSyncInputs))
    Set-StateValue "package_topology_digest" (Get-PathSetDigest @(Get-ProjectPackageTopologyInputs))
    Confirm-DevelopmentIdentity
    Save-State
}

function Resolve-DocsPython {
    $prefix = Resolve-CondaPrefix $true
    if (-not (Test-CondaPython $prefix)) { Fail-Development "docs" "jiejian_env 不是符合要求的 CPython 3.13" "执行 .\scripts\dev.ps1 bootstrap" }
    return [IO.Path]::GetFullPath((Join-Path $prefix "python.exe"))
}
