# 为工程入口保存并恢复调用者环境、编码和工作目录。

function Save-CallerEnvironment {
    $names = @(
        "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "PYTHONUTF8", "PYTHONIOENCODING", "PYTHONPATH", "PYTHONHOME",
        "UV_PROJECT_ENVIRONMENT", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "PLAYWRIGHT_BROWSERS_PATH",
        "JIEJIAN_VAR_DIR", "JIEJIAN_PROJECT_ROOT", "JIEJIAN_RUNTIME_MODE", "JIEJIAN_PYTHON_EXECUTABLE",
        "JIEJIAN_PYTHON_ENVIRONMENT_PATH", "JIEJIAN_PYTHON_ENVIRONMENT_TYPE", "JIEJIAN_UV_EXECUTABLE", "JIEJIAN_UV_VERSION",
        "JIEJIAN_TOOLCHAIN_MANIFEST", "JIEJIAN_RUNTIME_FINGERPRINT", "JIEJIAN_PLAYWRIGHT_EXECUTABLE", "PATH",
        "JIEJIAN_NODE_EXECUTABLE", "JIEJIAN_NODE_VERSION", "JIEJIAN_PNPM_EXECUTABLE", "JIEJIAN_PNPM_VERSION",
        "JIEJIAN_FRONTEND_OUT_DIR", "JIEJIAN_FRONTEND_CACHE_DIR", "JIEJIAN_FRONTEND_DEPENDENCIES",
        "JIEJIAN_FRONTEND_DIST", "JIEJIAN_FRONTEND_BUILD_STATE", "JIEJIAN_PACKAGE_FRONTEND_DIR",
        "COREPACK_HOME", "COREPACK_ENABLE_DOWNLOAD_PROMPT", "JIEJIAN_COREPACK_EXECUTABLE", "PNPM_HOME", "npm_config_cache"
    )
    $values = @{}
    $processEnvironment = [Environment]::GetEnvironmentVariables("Process")
    foreach ($name in $names) {
        # 必须区分“不存在”和已有字符串值，恢复时不能把本轮引导变量遗留给调用者。
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
    # 模块通过点引入参与入口会话；恢复调用者作用域的编码，不能只修改当前函数的局部变量。
    Set-Variable -Name OutputEncoding -Value $snapshot.output_encoding_variable -Scope 1
    [Console]::OutputEncoding = $snapshot.output_encoding
    [Console]::InputEncoding = $snapshot.input_encoding
}
