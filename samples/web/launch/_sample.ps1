#Requires -Version 5.1

# =============================================================================
# Web Sample 启动公共能力
#
# 定位
#   为 GUI/CLI Sample 入口准备同一个本机 Target 与临时身份
#
# 职责
#   复用源码运行环境｜生成进程级凭据｜启动并探活 Target｜精确回收子进程
#
# 边界
#   只调用产品公开入口，不写产品数据库或预设结论；日志和临时状态只进入 var/。
#
# 调用链
#   gui.ps1 / cli.ps1 → 本脚本 → scripts/dev.ps1 / Sample Target
# =============================================================================

Set-StrictMode -Version Latest

$script:SampleSecretNames = @(
    "JIEJIAN_AUTHORIZATION_OWNER_TOKEN",
    "JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN",
    "JIEJIAN_AUTHORIZATION_PEER_TOKEN",
    "JIEJIAN_AUTHORIZATION_OWNER_OBSERVER"
)

function Resolve-SampleContext([string]$VarDir) {
    $projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
    $shellName = if ($PSEdition -eq "Core") { "pwsh.exe" } else { "powershell.exe" }
    $shell = Join-Path $PSHOME $shellName
    if (-not (Test-Path -LiteralPath $shell -PathType Leaf)) {
        throw "无法定位当前 PowerShell 可执行文件。"
    }
    $resolvedVar = if ([string]::IsNullOrWhiteSpace($VarDir)) {
        Join-Path $projectRoot "var"
    } elseif ([IO.Path]::IsPathRooted($VarDir)) {
        [IO.Path]::GetFullPath($VarDir)
    } else {
        [IO.Path]::GetFullPath((Join-Path $projectRoot $VarDir))
    }
    return [pscustomobject]@{
        ProjectRoot = $projectRoot
        VarDir = $resolvedVar
        PowerShell = $shell
        DevScript = Join-Path $projectRoot "scripts\dev.ps1"
        StartCommand = Join-Path $projectRoot "start.cmd"
        SampleRoot = Join-Path $projectRoot "samples\web"
    }
}

function Set-SampleSecrets {
    $saved = @{}
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        foreach ($name in $script:SampleSecretNames) {
            $saved[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
            $bytes = New-Object byte[] 24
            $generator.GetBytes($bytes)
            $value = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    } finally {
        $generator.Dispose()
    }
    return $saved
}

function Restore-SampleSecrets([hashtable]$Saved) {
    foreach ($name in $script:SampleSecretNames) {
        [Environment]::SetEnvironmentVariable($name, $Saved[$name], "Process")
    }
}

function Start-SampleTarget($Context, [string]$Variant) {
    & $Context.PowerShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File $Context.DevScript prepare -VarDir $Context.VarDir | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "界鉴源码运行环境准备失败。"
    }
    $receiptPath = Join-Path $Context.VarDir "runtime\source\receipt.json"
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
        throw "未找到源码运行环境回执：$receiptPath"
    }
    $receipt = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json
    $python = [string]$receipt.python.executable
    if ([string]::IsNullOrWhiteSpace($python) -or -not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "源码运行环境回执没有提供有效 Python。"
    }
    $ports = @{ fixed = 8865; vulnerable = 8766; inconclusive = 8767 }
    $port = [int]$ports[$Variant]
    $logRoot = Join-Path $Context.VarDir "logs\samples"
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $stdout = Join-Path $logRoot ("web-{0}.log" -f $Variant)
    $stderr = Join-Path $logRoot ("web-{0}.error.log" -f $Variant)
    $process = Start-Process -FilePath $python -ArgumentList @(
        "-B", "-m", "samples.web.target.server",
        "--variant", $Variant,
        "--port", [string]$port
    ) -WorkingDirectory $Context.ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 50; $attempt += 1) {
        $process.Refresh()
        if ($process.HasExited) {
            $detail = if (Test-Path -LiteralPath $stderr) { (Get-Content -Raw -LiteralPath $stderr).Trim() } else { "" }
            throw ("Sample Target 启动失败。{0}" -f $(if ($detail) { " $detail" } else { "" }))
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/health" -f $port) -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 100
        }
    }
    if (-not $ready) {
        Stop-SampleTarget $process
        throw "Sample Target 启动超时，请查看 $stderr。"
    }
    return [pscustomobject]@{
        Process = $process
        Port = $port
        Address = "http://127.0.0.1:$port"
        Profile = Join-Path $Context.SampleRoot "$Variant\profile.json"
        Contract = Join-Path $Context.SampleRoot "$Variant\contract.json"
        Log = $stdout
        ErrorLog = $stderr
    }
}

function Stop-SampleTarget($Target) {
    $process = if ($Target -is [Diagnostics.Process]) { $Target } else { $Target.Process }
    if ($null -eq $process) { return }
    $process.Refresh()
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $process.WaitForExit(5000) | Out-Null
    }
    $process.Dispose()
}
