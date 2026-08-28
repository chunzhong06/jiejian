# Windows x64 Portable 发行入口：准备已冻结构建材料并委托唯一 Python 组装器生成双 ZIP。

function Invoke-Package($Toolchain) {
    $releaseVersion = (& $script:Python -B -c "from product.backend import __version__; print(__version__)" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $releaseVersion) {
        Fail-Development "portable" "无法读取界鉴产品版本真源" "检查 product/backend/__init__.py 与受控 Python 环境"
    }
    $releaseName = "JieJian-WebV1-{0}-Windows-x64" -f $releaseVersion
    if ($env:PROCESSOR_ARCHITECTURE -ne "AMD64") {
        Fail-Development "portable" ("Web V1 {0} 便携发行只支持 Windows x64" -f $releaseVersion) "请在 AMD64 Windows 上执行 .\scripts\dev.ps1 package"
    }

    Prepare-Chromium
    Prepare-SourceFrontend $Toolchain

    $releaseRoot = Join-Path $script:DevelopmentRoot "release"
    $buildRoot = Join-Path $releaseRoot "build\wheel"
    $artifactRoot = Join-Path $releaseRoot "artifacts"
    $frontend = Join-Path $script:VarDir "runtime\frontend"
    $distribution = [string]$Toolchain.python.release_distribution
    $releasePython = Join-Path $script:DevelopmentRoot ("tools\python\installations\{0}" -f $distribution)
    $releasePythonExecutable = Join-Path $releasePython "python.exe"

    if (-not (Test-Path -LiteralPath (Join-Path $frontend "index.html") -PathType Leaf)) {
        Fail-Development "portable" "便携发行缺少已准备的前端入口" "检查 Prepare-SourceFrontend 的正式构建输出"
    }
    if (-not (Test-Path -LiteralPath $releasePythonExecutable -PathType Leaf)) {
        $version = [string]$Toolchain.python.release_version
        Invoke-External "portable-python" @($script:Uv, "python", "install", $version)
    }
    if (-not (Test-Path -LiteralPath $releasePythonExecutable -PathType Leaf)) {
        Fail-Development "portable" "uv 未形成冻结的 Windows x64 CPython" ("预期目录：{0}" -f $releasePython)
    }

    New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
    Get-ChildItem -LiteralPath $buildRoot -Filter "jiejian-*.whl" -File -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -LiteralPath $artifactRoot -Filter "jiejian-*.whl" -File -ErrorAction SilentlyContinue | Remove-Item -Force
    foreach ($name in @(
        ($releaseName + ".zip"),
        ($releaseName + "-nosamples.zip"),
        "SHA256SUMS.txt"
    )) {
        Remove-Item -LiteralPath (Join-Path $artifactRoot $name) -Force -ErrorAction SilentlyContinue
    }

    $env:JIEJIAN_PACKAGE_FRONTEND_DIR = [IO.Path]::GetFullPath($frontend)
    Push-Location -LiteralPath $script:ProjectRoot
    try {
        Invoke-External "wheel" @($script:Uv, "build", "--wheel", "--out-dir", $buildRoot)
    } finally {
        Pop-Location
    }
    $wheels = @(Get-ChildItem -LiteralPath $buildRoot -Filter "jiejian-*.whl" -File)
    if ($wheels.Count -ne 1) {
        Fail-Development "portable" "便携发行没有形成唯一内部 Wheel" "检查 uv build 输出"
    }

    $arguments = @(
        "-B",
        (Join-Path $script:ProjectRoot "scripts\build\portable.py"),
        "--project-root", $script:ProjectRoot,
        "--release-root", $releaseRoot,
        "--wheel", $wheels[0].FullName,
        "--python-source", $releasePython,
        "--playwright-source", (Join-Path $script:DevelopmentRoot "tools\playwright"),
        "--samples-source", (Join-Path $script:ProjectRoot "samples"),
        "--uv", $script:Uv,
        "--uv-cache", (Join-Path $script:DevelopmentRoot "cache\uv"),
        "--toolchain", $script:ToolchainPath
    )
    Invoke-External "portable" (@($script:Python) + $arguments)

    $outputs = @(
        (Join-Path $artifactRoot ($releaseName + ".zip")),
        (Join-Path $artifactRoot ($releaseName + "-nosamples.zip")),
        (Join-Path $artifactRoot "SHA256SUMS.txt")
    )
    foreach ($output in $outputs) {
        if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
            Fail-Development "portable" "便携发行缺少固定交付物" ("缺失：{0}" -f $output)
        }
    }
    Write-Host "Windows x64 Portable 已生成：" -ForegroundColor Green
    foreach ($output in $outputs) { Write-Host ("  {0}" -f $output) }
}
