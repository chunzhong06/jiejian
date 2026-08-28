# 界鉴开发总控台共享失败、锁、状态、摘要与调用者环境恢复边界。

function Fail-Development([string]$Stage, [string]$Message, [string]$Recovery) {
    Write-Host ""
    Write-Host ("开发环境失败：{0}" -f $Stage) -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    Write-Host ("建议：{0}" -f $Recovery) -ForegroundColor Yellow
    throw $Message
}

function Invoke-External([string]$Stage, [string[]]$Invocation) {
    if ($Invocation.Count -lt 1) { Fail-Development $Stage "缺少外部命令" "检查开发脚本参数" }
    $executable = $Invocation[0]
    [string[]]$arguments = if ($Invocation.Count -gt 1) { @($Invocation[1..($Invocation.Count - 1)]) } else { @() }
    & $executable @arguments
    if ($LASTEXITCODE -ne 0) {
        Fail-Development $Stage ("外部命令返回 {0}" -f $LASTEXITCODE) "修复上方错误后重试同一命令"
    }
}

# prepare 子进程只输出固定机器标记；路径、秘密和外部命令正文继续留在日志边界。
function Write-PrepareStatus(
    [ValidateSet("toolchain", "python", "browser", "frontend-dependencies", "frontend-build", "database")][string]$Token,
    [ValidateSet("start", "done")][string]$State
) {
    [Console]::Out.WriteLine(("__JIEJIAN_PREPARE_STATUS__:{0}:{1}" -f $Token, $State))
}

function Get-FileDigest([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-CombinedDigest([string[]]$Paths) {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($path in ($Paths | Sort-Object)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $null = $lines.Add(("{0}|{1}" -f [IO.Path]::GetFullPath($path), (Get-FileDigest $path)))
        }
    }
    $bytes = $script:Utf8NoBom.GetBytes(($lines -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Get-PathSetDigest([string[]]$Paths) {
    $lines = @(
        $Paths |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            ForEach-Object { [IO.Path]::GetFullPath($_) } |
            Sort-Object
    )
    $bytes = $script:Utf8NoBom.GetBytes(($lines -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Enter-PrepareLock {
    # 锁与它保护的 Conda、uv、浏览器及前端工具同属共享开发环境，不能按产品实例分裂。
    $lockPath = Join-Path $script:DevelopmentRoot "locks\prepare.lock"
    New-Item -ItemType Directory -Path (Split-Path -Parent $lockPath) -Force | Out-Null
    try {
        $script:PrepareLock = [IO.File]::Open(
            $lockPath,
            [IO.FileMode]::OpenOrCreate,
            [IO.FileAccess]::ReadWrite,
            [IO.FileShare]::None
        )
    } catch [IO.IOException] {
        Fail-Development "prepare-lock" "另一个界鉴准备进程正在修改运行环境" "等待另一进程完成后重试"
    }
}

function Exit-PrepareLock {
    if ($null -ne $script:PrepareLock) {
        $script:PrepareLock.Dispose()
        $script:PrepareLock = $null
    }
}

function Read-State {
    if (-not (Test-Path -LiteralPath $script:StatePath -PathType Leaf)) { return }
    try {
        $value = Get-Content -LiteralPath $script:StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($value.schema_version -eq "1") { $script:State = $value }
    } catch {
        $script:State = [pscustomobject]@{ schema_version = "1" }
    }
}

function Get-StateValue([string]$Name) {
    $property = $script:State.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Set-StateValue([string]$Name, [object]$Value) {
    $script:State | Add-Member -MemberType NoteProperty -Name $Name -Value $Value -Force
}

function Save-State {
    $directory = Split-Path -Parent $script:StatePath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = Join-Path $directory ("development-state-{0}.tmp" -f [guid]::NewGuid().ToString("N"))
    $backup = Join-Path $directory ("development-state-{0}.bak" -f [guid]::NewGuid().ToString("N"))
    [IO.File]::WriteAllText($temporary, ($script:State | ConvertTo-Json -Depth 8 -Compress), $script:Utf8NoBom)
    try {
        if (Test-Path -LiteralPath $script:StatePath -PathType Leaf) {
            [IO.File]::Replace([string]$temporary, [string]$script:StatePath, [string]$backup, $true)
        } else {
            [IO.File]::Move([string]$temporary, [string]$script:StatePath)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
}

function Read-Toolchain {
    try {
        $toolchain = Get-Content -LiteralPath $script:ToolchainPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($toolchain.schema_version -ne "1") { throw "unsupported toolchain schema" }
        return $toolchain
    } catch {
        Fail-Development "toolchain" "无法读取唯一工具链清单" "恢复 product/config/toolchain.json 后重试"
    }
}

function Save-CallerEnvironment {
    $names = @(
        "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "PYTHONUTF8", "PYTHONIOENCODING", "PYTHONPATH", "PYTHONHOME",
        "UV_PROJECT_ENVIRONMENT", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "PLAYWRIGHT_BROWSERS_PATH",
        "JIEJIAN_VAR_DIR", "JIEJIAN_PROJECT_ROOT", "JIEJIAN_RUNTIME_MODE", "JIEJIAN_PYTHON_EXECUTABLE",
        "JIEJIAN_PYTHON_ENVIRONMENT_PATH", "JIEJIAN_PYTHON_ENVIRONMENT_TYPE", "JIEJIAN_UV_EXECUTABLE", "JIEJIAN_UV_VERSION",
        "JIEJIAN_TOOLCHAIN_MANIFEST", "JIEJIAN_RUNTIME_FINGERPRINT", "JIEJIAN_PLAYWRIGHT_EXECUTABLE", "PATH",
        "JIEJIAN_NODE_EXECUTABLE", "JIEJIAN_NODE_VERSION", "JIEJIAN_PNPM_EXECUTABLE", "JIEJIAN_PNPM_VERSION",
        "JIEJIAN_FRONTEND_OUT_DIR", "JIEJIAN_FRONTEND_CACHE_DIR", "JIEJIAN_FRONTEND_DEPENDENCIES",
        "JIEJIAN_FRONTEND_DIST", "JIEJIAN_FRONTEND_BUILD_STATE", "JIEJIAN_PACKAGE_FRONTEND_DIR"
    )
    $values = @{}
    $processEnvironment = [Environment]::GetEnvironmentVariables("Process")
    foreach ($name in $names) {
        $exists = $processEnvironment.Contains($name)
        $values[$name] = [pscustomobject]@{
            exists = $exists
            value = if ($exists) { [string]$processEnvironment[$name] } else { $null }
        }
    }
    $script:CallerEnvironmentSnapshot = [pscustomobject]@{
        variable_names = @($names)
        variables = $values
        input_encoding = [Console]::InputEncoding
        output_encoding = [Console]::OutputEncoding
        output_encoding_variable = $OutputEncoding
        location = (Get-Location).Path
    }
}

function Restore-CallerEnvironment {
    $snapshot = $script:CallerEnvironmentSnapshot
    if ($null -eq $snapshot) { return }
    try { Set-Location -LiteralPath $snapshot.location } catch { }
    for ($index = $snapshot.variable_names.Count - 1; $index -ge 0; $index--) {
        $name = [string]$snapshot.variable_names[$index]
        $record = $snapshot.variables[$name]
        if ([bool]$record.exists) { [Environment]::SetEnvironmentVariable($name, [string]$record.value, "Process") }
        else { Remove-Item -LiteralPath ("Env:{0}" -f $name) -ErrorAction SilentlyContinue }
    }
    Set-Variable -Name OutputEncoding -Value $snapshot.output_encoding_variable -Scope 1
    [Console]::OutputEncoding = $snapshot.output_encoding
    [Console]::InputEncoding = $snapshot.input_encoding
}
