# 工程文件摘要与受控临时目录标记；不拥有产品业务数据。

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

function Register-StartupTemporary([string]$Path) {
    # 只标记共享启动临时根内已建立的目录；调用方持有 prepare lock。
    $root = [IO.Path]::GetFullPath((Join-Path $script:DevelopmentRoot "temp"))
    $target = [IO.Path]::GetFullPath($Path)
    if (-not $target.StartsWith($root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "启动临时目录越界" }
    $directory = Get-Item -LiteralPath $target
    if (($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "启动临时目录不能是链接" }
    $record = [ordered]@{ schema_version = "1"; kind = "startup-temporary"; name = $directory.Name }
    [IO.File]::WriteAllText((Join-Path $target ".startup-owned.json"), ($record | ConvertTo-Json -Compress), $script:Utf8NoBom)
}
