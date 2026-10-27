# 验证开发总控台模块装配、命令合同、受控工作区与调用者环境恢复。
from __future__ import annotations
import pytest

import json

import os

import shutil

import subprocess

from pathlib import Path

ROOT = Path(__file__).parents[3]

DEV = ROOT / "scripts" / "dev.ps1"

MODULE_ROOT = ROOT / "scripts" / "development"

POWERSHELL = shutil.which("pwsh") or shutil.which("powershell") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")

def _powershell_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"

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

def test_python_sync_digest_tracks_editable_package_topology(tmp_path, powershell_record):
    for relative in ['product/backend/__init__.py','product/protocols/__init__.py','pyproject.toml','uv.lock']:
        path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('original',encoding='utf-8')
    package=tmp_path/'product/backend/new_package/__init__.py'
    command=(f". {_powershell_literal(ROOT/'scripts/development/files.ps1')};. {_powershell_literal(MODULE_ROOT/'context.ps1')};. {_powershell_literal(MODULE_ROOT/'python.ps1')};"
        f"$script:ProjectRoot={_powershell_literal(tmp_path)};$script:Utf8NoBom=New-Object Text.UTF8Encoding($false);"
        "$before=Get-PathSetDigest @(Get-ProjectPackageTopologyInputs);$sync=Get-CombinedDigest @(Get-ProjectSyncInputs);"
        f"Set-Content -LiteralPath {_powershell_literal(tmp_path/'product/backend/__init__.py')} -Value 'changed';"
        "$same=Get-PathSetDigest @(Get-ProjectPackageTopologyInputs);$changedSync=Get-CombinedDigest @(Get-ProjectSyncInputs);"
        f"New-Item -ItemType Directory -Force -Path {_powershell_literal(package.parent)}|Out-Null;"
        f"Set-Content -LiteralPath {_powershell_literal(package)} -Value '# package';"
        "$added=Get-PathSetDigest @(Get-ProjectPackageTopologyInputs);"
        f"Remove-Item -LiteralPath {_powershell_literal(package)};"
        "$removed=Get-PathSetDigest @(Get-ProjectPackageTopologyInputs);"
        "[pscustomobject]@{content_ignored=($before -eq $same);version_tracked=($sync -ne $changedSync);package_tracked=($before -ne $added);removed_restored=($before -eq $removed)}|ConvertTo-Json -Compress")
    assert powershell_record(command)==dict(content_ignored=True,version_tracked=True,package_tracked=True,removed_restored=True)


def test_missing_cache_reuses_healthy_minimal_conda_but_not_changed_contract(tmp_path: Path) -> None:
    # 清空 var 不应触发外部环境更新；未来增加依赖或明确 bootstrap 仍须更新。
    definition = tmp_path / "environment.yml"
    baseline = (MODULE_ROOT / "environment.yml").read_text(encoding="utf-8")
    for content, mode, expected_updates in ((baseline, "auto", 0), (baseline + "  - pip\n", "auto", 1), (baseline, "force", 1)):
        definition.write_text(content, encoding="utf-8")
        command = (
            f". {_powershell_literal(MODULE_ROOT / 'python.ps1')};"
            f"$script:EnvironmentPath={_powershell_literal(definition)};"
            "$script:updates=0;"
            f"function Resolve-CondaPrefix {{ $script:Conda='conda'; return {_powershell_literal(tmp_path / 'jiejian_env')} }};"
            "function Test-CondaPython { return $true };"
            "function Get-FileDigest { return 'current' };"
            "function Get-StateValue { return $null };"
            "function Set-StateValue { param($name,$value) };"
            "function Invoke-External { $script:updates++ };"
            "function Fail-Development { throw 'unexpected failure' };"
            f"Ensure-Conda {mode};"
            "[pscustomobject]@{updates=$script:updates}|ConvertTo-Json -Compress"
        )
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout.strip().splitlines()[-1])["updates"] == expected_updates

def test_uv_archive_is_really_extracted_and_temporary_download_is_removed(tmp_path, powershell_record):
    import hashlib,zipfile
    archive=tmp_path/'local.zip'
    with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr('bundle/uv.exe',b'local executable fixture')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    command=(f". {_powershell_literal(ROOT/'scripts/development/files.ps1')};. {_powershell_literal(MODULE_ROOT/'context.ps1')};. {_powershell_literal(MODULE_ROOT/'python.ps1')};"
        f"$script:DevelopmentRoot={_powershell_literal(tmp_path/'development')};$script:Utf8NoBom=New-Object Text.UTF8Encoding($false);"
        "function Register-StartupTemporary {};"
        f"function Invoke-WebRequest {{param($Uri,$OutFile,[switch]$UseBasicParsing) Microsoft.PowerShell.Management\\Copy-Item -LiteralPath {_powershell_literal(archive)} -Destination $OutFile}};"
        "function Copy-Item {param($LiteralPath,$Destination,[switch]$Force) $script:extracted=[IO.File]::ReadAllText($LiteralPath);throw 'EXTRACTION_OBSERVED'};"
        f"$metadata=[pscustomobject]@{{asset='local.zip';sha256='{digest}'}};"
        "$tool=[pscustomobject]@{uv=[pscustomobject]@{version='local';windows=[pscustomobject]@{x64=$metadata;arm64=$metadata}}};"
        "try {Resolve-Uv $tool;exit 3}catch{if($_.Exception.Message -ne 'EXTRACTION_OBSERVED'){throw}};"
        "$remaining=@(Get-ChildItem -LiteralPath (Join-Path $script:DevelopmentRoot 'cache/downloads') -File);"
        "[pscustomobject]@{extracted=$script:extracted;temporary_empty=($remaining.Count -eq 0)}|ConvertTo-Json -Compress")
    assert powershell_record(command)==dict(extracted='local executable fixture',temporary_empty=True)


@pytest.mark.parametrize('update',[False,True])
def test_docs_uses_existing_python_without_full_prepare_or_uv(tmp_path, powershell_record, update):
    command=(f". {_powershell_literal(MODULE_ROOT/'python.ps1')};. {_powershell_literal(MODULE_ROOT/'commands.ps1')};"
        f"$script:ProjectRoot={_powershell_literal(ROOT)};"
        f"function Resolve-CondaPrefix {{{_powershell_literal(tmp_path)}}};function Test-CondaPython {{$true}};"
        "function Resolve-Uv {throw 'unexpected download'};function Sync-Project {throw 'unexpected sync'};"
        "function Invoke-External {param($Stage,$Invocation) $script:seen+=,@{stage=$Stage;args=@($Invocation)}};"
        f"$Update={'$true' if update else '$false'};$CommandArguments=@();$script:seen=@();Invoke-Docs;"
        "[pscustomobject]@{calls=@($script:seen)}|ConvertTo-Json -Depth 4 -Compress")
    calls=powershell_record(command)['calls']
    assert [call['stage'] for call in calls]==(['docs','docs-check'] if update else ['docs'])
    assert all(Path(call['args'][0])==tmp_path/'python.exe' and '-B' in call['args'] for call in calls)
    assert ('--update' in calls[0]['args']) is update
    assert all('--update' not in call['args'] for call in calls[1:])


def _run_environment_restore_probe(*, raise_after_mutation: bool) -> dict[str, object]:
    common = ROOT / "scripts/development/session.ps1"
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

def test_frontend_build_failure_keeps_diagnostics_visible_through_receipt_assignment(tmp_path):
    command = (
        f". {_powershell_literal(MODULE_ROOT / 'frontend.ps1')};"
        f"$script:DevelopmentRoot={_powershell_literal(tmp_path)};"
        "$script:PnpmRunner=@('fixture');"
        "function Invoke-External { param($Stage,$Invocation) Write-Output 'FIXTURE_TYPE_DIAGNOSTIC';throw 'FIXTURE_BUILD_FAILED' };"
        f"try {{$receipt=Invoke-FrontendBuild {_powershell_literal(tmp_path)} {_powershell_literal(tmp_path / 'dist')};exit 3}}"
        "catch {if($_.Exception.Message -ne 'FIXTURE_BUILD_FAILED'){exit 4};Write-Output 'FAILURE_PRESERVED'}"
    )
    completed = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command],
                               cwd=ROOT, text=True, capture_output=True, check=False)
    assert completed.returncode == 0
    assert "FIXTURE_TYPE_DIAGNOSTIC" in completed.stdout
    assert "FAILURE_PRESERVED" in completed.stdout

def test_frontend_type_failure_stops_vitest_and_restores_location(tmp_path):
    command = (
        f". {_powershell_literal(MODULE_ROOT / 'commands.ps1')};"
        f"$script:DevelopmentRoot={_powershell_literal(tmp_path)};$script:VarDir=$script:DevelopmentRoot;"
        f"$script:ProjectRoot={_powershell_literal(ROOT)};$script:Node='fixture';$script:PnpmRunner=@('fixture');"
        "$script:calls=@();$before=(Get-Location).Path;"
        "function Remove-LegacyFrontendArtifacts {};function Get-FrontendSourceInputs {};"
        "function Get-FrontendDependencyDigest {'fixture'};function Prepare-FrontendWorkspace {};"
        f"function Get-FrontendWorkspace {{{_powershell_literal(tmp_path)}}};"
        "function Invoke-External {param($Stage,$Invocation) $script:calls+=$Stage;if($Stage -eq 'frontend-types'){throw 'TYPE_CONTRACT_FAILED'}};"
        "try {Invoke-FrontendTest $null;exit 3}catch{if($_.Exception.Message -ne 'TYPE_CONTRACT_FAILED'){exit 4}};"
        "[pscustomobject]@{calls=$script:calls;location_restored=((Get-Location).Path -eq $before)}|ConvertTo-Json -Compress"
    )
    completed = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT,
                               text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stdout
    record = json.loads(completed.stdout.strip().splitlines()[-1])
    assert record == {"calls": ["frontend-editor", "frontend-types"], "location_restored": True}

@pytest.mark.parametrize('arguments',[[],['one value','--literal']])
def test_external_command_wrapper_preserves_arguments(tmp_path, powershell_record, arguments):
    import sys
    probe=tmp_path/'one argument.py';probe.write_text('import json,sys;print(json.dumps({"args":sys.argv[1:]}))',encoding='utf-8')
    values=','.join(_powershell_literal(value) for value in [sys.executable,str(probe),*arguments])
    command=f". {_powershell_literal(MODULE_ROOT/'context.ps1')};Invoke-External 'probe' @({values})"
    assert powershell_record(command)=={'args':arguments}


def test_frontend_workspace_scope_invalidates_dependency_identity(tmp_path, powershell_record):
    frontend = tmp_path/'product/frontend'
    plugin = frontend/'tooling/editor-resolver'
    plugin.mkdir(parents=True)
    for name in ('package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml'):
        (frontend/name).write_text('{}', encoding='utf-8')
    (plugin/'package.json').write_text('{}', encoding='utf-8')
    (plugin/'index.cjs').write_text('module.exports={}', encoding='utf-8')
    command = (
        f". {_powershell_literal(MODULE_ROOT/'files.ps1')};"
        f". {_powershell_literal(MODULE_ROOT/'frontend-workspace.ps1')};"
        f"$script:ProjectRoot={_powershell_literal(tmp_path)};"
        "$script:Utf8NoBom=New-Object Text.UTF8Encoding($false);"
        "$tools=[pscustomobject]@{node=[pscustomobject]@{build_version='24'};pnpm=[pscustomobject]@{version='11'}};"
        "$first=Get-FrontendDependencyDigest $tools;"
        f"[IO.File]::WriteAllText({_powershell_literal(frontend/'pnpm-workspace.yaml')},\"packages:`n  - .`n\");"
        "$second=Get-FrontendDependencyDigest $tools;"
        "[pscustomobject]@{changed=$first -ne $second}|ConvertTo-Json -Compress"
    )
    assert powershell_record(command)['changed'] is True


def test_development_powershell_modules_parse_and_keep_utf8_bom() -> None:
    files = (DEV, ROOT/"scripts/start.ps1", *sorted(MODULE_ROOT.rglob("*.ps1")))
    for path in files:
        literal = str(path).replace("'", "''")
        command = "$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseFile('{0}',[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count -gt 0){{exit 1}}".format(literal)
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
        assert result.returncode == 0, f"{path}\n{result.stdout}{result.stderr}"
        assert path.read_bytes().startswith(b"\xef\xbb\xbf"), path

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

@pytest.mark.parametrize('download_fails',[False,True])
def test_browser_download_restores_temporary_environment(tmp_path, monkeypatch, powershell_record, download_fails):
    import sys
    from playwright.sync_api import sync_playwright
    browsers=tmp_path/'browsers';monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH',str(browsers))
    with sync_playwright() as runtime:executable=Path(runtime.chromium.executable_path)
    development=tmp_path/'development'
    install="throw 'DOWNLOAD_STOP'" if download_fails else f"New-Item -ItemType Directory -Force -Path {_powershell_literal(executable.parent)}|Out-Null;Set-Content -LiteralPath {_powershell_literal(executable)} -Value 'fixture'"
    command=(f". {_powershell_literal(MODULE_ROOT/'prepare.ps1')};$script:Python={_powershell_literal(sys.executable)};"
        f"$script:DevelopmentRoot={_powershell_literal(development)};$env:TEMP='original-temp';Remove-Item Env:TMP -ErrorAction SilentlyContinue;"
        "function Write-PrepareStatus {};function Fail-Development {param($Stage,$Message,$Recovery) throw $Message};"
        "function Invoke-ExternalWithProgressTimeout {param($Stage,$Invocation,$Root,$Seconds,$Recovery) "
        f"$script:download=@{{root=$Root;temp=$env:TEMP;tmp=$env:TMP}};{install}}};"
        "$failed=$false;try{Prepare-Chromium}catch{if($_.Exception.Message -ne 'DOWNLOAD_STOP'){throw};$failed=$true};"
        "[pscustomobject]@{download=$script:download;temp=$env:TEMP;tmp_absent=(-not [Environment]::GetEnvironmentVariables('Process').Contains('TMP'));failed=$failed}|ConvertTo-Json -Depth 3 -Compress")
    result=powershell_record(command)
    assert result['failed'] is download_fails
    assert result['temp']=='original-temp' and result['tmp_absent']
    expected=development/'cache/downloads/playwright'
    assert all(Path(value)==expected for value in result['download'].values())


pytestmark = [pytest.mark.level3]
