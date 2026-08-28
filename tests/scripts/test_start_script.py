# 验证启动脚本、启动协议、准备阶段展示与终端回退边界。

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[2]
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


def _powershell_literal(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def test_product_start_prepares_current_repository_without_wheel() -> None:
    source = _text(START)
    assert '"source.ps1"' in source
    assert "Prepare-SourceRuntime" in source
    assert "Confirm-SourceFrontend" in source
    assert "Release" not in source
    assert "Wheel" in source
    assert "Get-ReleaseWheel" not in source
    assert "Prepare-ReleasePython" not in source


def test_source_receipt_requires_editable_repository_shared_build_and_instance_frontend() -> None:
    source = _text(SOURCE)
    prepare = _text(PREPARE)
    frontend = _text(ROOT / "scripts" / "dev" / "frontend.ps1")
    assert '"prepare"' in source
    assert "project_distribution.editable" in source
    assert "project_distribution.source_root" in source
    assert 'runtime\\frontend' in source
    assert 'runtime\\source\\receipt.json' in source
    assert 'JIEJIAN_RUNTIME_MODE = "development"' in source
    assert "Get-ReleaseWheel" not in source
    assert "pip install" not in source
    assert "frontend-receipt.json" in frontend
    assert 'DevelopmentRoot "frontend\\workspace"' in frontend
    assert 'DevelopmentRoot ("frontend\\builds\\{0}"' in frontend
    assert 'VarDir "runtime\\frontend"' in frontend
    assert "dependency_digest" in frontend
    assert "build_digest" in frontend
    assert "$buildHit" in frontend
    runtime = prepare[prepare.index("function Prepare-SourceRuntime") :]
    assert runtime.index("Prepare-Database") < runtime.index("Write-SourceReceipt")


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


def test_startup_uses_new_database_and_frontend_paths() -> None:
    start = _text(START)
    prepare = _text(PREPARE)
    assert "default_database_path" in prepare
    assert 'Join-Path $script:VarDir "jiejian.db"' not in prepare
    assert '"--frontend-dir", $script:FrontendDist' in start
    assert '"--frontend-dir", (Join-Path $script:ProjectRoot' not in start
    assert 'runtime\\frontend' in _text(ROOT / "scripts" / "dev" / "frontend.ps1")
    package = _text(ROOT / "scripts" / "dev" / "package.ps1")
    assert 'DevelopmentRoot "release"' in package
    assert 'releaseRoot "artifacts"' in package
    assert 'JIEJIAN_FRONTEND_OUT_DIR' in _text(ROOT / "product" / "frontend" / "vite.config.ts")
    assert 'JIEJIAN_FRONTEND_CACHE_DIR' in _text(ROOT / "product" / "frontend" / "vite.config.ts")


def test_serve_status_protocol_never_maps_still_starting_to_browser_failure() -> None:
    runtime = _text(RUNTIME)
    system = _text(ROOT / "product" / "backend" / "cli" / "commands" / "system.py")
    assert "__JIEJIAN_SERVE_READY__" not in runtime + system
    assert "__JIEJIAN_SERVE_STATUS__" in runtime + system
    for status in ("still-starting", "ready-browser-opened", "ready-browser-open-failed", "startup-failed"):
        assert status in runtime + system
    assert "界鉴启动时间较长，仍在准备，请稍候" in runtime
    assert "界鉴已经启动，但未能自动打开网页" in runtime


def test_startup_powershell_files_parse_and_keep_utf8_bom() -> None:
    files = (START, *sorted(STARTUP.glob("*.ps1")))
    for path in files:
        literal = str(path).replace("'", "''")
        command = "$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseFile('{0}',[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count -gt 0){{exit 1}}".format(literal)
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
        assert result.returncode == 0, f"{path}\n{result.stdout}{result.stderr}"
        assert path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_root_batch_is_ascii_without_bom_and_preserves_exit_code() -> None:
    payload = START_CMD.read_bytes()
    source = payload.decode("ascii")
    assert not payload.startswith(b"\xef\xbb\xbf")
    assert '"%POWERSHELL_EXE%"' in source
    assert "%*" in source
    assert 'set "START_EXIT=%ERRORLEVEL%"' in source
    assert "exit /b %START_EXIT%" in source
    assert "pause >nul" in source


def test_display_result_keeps_chinese_labels_and_selection_hint() -> None:
    presentation = _text(PRESENTATION)
    assert "↑ ↓ 选择" in presentation
    assert "Enter 确认" in presentation
    assert '"图形界面"' in presentation
    assert '"命令行"' in presentation
    assert '"仅完成环境准备"' in presentation


def test_prepare_status_markers_follow_the_six_real_stage_order() -> None:
    dev = _text(DEV := ROOT / "scripts" / "dev.ps1")
    prepare = _text(PREPARE)
    runtime = _text(RUNTIME)
    presentation = _text(PRESENTATION)
    tokens = ("toolchain", "python", "browser", "frontend-dependencies", "frontend-build", "database")
    assert 'function Write-PrepareStatus' in _text(ROOT / "scripts" / "dev" / "common.ps1")
    positions = [dev.index(f'"dev\\{name}.ps1"') for name in ("common", "python", "frontend", "prepare", "package", "commands")]
    assert positions == sorted(positions)
    marker_positions = [prepare.index(f'Write-PrepareStatus "{token}" "start"') for token in ("browser", "database")]
    assert marker_positions == sorted(marker_positions)
    runtime_function = prepare[prepare.index("function Prepare-SourceRuntime") :]
    assert runtime_function.index("Prepare-Chromium") < runtime_function.index("Prepare-SourceFrontend") < runtime_function.index("Prepare-Database")
    assert runtime.count("^__JIEJIAN_PREPARE_STATUS__:(toolchain|python|browser|frontend-dependencies|frontend-build|database):(start|done)$") == 1
    assert "Handle-PrepareStatus $line" in runtime
    assert "[1/6]" not in _text(START)
    for label in ("准备工具链", "准备 Python", "准备浏览器", "准备界面", "检查本地数据", "启动界鉴"):
        assert label in _text(START) or label in runtime
    assert "DisplaySpinnerStartedAt" in presentation
    assert "DisplaySpinnerStopEvent" in _text(START)
    assert "DisplaySpinnerStopEvent" in presentation
    assert "{2}s" in presentation


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


def test_permanent_startup_output_stops_wait_indicator_first() -> None:
    presentation = _text(PRESENTATION)
    runtime = _text(RUNTIME)
    start = _text(START)
    display_result = presentation[presentation.index("function Write-DisplayResult") : presentation.index("function Get-WaitIndicatorLabel")]
    complete_stage = presentation[presentation.index("function Complete-DisplayStage") : presentation.index("function Get-DisplayCellWidth")]
    fail_start = runtime[runtime.index("function Fail-Start") : runtime.index("function Set-PrepareDisplayTask")]
    assert display_result.index("Stop-WaitIndicator") < display_result.index("Write-Host")
    assert complete_stage.index("Stop-WaitIndicator") < complete_stage.index("Write-Host")
    assert fail_start.index("Stop-WaitIndicator") < fail_start.index("Write-Host")
    assert "Stop-WaitIndicator" in start[start.index("} finally {") :]


def test_prepare_done_stops_indicator_before_writing_permanent_result() -> None:
    command = (
        f". {_powershell_literal(PRESENTATION)};. {_powershell_literal(RUNTIME)};"
        "$script:Events=New-Object 'System.Collections.Generic.List[string]';"
        "function Stop-WaitIndicator{$null=$script:Events.Add('stop')};function Start-WaitIndicator{};"
        "function Write-Host{param([Parameter(Position=0)][object]$Object,[object]$ForegroundColor,[switch]$NoNewline,[object]$Separator);$null=$script:Events.Add('write')};"
        "$script:PrepareStatusOrder=@('toolchain','python','browser','frontend-dependencies','frontend-build','database');$script:PrepareStatusIndex=0;$script:PrepareStatusState=@{};"
        "$script:DisplayStageTimer=$null;$script:DisplayStageIndex=0;$script:DisplayUnicode=$false;$script:DisplayInteractive=$false;"
        "[void](Handle-PrepareStatus '__JIEJIAN_PREPARE_STATUS__:toolchain:start');$script:Events.Clear();$script:DisplayInteractive=$true;"
        "[void](Handle-PrepareStatus '__JIEJIAN_PREPARE_STATUS__:toolchain:done');"
        "[pscustomobject]@{events=@($script:Events);index=$script:PrepareStatusIndex}|ConvertTo-Json -Depth 3 -Compress"
    )
    result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(result.stdout.strip().splitlines()[-1])
    assert record["index"] == 2
    assert record["events"][0] == "stop"
    assert record["events"].index("stop") < record["events"].index("write")


def test_normal_start_no_longer_prints_runtime_summary_but_keeps_diagnostics() -> None:
    start = _text(START)
    product = _text(STARTUP / "product.ps1")
    source = _text(SOURCE)
    assert "Write-RuntimeSummary" not in start + product
    assert "当前界鉴运行环境" not in start + product
    assert "Write-PythonEnvironment" in product
    assert "Write-Startup" in product[product.index("function Write-PythonEnvironment") : product.index("function Invoke-Python")]
    assert "receipt.json" in source
    assert '"doctor"' in start
    for text in ("VarDir", "jiejian status", "jiejian system doctor"):
        assert text in _text(PRESENTATION)


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


def test_banner_keeps_six_lines_wide_j_glyphs_and_safe_fallback() -> None:
    presentation = _text(PRESENTATION)
    command = "$script:DisplayUnicode=$true;$script:DisplayTrueColor=$false;" + f". {_powershell_literal(PRESENTATION)};Write-Banner"
    result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    output = [line.rstrip() for line in result.stdout.splitlines() if line.strip()]
    banner = output[:6]
    assert len(output) == 7
    assert len(banner) == 6
    assert all(len(line) < 72 for line in banner)
    assert banner[0].count("     ██╗") == 2
    assert banner[3].count("██   ██║") == 2
    assert banner[4].count("╚█████╔╝") == 2
    assert banner[5].count("╚════╝") == 2
    assert output[-1].strip() == "界鉴 · 安全意图一致性验证"
    assert 'Write-Host "JIEJIAN"' in presentation
    assert "WindowSize.Width -ge 72" in _text(START)
    assert "SupportsVirtualTerminal" in _text(START)
