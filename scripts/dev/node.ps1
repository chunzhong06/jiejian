# 解析并核验前端构建的 Node 与 pnpm 工具链。

function Resolve-DevelopmentNode($Toolchain, [bool]$Exact) {
    if ($Exact) {
        $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
        $key = switch ($architecture.ToUpperInvariant()) { "AMD64" { "x64" } "ARM64" { "arm64" } default { $null } }
        if ($null -eq $key) { Fail-Development "frontend" "当前 Windows 架构不受发布构建工具链支持" "使用 AMD64 或 ARM64 Windows" }
        $nodeVersion = [string]$Toolchain.node.build_version
        $pnpmVersion = [string]$Toolchain.pnpm.version
        $nodeRoot = Join-Path $script:DevelopmentRoot ("tools\node\{0}\{1}" -f $nodeVersion, $key)
        $nodeExecutable = Join-Path $nodeRoot ("node-v{0}-win-{1}\node.exe" -f $nodeVersion, $key)
        $pnpmRoot = Join-Path $script:DevelopmentRoot ("tools\pnpm\{0}" -f $pnpmVersion)
        $pnpmEntry = Join-Path $pnpmRoot "package\bin\pnpm.cjs"
        $receiptPath = Join-Path $script:DevelopmentRoot "state\toolchain-receipt.json"
        $hashProperty = "{0}_sha256" -f $key
        $expectedNodeHash = [string]$Toolchain.node.windows.PSObject.Properties[$hashProperty].Value
        $healthy = $false
        if ((Test-Path -LiteralPath $nodeExecutable -PathType Leaf) -and (Test-Path -LiteralPath $pnpmEntry -PathType Leaf) -and (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
            try {
                $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $healthy = $receipt.node_version -eq $nodeVersion -and $receipt.pnpm_version -eq $pnpmVersion -and $receipt.node_executable_sha256 -eq (Get-FileDigest $nodeExecutable) -and $receipt.pnpm_entry_sha256 -eq (Get-FileDigest $pnpmEntry)
            } catch { $healthy = $false }
        }
        if (-not $healthy) {
            $downloadRoot = Join-Path $script:DevelopmentRoot ("temp\build-toolchain-{0}" -f [guid]::NewGuid().ToString("N"))
            $nodeArchive = Join-Path $downloadRoot ("node-v{0}-win-{1}.zip" -f $nodeVersion, $key)
            $pnpmArchive = Join-Path $downloadRoot ("pnpm-{0}.tgz" -f $pnpmVersion)
            New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
            Register-StartupTemporary $downloadRoot
            try {
                Invoke-WebRequest -Uri ("{0}node-v{1}-win-{2}.zip" -f [string]$Toolchain.node.source, $nodeVersion, $key) -OutFile $nodeArchive -UseBasicParsing
                if ((Get-FileDigest $nodeArchive) -ne $expectedNodeHash) { Fail-Development "frontend" "Node.js 发布构建归档校验失败" "检查 product/config/toolchain.json 与官方下载源" }
                Invoke-WebRequest -Uri ([string]$Toolchain.pnpm.source) -OutFile $pnpmArchive -UseBasicParsing
                $sha512 = [Security.Cryptography.SHA512]::Create()
                try { $pnpmIntegrity = "sha512-" + [Convert]::ToBase64String($sha512.ComputeHash([IO.File]::ReadAllBytes($pnpmArchive))) } finally { $sha512.Dispose() }
                if ($pnpmIntegrity -ne [string]$Toolchain.pnpm.integrity) { Fail-Development "frontend" "pnpm 发布构建归档完整性校验失败" "检查 product/config/toolchain.json 与 npm 官方归档" }
                Remove-Item -LiteralPath $nodeRoot -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item -LiteralPath $pnpmRoot -Recurse -Force -ErrorAction SilentlyContinue
                New-Item -ItemType Directory -Path $nodeRoot -Force | Out-Null
                New-Item -ItemType Directory -Path $pnpmRoot -Force | Out-Null
                Expand-Archive -LiteralPath $nodeArchive -DestinationPath $nodeRoot -Force
                & tar.exe -xzf $pnpmArchive -C $pnpmRoot
                if ($LASTEXITCODE -ne 0) { Fail-Development "frontend" "无法展开固定 pnpm 归档" "确认 Windows tar.exe 可用后重试" }
                if (-not (Test-Path -LiteralPath $nodeExecutable -PathType Leaf) -or -not (Test-Path -LiteralPath $pnpmEntry -PathType Leaf)) { Fail-Development "frontend" "发布构建工具归档缺少预期入口" "删除 var/development/tools 中对应工具后重试" }
                $receipt = [ordered]@{ schema_version = "1"; node_version = $nodeVersion; pnpm_version = $pnpmVersion; node_archive_sha256 = $expectedNodeHash; pnpm_integrity = $pnpmIntegrity; node_executable_sha256 = Get-FileDigest $nodeExecutable; pnpm_entry_sha256 = Get-FileDigest $pnpmEntry }
                New-Item -ItemType Directory -Path (Split-Path -Parent $receiptPath) -Force | Out-Null
                [IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Compress), $script:Utf8NoBom)
            } finally { Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue }
        }
        $script:Node = [IO.Path]::GetFullPath($nodeExecutable)
        $script:PnpmRunner = @($script:Node, [IO.Path]::GetFullPath($pnpmEntry))
        $script:NodeVersion = (& $script:Node --version 2>&1 | Out-String).Trim().TrimStart("v")
        $script:PnpmVersion = (& $script:PnpmRunner[0] $script:PnpmRunner[1] --version 2>&1 | Out-String).Trim()
        if ($script:NodeVersion -ne $nodeVersion -or $script:PnpmVersion -ne $pnpmVersion) { Fail-Development "frontend" "固定发布构建工具版本探针失败" "删除 var/development/tools 中对应工具后重新执行 package" }
        $originalPath = [string]$script:CallerEnvironmentSnapshot.variables["PATH"].value
        $env:PATH = (Split-Path -Parent $script:Node) + ";" + $originalPath
        $env:JIEJIAN_NODE_EXECUTABLE = $script:Node
        $env:JIEJIAN_NODE_VERSION = $script:NodeVersion
        $env:JIEJIAN_PNPM_EXECUTABLE = $script:PnpmRunner[1]
        $env:JIEJIAN_PNPM_VERSION = $script:PnpmVersion
        return
    }
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    $pnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $node -or $null -eq $pnpm) { Fail-Development "frontend" "开发前端需要 Node.js 与 pnpm" "安装满足 package.json 的 Node.js 和 pnpm，或执行发布构建准备" }
    $nodeVersion = (& $node.Source --version 2>&1 | Out-String).Trim().TrimStart("v")
    $pnpmVersion = (& $pnpm.Source --version 2>&1 | Out-String).Trim()
    try { $parsed = [version]$nodeVersion } catch { $parsed = $null }
    $nodeOk = $null -ne $parsed -and $parsed -ge [version]"24.13.0" -and $parsed.Major -lt 25
    if (-not $nodeOk -or $pnpmVersion -ne [string]$Toolchain.pnpm.version) { Fail-Development "frontend" "Node/pnpm 版本不符合工具链清单" ("需要 Node {0} 与 pnpm {1}" -f $Toolchain.node.development_range, $Toolchain.pnpm.version) }
    $script:Node = $node.Source
    $script:NodeVersion = $nodeVersion
    $script:PnpmRunner = @($pnpm.Source)
    $script:PnpmVersion = $pnpmVersion
    $env:JIEJIAN_NODE_EXECUTABLE = $script:Node
    $env:JIEJIAN_NODE_VERSION = $script:NodeVersion
    $env:JIEJIAN_PNPM_EXECUTABLE = $script:PnpmRunner[0]
    $env:JIEJIAN_PNPM_VERSION = $script:PnpmVersion
}
