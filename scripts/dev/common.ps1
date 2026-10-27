# 开发准备的失败映射、共享锁和状态记录。

function Fail-Development([string]$Stage, [string]$Message, [string]$Recovery) {
    # 父启动面板读取固定字段，避免只剩“外部命令返回 1”而丢失准备阶段。
    $failure = @{stage=$Stage; message=$Message; recovery=$Recovery} | ConvertTo-Json -Compress
    [Console]::Out.WriteLine("__JIEJIAN_PREPARE_FAILURE__:" + $failure)
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
