# 启动准备状态：持久化阶段指纹、缓存命中事实和最低环境探针。
# 损坏或未知版本只触发冷准备，不猜测迁移旧状态。
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
        Write-DisplaySubtask "准备状态损坏或版本未知，安全执行冷准备"
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
    # 状态文件采用同目录临时文件替换，异常中断不能留下半写 JSON 被当作缓存命中。
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
    # 路径和事实均排序后再哈希，使指纹只随真实输入变化而不受枚举顺序影响。
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

function Get-ExpectedPnpmStoreDir {
    $versionMatch = [regex]::Match([string]$script:PnpmVersion, "(?m)^v?(?<major>\d+)(?:\.|$)")
    if (-not $versionMatch.Success) { return $null }
    $storeRoot = Join-Path (Split-Path -Parent $script:ProjectRoot) ".pnpm-store"
    return [IO.Path]::GetFullPath((Join-Path $storeRoot ("v{0}" -f $versionMatch.Groups["major"].Value)))
}

function Test-PnpmStoreDir([string]$ModulesManifest, [string]$ExpectedStoreDir) {
    if ([string]::IsNullOrWhiteSpace($ExpectedStoreDir) -or -not (Test-Path -LiteralPath $ModulesManifest -PathType Leaf)) {
        return $false
    }
    try {
        $content = Get-Content -LiteralPath $ModulesManifest -Raw -ErrorAction Stop
        $manifestObject = $content | ConvertFrom-Json -ErrorAction Stop
        $recordedValue = $manifestObject.storeDir
        if ($null -eq $recordedValue -or $recordedValue -isnot [string] -or [string]::IsNullOrWhiteSpace($recordedValue)) {
            return $false
        }
        $recorded = [IO.Path]::GetFullPath($recordedValue)
        return [string]::Equals($recorded, $ExpectedStoreDir, [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}
