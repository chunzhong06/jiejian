# 验证启动脚本、启动协议、准备阶段展示与终端回退边界。
from __future__ import annotations

import json

import os

import shutil

import subprocess

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]

START = ROOT / "scripts" / "start.ps1"

START_CMD = ROOT / "start.cmd"

STARTUP = ROOT / "scripts" / "startup"

SOURCE = STARTUP / "source.ps1"

RUNTIME = STARTUP / "runtime.ps1"

PRESENTATION = STARTUP / "presentation.ps1"

PREPARE = ROOT / "scripts" / "dev" / "prepare.ps1"

POWERSHELL = shutil.which("powershell") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")

@pytest.mark.parametrize("prefer_core", [False, True])
@pytest.mark.parametrize("exit_code", [0, 17])
def test_cmd_selects_real_shell_and_forwards_arguments(tmp_path: Path, prefer_core: bool, exit_code: int) -> None:
    core = shutil.which("pwsh")
    if core is None:
        candidate = Path(os.environ["LOCALAPPDATA"]) / "Programs/PowerShell/7/pwsh.exe"
        core = str(candidate) if candidate.is_file() else None
    if prefer_core and core is None:
        pytest.skip("PowerShell 7 is not installed")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    batch = tmp_path / "start.cmd"
    batch.write_bytes(START_CMD.read_bytes())
    output = tmp_path / "selected.json"
    (scripts / "start.ps1").write_text(
        "# 验证批处理真实选壳和参数转交，不运行产品准备。\n"
        "param([string]$ProbeOutput)\n"
        "[pscustomobject]@{major=$PSVersionTable.PSVersion.Major;output=$ProbeOutput}|"
        "ConvertTo-Json -Compress|Set-Content -LiteralPath $ProbeOutput -Encoding UTF8\n"
        f"exit {exit_code}\n", encoding="utf-8-sig",
    )
    environment = os.environ.copy()
    windows = Path(os.environ["SystemRoot"])
    environment["PATH"] = os.pathsep.join(
        ([str(Path(core).parent)] if prefer_core else []) + [str(windows / "System32"), str(windows)]
    )
    # 模拟普通 Windows 调用者，避免测试宿主的 Core 模块抢先覆盖 5.1 内置模块。
    environment.pop("PSMODULEPATH", None)
    result = subprocess.run(
        [str(windows / "System32/cmd.exe"), "/d", "/c", str(batch), "-ProbeOutput", str(output)],
        cwd=tmp_path, env=environment, input="\n", text=True, capture_output=True, timeout=20, check=False,
    )
    assert result.returncode == exit_code, result.stdout + result.stderr
    record = json.loads(output.read_text(encoding="utf-8-sig"))
    assert record == {"major": 7 if prefer_core else 5, "output": str(output)}

def _powershell_literal(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"

def test_source_receipt_follows_current_relocated_repository(tmp_path: Path) -> None:
    project_root = (tmp_path / "relocated-repository").resolve()
    var_dir = (tmp_path / "runtime-var").resolve()
    frontend = var_dir / "runtime" / "frontend"
    python = var_dir / "runtime" / "python" / "python.exe"
    environment_path = var_dir / "runtime" / "python"
    uv = var_dir / "runtime" / "tools" / "uv.exe"
    chromium = var_dir / "runtime" / "browsers" / "chrome.exe"
    browsers = var_dir / "runtime" / "browsers"
    receipt_path = var_dir / "runtime" / "source" / "receipt.json"
    for path in (project_root, frontend, environment_path, uv.parent, browsers):
        path.mkdir(parents=True, exist_ok=True)
    for path in (frontend / "index.html", python, uv, chromium):
        path.write_text("test", encoding="utf-8")
    receipt = {
        "schema_version": "1", "project_root": str(project_root), "var_dir": str(var_dir), "runtime_mode": "development",
        "python": {"executable": str(python), "version": "3.13.test", "environment_path": str(environment_path), "environment_type": "conda", "runtime_fingerprint": "relocated-test", "report": {"ok": True, "project_distribution": {"editable": True, "source_root": str(project_root)}}},
        "uv": {"executable": str(uv), "version": "test"}, "node": {"executable": "", "version": ""}, "pnpm": {"executable": "", "version": ""},
        "playwright": {"executable": str(chromium), "browsers_path": str(browsers)}, "frontend": {"dist": str(frontend), "dependencies": "test", "build_state": "test"},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    command = (
        "function Fail-Start { param($Code,$Stage,$Message,$Recovery); throw ($Stage + ':' + $Message) };"
        "function Get-RecoveryCommand { return 'recover' };"
        f"$script:ProjectRoot={_powershell_literal(project_root)};"
        f"$script:VarDir={_powershell_literal(var_dir)};"
        f"$script:ToolchainPath={_powershell_literal(project_root / 'product/config/toolchain.json')};"
        f". {_powershell_literal(SOURCE)};Import-SourceReceipt;"
        "if (-not (Test-ExactPath $env:JIEJIAN_PROJECT_ROOT $script:ProjectRoot)) { exit 91 };Write-Output 'RECEIPT_OK'"
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    accepted = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert "RECEIPT_OK" in accepted.stdout
    receipt["project_root"] = str(ROOT.resolve())
    receipt["python"]["report"]["project_distribution"]["source_root"] = str(ROOT.resolve())
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    rejected = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    assert rejected.returncode != 0

@pytest.mark.parametrize('status,ready,failed',[
    ('still-starting',False,False),('ready-browser-opened',True,False),
    ('ready-browser-open-failed',True,False),('startup-failed',False,True),
    ('unknown',False,False),('invalid-ready-browser-opened',False,False),
])
def test_serve_status_uses_exact_events_to_drive_readiness(tmp_path,powershell_record,status,ready,failed):
    import sys
    probe=tmp_path/'serve-events.py';probe.write_text('print('+repr('__JIEJIAN_SERVE_STATUS__:'+status)+')',encoding='utf-8')
    command=(f". {_powershell_literal(RUNTIME)};$Port=38765;$script:LogPath={_powershell_literal(tmp_path/'serve.log')};"
        "$script:Utf8Encoding=New-Object Text.UTF8Encoding($false);$script:ServeReadyObserved=$false;$script:ServeStartupFailed=$false;"
        "function Write-Startup {};function Start-WaitIndicator {};function Stop-WaitIndicator {};function Set-StartupStatus {};"
        "function Fail-Start {$script:failure=$args[0]};"
        f"Invoke-External -Stage 'serve' -Command @({_powershell_literal(Path(sys.executable))},{_powershell_literal(probe)}) -Arguments @() -FailureCode 50 -Recovery 'local';"
        "[pscustomobject]@{ready=$script:ServeReadyObserved;failed=$script:ServeStartupFailed;error=$script:failure}|ConvertTo-Json -Compress")
    result=powershell_record(command)
    assert result['ready'] is ready and result['failed'] is failed
    assert (result['error'] is not None) is failed


def test_startup_powershell_files_parse_and_keep_utf8_bom() -> None:
    files = (START, *sorted(STARTUP.glob("*.ps1")))
    for path in files:
        literal = str(path).replace("'", "''")
        command = "$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseFile('{0}',[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count -gt 0){{exit 1}}".format(literal)
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
        assert result.returncode == 0, f"{path}\n{result.stdout}{result.stderr}"
        assert path.read_bytes().startswith(b"\xef\xbb\xbf"), path

def test_root_batch_encoding_is_readable_by_windows_cmd():
    payload=START_CMD.read_bytes()
    payload.decode('ascii')
    assert not payload.startswith(b'\xef\xbb\xbf')


def test_wait_indicator_child_exits_on_named_event_without_late_output(tmp_path: Path) -> None:
    stdout = tmp_path / "spinner.out"
    stderr = tmp_path / "spinner.err"
    command = (
        "$ErrorActionPreference='Stop';"
        "$eventName='Local\\JiejianWait-Test-'+$PID+'-'+[guid]::NewGuid().ToString('N');$created=$false;"
        "$event=[Threading.EventWaitHandle]::new($false,[Threading.EventResetMode]::ManualReset,$eventName,[ref]$created);$process=$null;"
        "try{$shell=(Get-Process -Id $PID).Path;"
        f"$arguments='-NoLogo -NoProfile -ExecutionPolicy Bypass -File \"'+{_powershell_literal(START)}+'\" -DisplaySpinnerProcess -DisplaySpinnerStage python -DisplaySpinnerStartedAt '+[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()+' -DisplaySpinnerStopEvent '+$eventName+' -DisplaySpinnerAscii';"
        f"$process=Start-Process -FilePath $shell -ArgumentList $arguments -RedirectStandardOutput {_powershell_literal(stdout)} -RedirectStandardError {_powershell_literal(stderr)} -PassThru;"
        "$deadline=[DateTime]::UtcNow.AddSeconds(5);do{if($process.HasExited){break};Start-Sleep -Milliseconds 50}while(((-not (Test-Path -LiteralPath '"
        + str(stdout).replace("'", "''")
        + "')) -or (Get-Item -LiteralPath '"
        + str(stdout).replace("'", "''")
        + "').Length -eq 0) -and [DateTime]::UtcNow -lt $deadline);"
        f"$before=if(Test-Path -LiteralPath {_powershell_literal(stdout)}){{(Get-Item -LiteralPath {_powershell_literal(stdout)}).Length}}else{{0}};"
        "$null=$event.Set();$graceful=$process.WaitForExit(2000);"
        f"$atExit=if(Test-Path -LiteralPath {_powershell_literal(stdout)}){{(Get-Item -LiteralPath {_powershell_literal(stdout)}).Length}}else{{0}};"
        f"Start-Sleep -Milliseconds 180;$after=if(Test-Path -LiteralPath {_powershell_literal(stdout)}){{(Get-Item -LiteralPath {_powershell_literal(stdout)}).Length}}else{{0}};"
        "$process.Dispose();$process=$null;$event.Dispose();$event=$null;$eventStillExists=$true;"
        "try{$probe=[Threading.EventWaitHandle]::OpenExisting($eventName);$probe.Dispose()}catch{$eventStillExists=$false};"
        f"$stderrText=$(if(Test-Path -LiteralPath {_powershell_literal(stderr)}){{Get-Content -LiteralPath {_powershell_literal(stderr)} -Raw}}else{{''}});"
        "[pscustomobject]@{created=$created;graceful=$graceful;before=$before;stable=($atExit -eq $after);event_still_exists=$eventStillExists;stderr=$stderrText}|ConvertTo-Json -Compress}"
        "finally{if($null -ne $process){if(-not $process.HasExited){Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue};$process.Dispose()};if($null -ne $event){$event.Dispose()}}"
    )
    result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(result.stdout.strip().splitlines()[-1])
    assert record["created"] is True
    assert record["graceful"] is True
    assert record["before"] > 0
    assert record["stable"] is True
    assert record["event_still_exists"] is False
    assert not record["stderr"]

def test_wait_indicator_uses_force_only_after_graceful_timeout() -> None:
    command = (
        f". {_powershell_literal(PRESENTATION)};"
        "function Clear-WaitIndicatorLine{$null=$script:Events.Add('clear')};"
        "function Stop-Process{[CmdletBinding()]param([int]$Id,[switch]$Force);$null=$script:Events.Add('force');[void]($script:WaitIndicatorProcess.HasExited=$true)};"
        "function New-FakeProcess{$value=[pscustomobject]@{Id=42;HasExited=$false};"
        "$value|Add-Member ScriptMethod WaitForExit {param($Milliseconds=$null);if($null -eq $Milliseconds){$null=$script:Events.Add('wait-final');[void]($this.HasExited=$true);return};$null=$script:Events.Add(('wait-'+$Milliseconds));if($script:FakeMode -eq 'normal'){$this.HasExited=$true;return $true};return $false};"
        "$value|Add-Member ScriptMethod Dispose {$null=$script:Events.Add('process-dispose')};return $value};"
        "function New-FakeEvent{$value=[pscustomobject]@{};$value|Add-Member ScriptMethod Set {$null=$script:Events.Add('signal');return $true};$value|Add-Member ScriptMethod Dispose {$null=$script:Events.Add('event-dispose')};return $value};"
        "function Invoke-Fake([string]$Mode){$script:FakeMode=$Mode;$script:Events=New-Object 'System.Collections.Generic.List[string]';$script:WaitIndicatorProcess=New-FakeProcess;$script:WaitIndicatorStopEvent=New-FakeEvent;$script:WaitIndicatorFallbackActive=$false;Stop-WaitIndicator;"
        "return [pscustomobject]@{events=@($script:Events);process_cleared=($null -eq $script:WaitIndicatorProcess);event_cleared=($null -eq $script:WaitIndicatorStopEvent)}};"
        "[pscustomobject]@{normal=(Invoke-Fake 'normal');timeout=(Invoke-Fake 'timeout')}|ConvertTo-Json -Depth 5 -Compress"
    )
    result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(result.stdout.strip().splitlines()[-1])
    assert record["normal"]["events"] == ["signal", "wait-2000", "clear", "process-dispose", "event-dispose"]
    assert record["timeout"]["events"] == ["signal", "wait-2000", "force", "wait-final", "clear", "process-dispose", "event-dispose"]
    assert record["normal"]["process_cleared"] is True and record["normal"]["event_cleared"] is True
    assert record["timeout"]["process_cleared"] is True and record["timeout"]["event_cleared"] is True

def test_prepare_status_parser_accepts_only_contiguous_whitelisted_events() -> None:
    command = (
        "$script:PrepareStatusOrder=@('toolchain','python','browser','frontend-dependencies','frontend-build','database');"
        "$script:PrepareStatusIndex=0;$script:PrepareStatusState=@{};"
        f". {_powershell_literal(RUNTIME)};"
        "function Start-DisplayStage{};function Stop-WaitIndicator{};function Start-WaitIndicator{};function Write-DisplayResult{};function Complete-DisplayStage{};"
        "$lines=@('__JIEJIAN_PREPARE_STATUS__:python:start','__JIEJIAN_PREPARE_STATUS__:toolchain:start','__JIEJIAN_PREPARE_STATUS__:toolchain:start','__JIEJIAN_PREPARE_STATUS__:toolchain:done:extra','__JIEJIAN_PREPARE_STATUS__:toolchain:done','__JIEJIAN_PREPARE_STATUS__:python:start','__JIEJIAN_PREPARE_STATUS__:python:done','__JIEJIAN_PREPARE_STATUS__:browser:start','__JIEJIAN_PREPARE_STATUS__:browser:done','__JIEJIAN_PREPARE_STATUS__:frontend-dependencies:start','__JIEJIAN_PREPARE_STATUS__:frontend-dependencies:done','__JIEJIAN_PREPARE_STATUS__:frontend-build:start','__JIEJIAN_PREPARE_STATUS__:frontend-build:done','__JIEJIAN_PREPARE_STATUS__:database:start','__JIEJIAN_PREPARE_STATUS__:database:done');"
        "foreach($line in $lines){[void](Handle-PrepareStatus $line)};Write-Output ('INDEX=' + $script:PrepareStatusIndex)"
    )
    result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "INDEX=12" in result.stdout

pytestmark = [pytest.mark.level3]
