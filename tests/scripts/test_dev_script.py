# 验证开发总控台模块装配、命令合同、受控工作区与调用者环境恢复。

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
DEV = ROOT / "scripts" / "dev.ps1"
MODULE_ROOT = ROOT / "scripts" / "dev"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _powershell_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def test_dev_loads_only_frozen_modules_in_order() -> None:
    dev = _text(DEV)
    modules = ("common", "python", "frontend", "prepare", "package", "sample-test", "commands")
    positions = [dev.index(f'"dev\\{name}.ps1"') for name in modules]
    assert positions == sorted(positions)
    assert dev.count(". (Join-Path $PSScriptRoot") == 7
    for path in MODULE_ROOT.glob("*.ps1"):
        source = _text(path)
        assert ". " not in source
        assert "dot-source" not in source


def test_development_start_only_forwards_to_product_startup() -> None:
    source = _text(MODULE_ROOT / "commands.ps1")
    function = source[source.index("function Invoke-DevelopmentStart") : source.index("function Invoke-DevelopmentTest")]
    assert "scripts\\start.ps1" in function
    assert '"-Mode", "Gui"' in function
    assert "Prepare-SourceRuntime" not in function
    assert '"serve"' not in function


def test_development_entry_keeps_public_commands_and_contract_preflight() -> None:
    dev = _text(DEV)
    python = _text(MODULE_ROOT / "python.ps1")
    commands = _text(MODULE_ROOT / "commands.ps1")
    for command in ("bootstrap", "sync", "update", "prepare", "start", "cli", "test", "frontend-test", "sample-test", "schema", "docs", "shell", "package"):
        assert f'"{command}"' in dev
    assert "Test-CommandContract" in dev
    assert "Enter-PrepareLock" in dev
    assert python.count('Invoke-External "uv-update"') == 1
    assert "function Invoke-Update" in python
    assert "function Invoke-Update" not in commands
    assert commands.count('Invoke-External "docs"') == 1
    assert 'Resolve-DocsPython' in commands


def test_command_contract_rejects_unused_options_before_lock() -> None:
    dev = _text(DEV)
    contract = dev[dev.index("function Test-CommandContract") : dev.index("try {")]
    assert '$Command -notin @("schema", "docs")' in contract
    assert '$Command -notin @("prepare", "start", "package")' in contract
    assert '$Command -notin @("update", "cli", "test", "frontend-test", "sample-test")' in contract
    preflight = dev[dev.index("try {") : dev.index("Read-State")]
    assert preflight.index("Test-CommandContract") < preflight.index("Enter-PrepareLock")


def test_invalid_arguments_fail_before_prepare_side_effects(tmp_path: Path) -> None:
    var_dir = tmp_path / "invalid-contract-var"
    nested_command = f"& {_powershell_literal(DEV)} test -Update -VarDir {_powershell_literal(var_dir)}"
    command = (
        "$env:UV_CACHE_DIR='sentinel-uv';"
        "$nested=[PowerShell]::Create();"
        f"$null=$nested.AddScript({_powershell_literal(nested_command)});"
        "$null=$nested.Invoke();$messages=@($nested.Streams.Information|ForEach-Object{$_.MessageData}) -join \"`n\";"
        "$state=$nested.InvocationStateInfo.State.ToString();$nested.Dispose();"
        f"[pscustomobject]@{{state=$state;uv=$env:UV_CACHE_DIR;var_exists=(Test-Path -LiteralPath {_powershell_literal(var_dir)});prepare_marker=($messages -match '__JIEJIAN_PREPARE_STATUS__')}}|ConvertTo-Json -Compress"
    )
    result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(result.stdout.strip().splitlines()[-1])
    assert record == {"state": "Completed", "uv": "sentinel-uv", "var_exists": False, "prepare_marker": False}


def test_python_sync_digest_tracks_editable_package_topology() -> None:
    source = _text(MODULE_ROOT / "python.ps1")
    assert '"product\\backend", "product\\protocols"' in source
    assert '-Filter "__init__.py" -File' in source
    assert source.count("Get-CombinedDigest @(Get-ProjectSyncInputs)") == 2
    assert source.count("Get-PathSetDigest @(Get-ProjectPackageTopologyInputs)") == 2
    assert source.count('"--reinstall-package", "jiejian"') == 2
    assert 'Set-StateValue "package_topology_digest"' in source
    assert "$stateTopologyDigest -ne $topologyDigest" in source


def test_uv_partial_download_keeps_zip_extension_for_expand_archive() -> None:
    source = _text(MODULE_ROOT / "python.ps1")
    assert 'cache\\downloads\\.tmp-{0}-{1}' in source
    assert "Expand-Archive -LiteralPath $partial" in source
    assert 'cache\\downloads\\{0}.partial' not in source


def test_docs_uses_existing_python_without_full_prepare_or_uv() -> None:
    python = _text(MODULE_ROOT / "python.ps1")
    commands = _text(MODULE_ROOT / "commands.ps1")
    locator = python[python.index("function Resolve-DocsPython") :]
    assert "Test-CondaPython" in locator
    assert "Resolve-Uv" not in locator
    assert "Sync-Project" not in locator
    docs = commands[commands.index("function Invoke-Docs") : commands.index("function Invoke-FrontendTest")]
    assert "Resolve-DocsPython" in docs
    assert "-B" in docs
    assert "--update" in docs


def _run_environment_restore_probe(*, raise_after_mutation: bool) -> dict[str, object]:
    common = MODULE_ROOT / "common.ps1"
    sentinels = {
        "PATH": "sentinel-path",
        "PYTHONPATH": "sentinel-python",
        "UV_CACHE_DIR": "sentinel-uv",
        "PLAYWRIGHT_BROWSERS_PATH": "sentinel-playwright",
        "JIEJIAN_NODE_EXECUTABLE": "sentinel-node",
        "JIEJIAN_PNPM_EXECUTABLE": "sentinel-pnpm",
        "JIEJIAN_FRONTEND_CACHE_DIR": "sentinel-frontend",
    }
    absent = ("PYTHONHOME", "JIEJIAN_RUNTIME_FINGERPRINT")
    sentinel_literal = "@{" + ";".join(f"'{name}'='{value}'" for name, value in sentinels.items()) + "}"
    absent_literal = "@(" + ",".join(f"'{name}'" for name in absent) + ")"
    should_raise = "$true" if raise_after_mutation else "$false"
    command = (
        f"$script:Utf8NoBom=New-Object System.Text.UTF8Encoding($false);$script:VarDir={_powershell_literal(ROOT / 'var')};"
        f"$script:StatePath={_powershell_literal(ROOT / 'var/development/state/development-state.json')};"
        f". {_powershell_literal(common)};"
        f"$sentinels={sentinel_literal};$absent={absent_literal};$shouldRaise={should_raise};"
        "foreach($pair in $sentinels.GetEnumerator()){[Environment]::SetEnvironmentVariable($pair.Key,[string]$pair.Value,'Process')};"
        "foreach($name in $absent){Remove-Item -LiteralPath ('Env:'+ $name) -ErrorAction SilentlyContinue};"
        "$expectedLocation=(Get-Location).Path;$expectedInput=[Console]::InputEncoding.WebName;$expectedOutput=[Console]::OutputEncoding.WebName;$expectedVariable=$OutputEncoding.WebName;"
        "Save-CallerEnvironment;try{foreach($pair in $sentinels.GetEnumerator()){[Environment]::SetEnvironmentVariable($pair.Key,'changed','Process')};"
        "foreach($name in $absent){[Environment]::SetEnvironmentVariable($name,'created','Process')};"
        "[Console]::InputEncoding=[Text.Encoding]::Unicode;[Console]::OutputEncoding=[Text.Encoding]::Unicode;$OutputEncoding=[Text.Encoding]::Unicode;Set-Location -LiteralPath $env:TEMP;"
        "if($shouldRaise){throw 'expected probe failure'}}catch{if(-not $shouldRaise){throw}}finally{Restore-CallerEnvironment};"
        "$record=[ordered]@{};foreach($pair in $sentinels.GetEnumerator()){$record[$pair.Key]=[Environment]::GetEnvironmentVariable($pair.Key,'Process')};"
        "foreach($name in $absent){$record['absent_'+$name]=-not ([Environment]::GetEnvironmentVariables('Process')).Contains($name)};"
        "$record['location']=(Get-Location).Path;$record['input']=[Console]::InputEncoding.WebName;$record['output']=[Console]::OutputEncoding.WebName;$record['variable']=$OutputEncoding.WebName;"
        "$record['expected_location']=$expectedLocation;$record['expected_input']=$expectedInput;$record['expected_output']=$expectedOutput;$record['expected_variable']=$expectedVariable;"
        "$record|ConvertTo-Json -Compress"
    )
    result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _assert_environment_restore_probe(record: dict[str, object]) -> None:
    assert record["PATH"] == "sentinel-path"
    assert record["PYTHONPATH"] == "sentinel-python"
    assert record["UV_CACHE_DIR"] == "sentinel-uv"
    assert record["PLAYWRIGHT_BROWSERS_PATH"] == "sentinel-playwright"
    assert record["JIEJIAN_NODE_EXECUTABLE"] == "sentinel-node"
    assert record["JIEJIAN_PNPM_EXECUTABLE"] == "sentinel-pnpm"
    assert record["JIEJIAN_FRONTEND_CACHE_DIR"] == "sentinel-frontend"
    assert record["absent_PYTHONHOME"] is True
    assert record["absent_JIEJIAN_RUNTIME_FINGERPRINT"] is True
    assert record["location"] == record["expected_location"]
    assert record["input"] == record["expected_input"]
    assert record["output"] == record["expected_output"]
    assert record["variable"] == record["expected_variable"]


def test_environment_snapshot_restores_representative_existing_and_absent_values() -> None:
    _assert_environment_restore_probe(_run_environment_restore_probe(raise_after_mutation=False))


def test_environment_snapshot_restores_after_helper_exception() -> None:
    _assert_environment_restore_probe(_run_environment_restore_probe(raise_after_mutation=True))


def test_environment_restore_runs_in_top_level_finally() -> None:
    dev = _text(DEV)
    assert "Save-CallerEnvironment" in dev
    assert "Restore-CallerEnvironment" in dev
    assert "finally" in dev[dev.index("try {") :]
    finalizer = dev[dev.index("} finally {", dev.index("} catch {")) :]
    assert finalizer.index("Restore-CallerEnvironment") < finalizer.index("Exit-PrepareLock")


def test_development_identity_probe_preserves_confirmed_runtime_fingerprint() -> None:
    python_module = MODULE_ROOT / "python.ps1"
    command = (
        f"$script:Python={_powershell_literal(Path(sys.executable).resolve())};"
        f". {_powershell_literal(python_module)};"
        "$env:JIEJIAN_RUNTIME_FINGERPRINT='confirmed-fingerprint';"
        "$null=Read-DevelopmentIdentity;"
        "[Environment]::GetEnvironmentVariable('JIEJIAN_RUNTIME_FINGERPRINT','Process')"
    )
    result = subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1] == "confirmed-fingerprint"


def test_package_routes_one_base_tree_to_fixed_windows_x64_portable_outputs() -> None:
    source = _text(MODULE_ROOT / "package.ps1")
    assert "Prepare-SourceFrontend" in source
    assert "Prepare-Chromium" in source
    assert '"scripts\\build\\portable.py"' in source
    assert '"release_distribution"' not in source
    assert ".release_distribution" in source
    assert '"python", "install", $version' in source
    assert '"--python-source"' in source
    assert '"--playwright-source"' in source
    assert '"--samples-source"' in source
    assert 'Get-ChildItem -LiteralPath $artifactRoot -Filter "jiejian-*.whl"' in source
    assert "from product.backend import __version__" in source
    assert '$releaseName = "JieJian-WebV1-{0}-Windows-x64" -f $releaseVersion' in source
    assert '($releaseName + ".zip")' in source
    assert '($releaseName + "-nosamples.zip")' in source
    assert "SHA256SUMS.txt" in source


def test_frontend_install_build_test_and_package_stay_outside_source_tree() -> None:
    frontend = _text(MODULE_ROOT / "frontend.ps1")
    package = _text(MODULE_ROOT / "package.ps1")
    hook = _text(ROOT / "scripts" / "build" / "hatch_build.py")
    assert "Prepare-FrontendWorkspace $Toolchain $inputs $dependencyDigest" in frontend
    assert "Get-FrontendDependencyDigest" in frontend
    assert "Get-FrontendBuildDigest" in frontend
    assert '"frontend\\builds\\{0}" -f $BuildDigest' in frontend
    assert "普通源码变化只同步受控工作区输入；依赖视图和 node_modules 不重装" in frontend
    assert 'Invoke-External "frontend-test"' in _text(MODULE_ROOT / "commands.ps1")
    assert 'Push-Location -LiteralPath $frontend' not in frontend
    for legacy in ("node_modules", "dist", "tsconfig.tsbuildinfo"):
        assert f'(Join-Path $frontend "{legacy}")' in frontend
    assert "JIEJIAN_PACKAGE_FRONTEND_DIR" in package + hook
    assert 'version == "editable"' in hook
    assert not (ROOT / "scripts" / "hatch_build.py").exists()


def test_sample_test_routes_to_real_start_cmd_with_a_fresh_var_directory() -> None:
    dev = _text(DEV)
    function = _text(MODULE_ROOT / "sample-test.ps1")
    package_root = MODULE_ROOT / "sample_test"
    driver_path = package_root / "driver.py"
    official_path = package_root / "official.py"
    driver = _text(driver_path)
    official = _text(official_path)
    assert '"sample-test" { Invoke-SampleTest $toolchain }' in dev
    assert "Prepare-SourceRuntime" not in function
    assert "Exit-PrepareLock" in function
    assert '"test\\sample-test\\{0}"' in function
    assert '"scripts\\dev\\sample_test\\driver.py"' in function
    assert '"official", "validation", "competition", "all"' in function
    assert '"--suite"' in function
    assert "Resolve-DevelopmentNode $Toolchain $true" in function
    assert '"--source-receipt"' not in function
    assert '"--frontend-dir"' not in function
    assert "_start_product(root, var_dir)" in official
    assert 'root / "start.cmd"' in official
    assert 'CONTROL_PORT = 8765' in official
    assert '"L5_CONTROL_PORT_OCCUPIED"' in official
    start_product = official[
        official.index("def _start_product(") : official.index("def _wait_product_ready(")
    ]
    run_cli = official[
        official.index("def _run_cli(") : official.index("def _assert_cli_equivalence(")
    ]
    assert '"product.backend.cli"' not in start_product
    assert '"product.backend.cli"' in run_cli
    assert not (ROOT / "scripts" / "sample_test.py").exists()
    assert driver_path.is_file()
    assert official_path.is_file()
    assert "def _start_product(" not in driver
    assert "def run_suite(" in driver
    for name in ("adapter", "registry", "oracle", "validation", "windows"):
        assert (package_root / f"{name}.py").is_file()
    assert not tuple(MODULE_ROOT.glob("sample_test*.py"))
    assert "prepare_formal_project" not in function
    assert "_persist_export_recording" not in function
    assert '"JIEJIAN_VAR_DIR": str(var_dir)' in official
    assert "require_python_environment(environment)" in official
    assert "client.bind_page(page)" in official
    assert "context.cookies" not in official
    assert "prepare_formal_project" not in official
    assert "_persist_export_recording" not in official


def test_frontend_editor_reuses_only_controlled_dependency_workspace() -> None:
    workspace = json.loads((ROOT / "jiejian.code-workspace").read_text(encoding="utf-8"))
    settings = workspace["settings"]
    tsconfig = json.loads((ROOT / "product" / "frontend" / "tsconfig.json").read_text(encoding="utf-8"))
    plugin = tsconfig["compilerOptions"]["plugins"][0]
    implementation = _text(ROOT / "scripts" / "editor" / "typescript-plugins" / "jiejian-controlled-workspace-resolver" / "index.cjs")
    verifier = _text(ROOT / "scripts" / "editor" / "verify-controlled-workspace-resolver.cjs")
    assert settings["js/ts.tsdk.path"].startswith("var/development/frontend/workspace/node_modules/typescript/")
    assert "js/ts.tsserver.pluginPaths" not in settings
    assert plugin == {"name": "jiejian-controlled-workspace-resolver", "sourceRoot": ".", "workspaceRoot": "../../var/development/frontend/workspace"}
    assert "resolveModuleNameLiterals" in implementation
    assert "ts.resolveModuleName" in implementation
    assert "Install-FrontendEditorPlugin $workspace" in _text(MODULE_ROOT / "frontend.ps1")
    assert 'Invoke-External "frontend-editor"' in _text(MODULE_ROOT / "commands.ps1")
    assert "PermissionCheckPage.test.tsx" in verifier
    assert "StartCheckPage.test.tsx" not in verifier
    assert not (ROOT / "product" / "frontend" / "node_modules").exists()


def test_external_command_wrapper_preserves_single_argument_arrays() -> None:
    assert "[string[]]$arguments" in _text(MODULE_ROOT / "common.ps1")


def test_development_powershell_modules_parse_and_keep_utf8_bom() -> None:
    files = (DEV, *sorted(MODULE_ROOT.glob("*.ps1")))
    for path in files:
        literal = str(path).replace("'", "''")
        command = "$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseFile('{0}',[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count -gt 0){{exit 1}}".format(literal)
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
        assert result.returncode == 0, f"{path}\n{result.stdout}{result.stderr}"
        assert path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_source_runtime_keeps_browser_frontend_database_order() -> None:
    source = _text(MODULE_ROOT / "prepare.ps1")
    runtime = source[source.index("function Prepare-SourceRuntime") :]
    assert runtime.index("Prepare-Chromium") < runtime.index("Prepare-SourceFrontend") < runtime.index("Prepare-Database")
    assert 'Write-PrepareStatus "database" "start"' in source
    assert 'Write-PrepareStatus "database" "done"' in source


def test_fresh_var_reuses_only_repository_development_tools() -> None:
    dev = _text(DEV)
    start = _text(ROOT / "scripts" / "start.ps1")
    common = _text(MODULE_ROOT / "common.ps1")
    python = _text(MODULE_ROOT / "python.ps1")
    frontend = _text(MODULE_ROOT / "frontend.ps1")
    startup = _text(ROOT / "scripts" / "startup" / "source.ps1")
    assert '$script:DevelopmentRoot = [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot "var\\development"))' in dev
    assert '$script:DevelopmentRoot = [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot "var\\development"))' in start
    assert 'Join-Path $script:DevelopmentRoot ("tools\\uv\\{0}\\{1}"' in python
    assert 'Join-Path $script:DevelopmentRoot "cache\\uv"' in python
    assert 'Join-Path $script:DevelopmentRoot "cache\\uv"' in startup
    assert 'Join-Path $script:DevelopmentRoot "tools\\playwright"' in python
    assert 'Join-Path $script:DevelopmentRoot ("tools\\node\\{0}\\{1}"' in frontend
    assert 'Join-Path $script:DevelopmentRoot ("tools\\pnpm\\{0}"' in frontend
    assert 'Join-Path $script:DevelopmentRoot "cache\\pnpm-store"' in frontend
    assert 'Join-Path $script:DevelopmentRoot "frontend\\workspace"' in frontend
    assert 'Join-Path $script:DevelopmentRoot ("frontend\\builds\\{0}"' in frontend
    assert 'Join-Path $script:VarDir "runtime\\build\\frontend-receipt.json"' in frontend
    assert 'Join-Path $script:VarDir "runtime\\frontend"' in frontend
    assert '$script:StatePath = Join-Path $script:DevelopmentRoot "state\\development-state.json"' in dev
    assert 'Join-Path $script:DevelopmentRoot "locks\\prepare.lock"' in common
    assert '$env:JIEJIAN_VAR_DIR = $script:VarDir' in python + startup
    assert '$script:StatePath = Join-Path $script:StartupDir "prepare-state.json"' in start


def test_browser_download_stops_after_no_progress_and_requests_user_action(tmp_path: Path) -> None:
    prepare = MODULE_ROOT / "prepare.ps1"
    stalled = tmp_path / "stalled-download"
    command = (
        f". {_powershell_literal(prepare)};"
        "function Fail-Development { param($Stage,$Message,$Recovery); throw ($Stage+'|'+$Message+'|'+$Recovery) };"
        f"$invocation=@({_powershell_literal(POWERSHELL)},'-NoLogo','-NoProfile','-Command','Start-Sleep -Seconds 10');"
        "$watch=[Diagnostics.Stopwatch]::StartNew();$message='';"
        f"try{{Invoke-ExternalWithProgressTimeout 'playwright' $invocation {_powershell_literal(stalled)} 1 '请检查网络后重试'}}catch{{$message=$_.Exception.Message}}finally{{$watch.Stop()}};"
        "[pscustomobject]@{elapsed=$watch.Elapsed.TotalSeconds;message=$message}|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(result.stdout.strip().splitlines()[-1])
    assert record["elapsed"] < 5
    assert "网络下载连续 1 秒没有写入新数据，已停止本次等待" in record["message"]
    assert "请检查网络后重试" in record["message"]


def test_browser_download_uses_var_temp_and_restores_process_temp() -> None:
    source = _text(MODULE_ROOT / "prepare.ps1")
    chromium = source[source.index("function Prepare-Chromium") : source.index("function Prepare-Database")]
    assert 'cache\\downloads\\playwright' in chromium
    assert 'foreach ($name in @("TEMP", "TMP"))' in chromium
    assert chromium.count('[Environment]::SetEnvironmentVariable($name') == 3
    assert "Invoke-ExternalWithProgressTimeout" in chromium
    assert "$treeStopExitCode -ne 0" in source
