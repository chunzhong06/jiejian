# 初始化开发任务上下文，产品实例与共享开发工具分别定位。

function Initialize-DevelopmentContext([string]$Root, [string]$RuntimeRoot) {
    $script:ProjectRoot = $Root
    $script:VarDir = if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) { Join-Path $script:ProjectRoot "var" } elseif ([IO.Path]::IsPathRooted($RuntimeRoot)) { [IO.Path]::GetFullPath($RuntimeRoot) } else { [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot $RuntimeRoot)) }
    # 每轮产品事实由 -VarDir 隔离；跨实例共享的开发工具、构建与状态只进入固定 DevelopmentRoot。
    $script:DevelopmentRoot = [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot "var\development"))
    $script:ToolchainPath = Join-Path $script:ProjectRoot "product\config\toolchain.json"
    $script:EnvironmentPath = Join-Path $script:ProjectRoot "environment.yml"
    $script:StatePath = Join-Path $script:DevelopmentRoot "state\development-state.json"
    $script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $script:PrepareLock = $null
    $script:Python = $null
    $script:Conda = $null
    $script:CondaPrefix = $null
    $script:Uv = $null
    $script:UvVersion = $null
    $script:Node = $null
    $script:NodeVersion = $null
    $script:PnpmRunner = @()
    $script:PnpmVersion = $null
    $script:FrontendBuildState = $null
    $script:State = [pscustomobject]@{ schema_version = "1" }
    $script:CallerEnvironmentSnapshot = $null

}
