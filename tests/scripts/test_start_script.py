from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "start.ps1"
CMD_SCRIPT = ROOT / "start.cmd"
POWERSHELL_SCRIPTS = (SCRIPT, *sorted((ROOT / "scripts" / "startup").glob("*.ps1")))
POWERSHELL = shutil.which("powershell") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def _write_cmd(path: Path, body: str) -> None:
    path.write_text("@echo off\r\n" + body + "\r\n", encoding="ascii")


def _clean_conda_environment(env: dict[str, str]) -> None:
    for key in list(env):
        if key.upper().startswith("CONDA") or key.upper().startswith("_CE_"):
            env.pop(key, None)


def _make_shims(tmp_path: Path, *, conda: bool, uv: bool, existing_env: bool = False) -> tuple[Path, Path]:
    shim = tmp_path / "shims"
    state = tmp_path / "state"
    shim.mkdir()
    state.mkdir()
    log = tmp_path / "commands.log"
    migration_helper = tmp_path / "migration_helper.py"
    revision_helper = tmp_path / "revision_helper.py"
    migration_helper.write_text(
        "import os, sqlite3, sys\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[1])\n"
        "root.mkdir(parents=True, exist_ok=True)\n"
        "db = root / 'jiejian.db'\n"
        "conn = sqlite3.connect(db)\n"
        "conn.execute('create table if not exists alembic_version (version_num varchar(32) not null)')\n"
        "conn.execute('delete from alembic_version')\n"
        "if not os.environ.get('SHIM_INVALID_REVISION'):\n"
        "    conn.execute(\"insert into alembic_version(version_num) values ('0001_initial')\")\n"
        "conn.commit()\n"
        "conn.close()\n",
        encoding="utf-8",
    )
    revision_helper.write_text(
        "import sqlite3, sys\n"
        "conn = sqlite3.connect(sys.argv[1])\n"
        "row = conn.execute('select version_num from alembic_version').fetchone()\n"
        "print(row[0] if row and row[0] else 'missing')\n"
        "conn.close()\n",
        encoding="utf-8",
    )
    env_path = tmp_path / "conda-envs" / "jiejian_env"
    (env_path / "conda-meta").mkdir(parents=True)
    if existing_env:
        (state / "env-exists").write_text("1", encoding="ascii")

    _write_cmd(
        shim / "node.cmd",
        '>>"%SHIM_LOG%" echo node %*\nif "%1"=="--version" echo v22.12.0\nexit /b 0',
    )
    _write_cmd(
        shim / "pnpm.cmd",
        '>>"%SHIM_LOG%" echo pnpm %*\n'
        'if "%1"=="--version" echo 11.21.0\n'
        'if "%1"=="install" (if not exist node_modules\\.bin mkdir node_modules\\.bin& '
        '>node_modules\\.modules.yaml echo {& '
        '>>node_modules\\.modules.yaml echo   "storeDir": "%SHIM_STORE_DIR%"& '
        '>>node_modules\\.modules.yaml echo }& '
        '>node_modules\\.bin\\tsc.cmd echo @exit /b 0& '
        '>node_modules\\.bin\\vite.cmd echo @exit /b 0& exit /b 0)\n'
        'if "%1"=="build" (if not exist dist mkdir dist& >dist\\index.html echo built& exit /b 0)\n'
        'exit /b 0',
    )
    if conda:
        _write_cmd(
            shim / "conda.cmd",
            '>>"%SHIM_LOG%" echo conda %*\n'
            'if "%1"=="env" if "%2"=="list" goto envlist\n'
            'if "%1"=="env" if "%2"=="create" (>>"%SHIM_STATE%\\created" echo 1& exit /b 0)\n'
            'if "%1"=="env" if "%2"=="update" (echo conda progress 1>&2& >>"%SHIM_STATE%\\updated" echo 1& exit /b 0)\n'
            'if "%1"=="run" goto run\nexit /b 0\n'
            ':run\n'
            'echo %* | findstr /c:"tomllib" >nul\nif not errorlevel 1 (echo ["pytest"]& exit /b 0)\n'
            'echo %* | findstr /c:"playwright install" >nul\nif not errorlevel 1 (>>"%SHIM_STATE%\\chromium-ready" echo 1& exit /b 0)\n'
            'echo %* | findstr /c:"playwright.sync_api" >nul\nif not errorlevel 1 if exist "%SHIM_STATE%\\chromium-ready" exit /b 0\nif not errorlevel 1 if not exist "%SHIM_STATE%\\chromium-ready" exit /b 1\n'
            'echo %* | findstr /c:"upgrade_database" >nul\nif not errorlevel 1 "%SHIM_PYTHON%" "%SHIM_MIGRATION_HELPER%" "%SHIM_VAR_DIR%"\n'
            'echo %* | findstr /c:"select version_num" >nul\nif not errorlevel 1 "%SHIM_PYTHON%" "%SHIM_REVISION_HELPER%" "%SHIM_VAR_DIR%\\jiejian.db"\n'
            'exit /b 0\n'
            ':envlist\n'
            'if "%SHIM_CONDA_MODE%"=="existing" echo {"envs":["%SHIM_ENV_PATH%"]}\n'
            'if exist "%SHIM_STATE%\\created" echo {"envs":["%SHIM_ENV_PATH%"]}\n'
            'if "%SHIM_CONDA_MODE%"=="missing" if not exist "%SHIM_STATE%\\created" echo {"envs":[]}\n'
            'exit /b 0',
        )
    if uv:
        _write_cmd(
            shim / "uv.cmd",
            '>>"%SHIM_LOG%" echo uv %*\n'
            'if "%1"=="--version" echo uv 0.11.12\n'
            'if "%1"=="lock" if "%UV_MODE%"=="mismatch" exit /b 7\n'
            'if "%1"=="sync" if not exist "%UV_PROJECT_ENVIRONMENT%" mkdir "%UV_PROJECT_ENVIRONMENT%"\n'
            'if "%1"=="run" goto run\nexit /b 0\n'
            ':run\n'
            'echo %* | findstr /c:"playwright install" >nul\nif not errorlevel 1 (>>"%SHIM_STATE%\\chromium-ready" echo 1& exit /b 0)\n'
            'echo %* | findstr /c:"playwright.sync_api" >nul\nif not errorlevel 1 if exist "%SHIM_STATE%\\chromium-ready" exit /b 0\nif not errorlevel 1 if not exist "%SHIM_STATE%\\chromium-ready" exit /b 1\n'
            'echo %* | findstr /c:"upgrade_database" >nul\nif not errorlevel 1 "%SHIM_PYTHON%" "%SHIM_MIGRATION_HELPER%" "%SHIM_VAR_DIR%"\n'
            'echo %* | findstr /c:"select version_num" >nul\nif not errorlevel 1 "%SHIM_PYTHON%" "%SHIM_REVISION_HELPER%" "%SHIM_VAR_DIR%\\jiejian.db"\n'
            'exit /b 0',
        )
    return shim, log


def _run_start(
    var_dir: Path,
    shim: Path,
    log: Path,
    *,
    command_var_dir: str | Path | None = None,
    cwd: Path = ROOT,
    script_path: Path = SCRIPT,
    force_prepare: bool = False,
    mode: str | None = None,
    prepare_only: bool = True,
    input_text: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    effective_script_path = script_path
    effective_cwd = cwd
    if script_path == SCRIPT:
        isolated_project = _make_isolated_project(shim.parent)
        effective_script_path = isolated_project / "scripts" / "start.ps1"
        effective_cwd = isolated_project
    env = os.environ.copy()
    _clean_conda_environment(env)
    shim_root = shim.parent
    env.update(
        {
            "PATH": str(shim) + r";C:\Windows\System32;C:\Windows",
            "SHIM_LOG": str(log),
            "SHIM_STATE": str(shim_root / "state"),
            "SHIM_ENV_PATH": "C:/jiejian_env",
            "SHIM_CONDA_MODE": "existing" if (shim_root / "state" / "env-exists").exists() else "missing",
            "SHIM_PYTHON": r"D:\Miniconda\envs\jiejian_env\python.exe",
            "SHIM_MIGRATION_HELPER": str(shim_root / "migration_helper.py"),
            "SHIM_REVISION_HELPER": str(shim_root / "revision_helper.py"),
            "SHIM_VAR_DIR": str(var_dir),
            "SHIM_STORE_DIR": (effective_script_path.parent.parent.parent / ".pnpm-store" / "v11").as_posix(),
            "LOCALAPPDATA": str(shim_root / "localappdata"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    if extra_env:
        env.update(extra_env)
    arguments = []
    if prepare_only:
        arguments.append("-PrepareOnly")
    if mode is not None:
        arguments.extend(["-Mode", mode])
    if force_prepare:
        arguments.append("-ForcePrepare")
    arguments.extend(["-VarDir", str(command_var_dir if command_var_dir is not None else var_dir)])
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(effective_script_path), *arguments],
        cwd=effective_cwd,
        env=env,
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
    )


def _state_path(var_dir: Path) -> Path:
    return var_dir / "startup" / "prepare-state.json"


def _make_isolated_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "scripts" / "startup", project / "scripts" / "startup", dirs_exist_ok=True)
    (project / "product" / "backend" / "migrations" / "versions").mkdir(parents=True, exist_ok=True)
    (project / "product" / "frontend" / "src").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPT, project / "scripts" / "start.ps1")
    for name in ("environment.yml", "pyproject.toml", "uv.lock"):
        (project / name).write_text(f"fixture-{name}\n", encoding="utf-8")
    (project / "product" / "backend" / "alembic.ini").write_text("[alembic]\nscript_location = migrations\n", encoding="utf-8")
    (project / "product" / "backend" / "migrations" / "env.py").write_text("fixture migration env\n", encoding="utf-8")
    (project / "product" / "backend" / "migrations" / "versions" / "0001_initial.py").write_text("fixture revision\n", encoding="utf-8")
    (project / "product" / "frontend" / "package.json").write_text('{"name":"fixture","scripts":{"build":"vite build"}}\n', encoding="utf-8")
    (project / "product" / "frontend" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (project / "product" / "frontend" / "pnpm-workspace.yaml").write_text("allowBuilds:\n  esbuild: true\nstoreDir: ../../../.pnpm-store\n", encoding="utf-8")
    (project / "product" / "frontend" / "index.html").write_text("<div id=app></div>\n", encoding="utf-8")
    (project / "product" / "frontend" / "src" / "main.ts").write_text("export const fixture = true;\n", encoding="utf-8")
    (project / "product" / "frontend" / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    (project / "product" / "frontend" / "vite.config.ts").write_text("export default {};\n", encoding="utf-8")
    return project


def _command_counts(log: Path) -> dict[str, int]:
    lines = log.read_text(encoding="utf-8").splitlines()
    return {
        "uv_sync": sum("uv sync" in line for line in lines),
        "playwright_install": sum("playwright install" in line for line in lines),
        "migration": sum("upgrade_database" in line for line in lines),
        "pnpm_install": sum("pnpm install" in line for line in lines),
        "pnpm_build": sum("pnpm build" in line for line in lines),
        "doctor": sum("doctor" in line for line in lines),
    }


def _display_width(text: str) -> int:
    width = 0
    for character in text:
        code = ord(character)
        wide = (
            0x1100 <= code <= 0x115F
            or 0x2329 <= code <= 0x232A
            or 0x2E80 <= code <= 0xA4CF
            or 0xAC00 <= code <= 0xD7A3
            or 0xF900 <= code <= 0xFAFF
            or 0xFE10 <= code <= 0xFE6F
            or 0xFF00 <= code <= 0xFF60
            or 0xFFE0 <= code <= 0xFFE6
        )
        width += 2 if wide else 1
    return width


def _marker_column(lines: list[str], name: str, marker: str, branch: str) -> int:
    line = next(line for line in lines if branch in line and name in line and marker in line)
    return _display_width(line[: line.rfind(marker)])


def test_display_result_aligns_unicode_and_ascii_markers_without_losing_details(tmp_path: Path) -> None:
    output_path = tmp_path / "presentation-output.txt"
    command = f"""
. '{ROOT / 'scripts' / 'startup' / 'presentation.ps1'}'
$script:DisplayStageTimer = [Diagnostics.Stopwatch]::StartNew()
$script:DisplayUnicode = $true
Write-DisplayResult '中文任务' '完成' $false 'Unicode detail'
Write-DisplayResult 'English' '失败' $false 'Unicode failure detail'
Write-DisplayResult '跳过任务' '跳过' $false 'Unicode skip detail'
Write-DisplayResult '末项' '跳过' $true 'Unicode last detail'
$script:DisplayUnicode = $false
Write-DisplayResult '中文任务' '完成' $false 'ASCII detail'
Write-DisplayResult 'English' '失败' $false 'ASCII failure detail'
Write-DisplayResult '跳过任务' '跳过' $false 'ASCII skip detail'
Write-DisplayResult '末项' '跳过' $true 'ASCII last detail'
"""
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output_path.write_text(result.stdout, encoding="utf-8")
    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert len({_marker_column(lines, name, marker, "├─") for name, marker in (("中文任务", "✓"), ("English", "×"), ("跳过任务", "SKIP"))}) == 1
    assert len({_marker_column(lines, name, marker, "|--") for name, marker in (("中文任务", "OK"), ("English", "FAILED"), ("跳过任务", "SKIP"))}) == 1
    for detail in ("Unicode detail", "Unicode failure detail", "Unicode skip detail", "Unicode last detail", "ASCII detail", "ASCII failure detail", "ASCII skip detail", "ASCII last detail"):
        detail_index = next(index for index, line in enumerate(lines) if detail in line)
        assert detail_index > 0
        assert any(name in lines[detail_index - 1] for name in ("中文任务", "English", "跳过任务", "末项"))
    assert "├─" in result.stdout and "└─" in result.stdout
    assert "|--" in result.stdout and "      --" in result.stdout


@pytest.mark.process
def test_conda_creates_missing_environment_without_uv(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=True, uv=False)
    relative_var_dir = Path("var") / f"pytest-o4-start-relative-{tmp_path.name}"
    expected_var_dir = (tmp_path / "project" / relative_var_dir).resolve()
    try:
        result = _run_start(expected_var_dir, shim, log, command_var_dir=relative_var_dir, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        commands = log.read_text(encoding="utf-8")
        assert "conda env create" in commands
        assert "conda env update" not in commands
        assert "python -B -m pip --isolated install --requirement" in commands
        assert "--editable" not in commands
        assert (expected_var_dir / "cache" / "python-dependencies.txt").read_text(
            encoding="utf-8"
        ).splitlines() == ["pytest"]
        assert "uv " not in commands
        assert "运行环境" in result.stdout
        assert "Conda · C:\\jiejian_env" in result.stdout
        assert f"运行目录：{expected_var_dir}" in result.stdout
        assert "日志" not in result.stdout
    finally:
        if expected_var_dir.exists():
            shutil.rmtree(expected_var_dir)


@pytest.mark.process
def test_conda_reuses_healthy_existing_environment_without_mutation(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=True, uv=False, existing_env=True)
    result = _run_start(tmp_path / "var", shim, log)
    assert result.returncode == 0, result.stdout + result.stderr
    commands = log.read_text(encoding="utf-8")
    assert "conda env update" not in commands
    assert "pip install" not in commands
    assert "conda env create" not in commands
    assert "uv " not in commands
    assert "python -B -m product.backend.cli" in commands
    output = result.stdout + result.stderr
    assert "NativeCommandError" not in output
    assert "CategoryInfo" not in output
    assert "FullyQualifiedErrorId" not in output
    assert "\n0\n" not in f"\n{output}\n"
    assert "Conda · C:\\jiejian_env" in result.stdout


@pytest.mark.process
def test_existing_chromium_is_adopted_when_prepare_state_is_missing(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=True, uv=False, existing_env=True)
    (tmp_path / "state" / "chromium-ready").write_text("1", encoding="ascii")

    result = _run_start(tmp_path / "var", shim, log)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "playwright install" not in log.read_text(encoding="utf-8")
    state = json.loads(_state_path(tmp_path / "var").read_text(encoding="utf-8"))
    assert state["phases"]["playwright"]["completed"] is True


@pytest.mark.process
def test_existing_uv_runs_locked_commands(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    result = _run_start(tmp_path / "var", shim, log)
    assert result.returncode == 0, result.stdout + result.stderr
    commands = log.read_text(encoding="utf-8")
    assert "uv lock --check" in commands
    assert "uv sync --locked --all-groups" in commands
    assert "--no-install-project" in commands
    assert "uv run --locked --no-sync" in commands
    assert "conda " not in commands
    assert f"uv · {tmp_path / 'var' / 'envs' / 'uv'}" in result.stdout
    assert "uv 版本：uv 0.11.12" in result.stdout


@pytest.mark.process
def test_prepare_state_is_versioned_atomic_and_hot_path_skips_cacheable_commands(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    var_dir = tmp_path / "var"
    first = _run_start(var_dir, shim, log)
    assert first.returncode == 0, first.stdout + first.stderr
    state = _state_path(var_dir)
    assert state.is_file()
    payload = __import__("json").loads(state.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1"
    assert set(payload["phases"]) >= {"critical_runtime", "python_dependencies", "playwright", "migration", "node_dependencies", "frontend_build"}
    assert not list(state.parent.glob("*.tmp"))
    before = log.read_text(encoding="utf-8")
    second = _run_start(var_dir, shim, log)
    assert second.returncode == 0, second.stdout + second.stderr
    after = log.read_text(encoding="utf-8")
    for command in ("uv sync", "playwright install", "pnpm install", "pnpm build"):
        assert after.count(command) == before.count(command)
    assert "已复用 Python 依赖缓存" in second.stdout
    assert "已复用前端资源" in second.stdout


def _run_isolated_fixture(tmp_path: Path, *, extra_env: dict[str, str] | None = None):
    project = _make_isolated_project(tmp_path)
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    result = _run_start(
        tmp_path / "var",
        shim,
        log,
        cwd=project,
        script_path=project / "scripts" / "start.ps1",
        extra_env=extra_env,
    )
    return project, shim, log, result


@pytest.mark.process
def test_isolated_fixture_cold_hot_and_valid_revision(tmp_path: Path) -> None:
    project, shim, log, first = _run_isolated_fixture(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "JIEJIAN" in first.stdout
    assert "安全意图一致性验证" in first.stdout
    for index, stage in enumerate(("检查运行环境", "准备 Python", "准备浏览器", "准备数据", "准备界面", "启动界鉴"), 1):
        assert f"[{index}/6] {stage}" in first.stdout
    assert first.stdout.count("JIEJIAN") == 1
    assert "正在准备" not in first.stdout
    assert "\r" not in first.stdout
    assert "uv sync" not in first.stdout
    assert "pnpm install" not in first.stdout
    cold = _command_counts(log)
    assert cold == {
        "uv_sync": 1,
        "playwright_install": 1,
        "migration": 1,
        "pnpm_install": 1,
        "pnpm_build": 1,
        "doctor": 1,
    }
    payload = json.loads(_state_path(tmp_path / "var").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1"
    assert payload["phases"]["migration"]["facts"]["revision"] == "0001_initial"
    second = _run_start(
        tmp_path / "var",
        shim,
        log,
        cwd=project,
        script_path=project / "scripts" / "start.ps1",
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert _command_counts(log) == {**cold, "doctor": 2}


@pytest.mark.process
def test_healthy_node_modules_are_adopted_when_prepare_state_is_missing(tmp_path: Path) -> None:
    project, shim, log, first = _run_isolated_fixture(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    state_path = _state_path(tmp_path / "var")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    del state["phases"]["node_dependencies"]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    before = _command_counts(log)

    second = _run_start(
        tmp_path / "var",
        shim,
        log,
        cwd=project,
        script_path=project / "scripts" / "start.ps1",
    )

    assert second.returncode == 0, second.stdout + second.stderr
    assert _command_counts(log)["pnpm_install"] == before["pnpm_install"]
    restored = json.loads(state_path.read_text(encoding="utf-8"))
    assert restored["phases"]["node_dependencies"]["completed"] is True


def test_wait_indicator_is_tty_gated_and_stopped_for_external_calls() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in (SCRIPT, *sorted((ROOT / "scripts" / "startup").glob("*.ps1"))))

    assert "function Start-WaitIndicator" in text
    assert "function Stop-WaitIndicator" in text
    assert "-not $script:DisplayInteractive -or [Console]::IsOutputRedirected" in text
    assert "-DisplaySpinnerProcess" in text
    assert "Start-Process -FilePath $shell" in text
    assert "Invoke-WaitIndicatorProcess" in text
    assert "Stop-Process -Id $script:WaitIndicatorProcess.Id" in text
    assert "if ($waitIndicatorStarted) { Stop-WaitIndicator }" in text


def test_service_uses_current_repository_cli_and_frontend() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in (SCRIPT, *sorted((ROOT / "scripts" / "startup").glob("*.ps1"))))

    assert '"python", "-B", "-m", "product.backend.cli"' in text
    assert '"-m", "pip", "--isolated", "install"' in text
    assert '"--editable"' not in text
    assert "version('jiejian')" not in text
    assert '"--no-install-project"' in text
    assert '"--frontend-dir", (Join-Path $script:ProjectRoot "product\\frontend\\dist")' in text
    assert '"serve", "--open"' in text


@pytest.mark.process
@pytest.mark.parametrize(
    ("name", "mutate", "rerun"),
    [
        ("python_input", lambda project: (project / "pyproject.toml").write_text("changed\n", encoding="utf-8"), {"uv_sync": 1}),
        ("node_input", lambda project: (project / "product" / "frontend" / "package.json").write_text('{"name":"changed"}\n', encoding="utf-8"), {"pnpm_install": 1, "pnpm_build": 1}),
        ("pnpm_workspace_input", lambda project: (project / "product" / "frontend" / "pnpm-workspace.yaml").write_text("allowBuilds:\n  esbuild: false\nstoreDir: ../../../.pnpm-store\n", encoding="utf-8"), {"pnpm_install": 1, "pnpm_build": 1}),
        ("frontend_source", lambda project: (project / "product" / "frontend" / "src" / "main.ts").write_text("export const changed = true;\n", encoding="utf-8"), {"pnpm_build": 1}),
        ("migration_input", lambda project: (project / "product" / "backend" / "migrations" / "versions" / "0001_initial.py").write_text("changed revision\n", encoding="utf-8"), {"migration": 1}),
    ],
)
def test_isolated_fingerprint_invalidation_matrix(tmp_path: Path, name: str, mutate, rerun: dict[str, int]) -> None:
    project, shim, log, first = _run_isolated_fixture(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    before = _command_counts(log)
    mutate(project)
    second = _run_start(tmp_path / "var", shim, log, cwd=project, script_path=project / "scripts" / "start.ps1")
    assert second.returncode == 0, f"{name}: {second.stdout}{second.stderr}"
    after = _command_counts(log)
    for command, amount in rerun.items():
        assert after[command] == before[command] + amount
    for command, amount in before.items():
        if command not in rerun and command != "doctor":
            assert after[command] == amount
    assert after["doctor"] == before["doctor"] + 1


@pytest.mark.process
@pytest.mark.parametrize("missing", ["node_modules", "corrupt_node_modules", "dist", "chromium", "database"])
def test_isolated_output_and_runtime_missingness_rebuilds_only_required_stage(tmp_path: Path, missing: str) -> None:
    project, shim, log, first = _run_isolated_fixture(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    before = _command_counts(log)
    if missing == "node_modules":
        shutil.rmtree(project / "product" / "frontend" / "node_modules")
    elif missing == "corrupt_node_modules":
        (project / "product" / "frontend" / "node_modules" / ".bin" / "tsc.cmd").unlink()
    elif missing == "dist":
        shutil.rmtree(project / "product" / "frontend" / "dist")
    elif missing == "chromium":
        (tmp_path / "state" / "chromium-ready").unlink()
    elif missing == "database":
        (tmp_path / "var" / "jiejian.db").unlink()
    second = _run_start(tmp_path / "var", shim, log, cwd=project, script_path=project / "scripts" / "start.ps1")
    assert second.returncode == 0, f"{missing}: {second.stdout}{second.stderr}"
    after = _command_counts(log)
    expected = {
        "node_modules": {"pnpm_install": 1, "pnpm_build": 1},
        "corrupt_node_modules": {"pnpm_install": 1, "pnpm_build": 1},
        "dist": {"pnpm_build": 1},
        "chromium": {"playwright_install": 1},
        "database": {"migration": 1},
    }[missing]
    for command, amount in expected.items():
        assert after[command] == before[command] + amount
    for command, amount in before.items():
        if command not in expected and command != "doctor":
            assert after[command] == amount


@pytest.mark.process
def test_old_pnpm_store_link_rebuilds_only_node_dependencies_and_frontend(tmp_path: Path) -> None:
    project, shim, log, first = _run_isolated_fixture(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    before = _command_counts(log)
    manifest = project / "product" / "frontend" / "node_modules" / ".modules.yaml"
    manifest.write_text('{\n  "storeDir": "D:\\\\.pnpm-store\\\\v11"\n}\n', encoding="utf-8")
    second = _run_start(tmp_path / "var", shim, log, cwd=project, script_path=project / "scripts" / "start.ps1")
    assert second.returncode == 0, second.stdout + second.stderr
    after = _command_counts(log)
    assert after["pnpm_install"] == before["pnpm_install"] + 1
    assert after["pnpm_build"] == before["pnpm_build"] + 1
    for command in ("uv_sync", "playwright_install", "migration"):
        assert after[command] == before[command]


@pytest.mark.process
def test_isolated_revision_replacement_invalidates_migration(tmp_path: Path) -> None:
    project, shim, log, first = _run_isolated_fixture(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    before = _command_counts(log)
    with sqlite3.connect(tmp_path / "var" / "jiejian.db") as connection:
        connection.execute("update alembic_version set version_num = 'replaced'")
    second = _run_start(tmp_path / "var", shim, log, cwd=project, script_path=project / "scripts" / "start.ps1")
    assert second.returncode == 0, second.stdout + second.stderr
    assert _command_counts(log)["migration"] == before["migration"] + 1


@pytest.mark.process
def test_isolated_migration_without_valid_revision_fails_without_success_state(tmp_path: Path) -> None:
    project, shim, log, result = _run_isolated_fixture(tmp_path, extra_env={"SHIM_INVALID_REVISION": "1"})
    assert result.returncode == 43, result.stdout + result.stderr
    state = _state_path(tmp_path / "var")
    payload = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {"phases": {}}
    assert "migration" not in payload["phases"]
    assert "未能读取有效 Alembic revision" in result.stdout


@pytest.mark.process
def test_force_prepare_reexecutes_cacheable_commands_and_prepare_only_never_serves(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    var_dir = tmp_path / "var"
    assert _run_start(var_dir, shim, log).returncode == 0
    result = _run_start(var_dir, shim, log, force_prepare=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "serve" not in log.read_text(encoding="utf-8")
    assert log.read_text(encoding="utf-8").count("uv sync") == 2
    assert log.read_text(encoding="utf-8").count("pnpm install") == 2


@pytest.mark.process
def test_corrupt_or_unknown_prepare_state_cold_starts_safely(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    var_dir = tmp_path / "var"
    state = _state_path(var_dir)
    state.parent.mkdir(parents=True)
    state.write_text('{"schema_version":"999","phases":{}}', encoding="utf-8")
    result = _run_start(var_dir, shim, log)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "损坏或版本未知" in result.stdout
    assert __import__("json").loads(state.read_text(encoding="utf-8"))["schema_version"] == "1"


@pytest.mark.process
def test_failed_stage_does_not_write_failed_phase_and_prints_force_recovery(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    var_dir = tmp_path / "var"
    result = _run_start(var_dir, shim, log, extra_env={"UV_MODE": "mismatch"})
    assert result.returncode == 22
    assert "-ForcePrepare -PrepareOnly" in result.stdout
    state = _state_path(var_dir)
    assert not state.exists() or "python_dependencies" not in __import__("json").loads(state.read_text(encoding="utf-8"))["phases"]


def _make_download_wrapper(tmp_path: Path, *, fail: bool = False) -> tuple[Path, Path, Path]:
    project = _make_isolated_project(tmp_path)
    archive_root = tmp_path / "download-source"
    archive_root.mkdir()
    uv_cmd = archive_root / "uv.cmd"
    migration_helper = tmp_path / "migration_helper.py"
    migration_helper.write_text(
        "import sqlite3, sys\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)\n"
        "conn = sqlite3.connect(root / 'jiejian.db')\n"
        "conn.execute('create table if not exists alembic_version (version_num varchar(32) not null)')\n"
        "conn.execute('delete from alembic_version')\n"
        "conn.execute(\"insert into alembic_version values ('0001_initial')\")\n"
        "conn.commit(); conn.close()\n",
        encoding="utf-8",
    )
    revision_helper = tmp_path / "revision_helper.py"
    revision_helper.write_text(
        "import sqlite3, sys\n"
        "conn = sqlite3.connect(sys.argv[1]); print(conn.execute('select version_num from alembic_version').fetchone()[0]); conn.close()\n",
        encoding="utf-8",
    )
    _write_cmd(
        uv_cmd,
        '>>"%SHIM_LOG%" echo uv %*\n'
        'if "%1"=="--version" echo uv 0.11.12\n'
        'if "%1"=="sync" if not exist "%UV_PROJECT_ENVIRONMENT%" mkdir "%UV_PROJECT_ENVIRONMENT%"\n'
        'if "%1"=="run" goto run\nexit /b 0\n'
        ':run\n'
        'echo %* | findstr /c:"playwright install" >nul\nif not errorlevel 1 (>>"%SHIM_STATE%\\chromium-ready" echo 1& exit /b 0)\n'
        'echo %* | findstr /c:"playwright.sync_api" >nul\nif not errorlevel 1 if exist "%SHIM_STATE%\\chromium-ready" exit /b 0\nif not errorlevel 1 if not exist "%SHIM_STATE%\\chromium-ready" exit /b 1\n'
        'echo %* | findstr /c:"upgrade_database" >nul\nif not errorlevel 1 "%SHIM_PYTHON%" "%SHIM_MIGRATION_HELPER%" "%SHIM_VAR_DIR%"\n'
        'echo %* | findstr /c:"select version_num" >nul\nif not errorlevel 1 "%SHIM_PYTHON%" "%SHIM_REVISION_HELPER%" "%SHIM_VAR_DIR%\\jiejian.db"\n'
        'exit /b 0',
    )
    archive = tmp_path / "uv-x86_64-pc-windows-msvc.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.write(uv_cmd, "uv.cmd")
    checksum = tmp_path / (archive.name + ".sha256")
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n", encoding="ascii")
    wrapper = tmp_path / "download-wrapper.ps1"
    source = f"$sourceZip = '{archive}'; $sourceHash = '{checksum}'"
    wrapper.write_text(
        f"{source}\n"
        f"function Invoke-WebRequest {{ param($Uri, $OutFile, [switch]$UseBasicParsing)\n"
        f"  if (${str(fail).lower()}) {{ throw 'offline' }}\n"
        f"  Add-Content -LiteralPath '{tmp_path / 'download-count.log'}' -Value $Uri\n"
        f"  if ($Uri.EndsWith('.sha256')) {{ Copy-Item -LiteralPath $sourceHash -Destination $OutFile }} else {{ Copy-Item -LiteralPath $sourceZip -Destination $OutFile }}\n"
        f"}}\n$env:SHIM_PYTHON = '{r'D:\Miniconda\envs\jiejian_env\python.exe'}'\n$env:SHIM_MIGRATION_HELPER = '{migration_helper}'\n$env:SHIM_REVISION_HELPER = '{revision_helper}'\n$env:SHIM_VAR_DIR = '{tmp_path / 'var'}'\n$env:SHIM_STORE_DIR = '{(project.parent / '.pnpm-store' / 'v11').as_posix()}'\n. '{project / 'scripts' / 'start.ps1'}' -PrepareOnly -VarDir '{tmp_path / 'var'}'\n"
        f"if (Get-ChildItem -LiteralPath '{tmp_path / 'var' / 'logs'}' -Filter 'startup-*.log' | Get-Content | Select-String '失败阶段') {{ exit 21 }}\n",
        encoding="utf-8",
    )
    return wrapper, archive, checksum


@pytest.mark.process
def test_missing_uv_downloads_after_hash_check_and_reuses_install(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=False)
    wrapper, _, _ = _make_download_wrapper(tmp_path)
    env = os.environ.copy()
    _clean_conda_environment(env)
    env.update(
        {
            "PATH": str(shim) + r";C:\Windows\System32;C:\Windows",
            "SHIM_LOG": str(log),
            "SHIM_STATE": str(tmp_path / "state"),
            "SHIM_ENV_PATH": "C:/jiejian_env",
            "SHIM_CONDA_MODE": "missing",
            "LOCALAPPDATA": str(tmp_path / "localappdata"),
            "PROCESSOR_ARCHITECTURE": "AMD64",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    first = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)], cwd=ROOT, env=env, text=True, capture_output=True)
    second = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)], cwd=ROOT, env=env, text=True, capture_output=True)
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert (tmp_path / "localappdata" / "jiejian" / "bin" / "uv.cmd").is_file()
    assert len(list(tmp_path.glob("var/uv-download-*"))) == 0
    assert len((tmp_path / "download-count.log").read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.process
def test_lock_mismatch_returns_22_without_sync_or_lockfile_change(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    lockfile = ROOT / "uv.lock"
    before = hashlib.sha256(lockfile.read_bytes()).digest()
    result = _run_start(tmp_path / "var", shim, log, extra_env={"UV_MODE": "mismatch"})
    assert result.returncode == 22
    assert "如何解决" in result.stdout
    assert "uv sync" not in log.read_text(encoding="utf-8")
    assert hashlib.sha256(lockfile.read_bytes()).digest() == before


@pytest.mark.process
def test_download_failure_returns_21_and_cleans_download_directory(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=False)
    wrapper, _, _ = _make_download_wrapper(tmp_path, fail=True)
    env = os.environ.copy()
    _clean_conda_environment(env)
    env.update({"PATH": str(shim) + r";C:\Windows\System32;C:\Windows", "SHIM_LOG": str(log), "LOCALAPPDATA": str(tmp_path / "localappdata"), "PROCESSOR_ARCHITECTURE": "AMD64", "PYTHONDONTWRITEBYTECODE": "1"})
    result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)], cwd=ROOT, env=env, text=True, capture_output=True)
    assert result.returncode == 21
    assert "日志" in result.stdout
    assert not list((tmp_path / "var").glob("uv-download-*"))


@pytest.mark.essential
def test_start_script_is_the_only_startup_script() -> None:
    assert [path.name for path in ROOT.glob("start*.cmd")] == ["start.cmd"]
    assert [path.name for path in (ROOT / "scripts").iterdir() if path.suffix.lower() in {".ps1", ".cmd"}] == ["start.ps1"]
    assert not (ROOT / "scripts" / "setup-conda.ps1").exists()


@pytest.mark.essential
def test_powershell_startup_scripts_keep_utf8_bom() -> None:
    """Windows PowerShell 5.1 在系统 UTF-8 Beta 关闭时依赖 BOM 识别中文脚本。"""

    for path in POWERSHELL_SCRIPTS:
        raw = path.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), path
        raw.decode("utf-8-sig")
    command_bytes = CMD_SCRIPT.read_bytes()
    assert not command_bytes.startswith(b"\xef\xbb\xbf")
    assert all(value < 0x80 for value in command_bytes)
    assert b"chcp 65001" in command_bytes


@pytest.mark.process
@pytest.mark.essential
def test_root_start_cmd_forwards_arguments_and_exit_code(tmp_path: Path) -> None:
    launch_root = tmp_path / "界鉴 启动"
    launch_root.mkdir()
    scripts = launch_root / "scripts"
    scripts.mkdir()
    forwarded_path = launch_root / "forwarded.txt"
    (launch_root / "start.cmd").write_bytes(CMD_SCRIPT.read_bytes())
    (scripts / "start.ps1").write_text(
        "param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)\n"
        f"Set-Content -LiteralPath '{forwarded_path}' -Value ($Args -join '|') -Encoding UTF8\n"
        "exit 37\n",
        encoding="utf-8",
    )
    log = tmp_path / "cmd.log"
    env = os.environ.copy()
    _clean_conda_environment(env)
    env.update({"PATH": r"C:\Windows\System32;C:\Windows;C:\Windows\System32\WindowsPowerShell\v1.0", "START_CMD_LOG": str(log)})
    result = subprocess.run(
        [
            os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"),
            "/d",
            "/c",
            'call start.cmd -ForcePrepare -PrepareOnly -VarDir "D:\\tmp\\界鉴-test"',
        ],
        cwd=launch_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 37
    forwarded = forwarded_path.read_text(encoding="utf-8-sig").strip()
    assert forwarded == '-WaitOnFailure|-ForcePrepare|-PrepareOnly|-VarDir|"D:\\tmp\\界鉴-test"'
    command_text = CMD_SCRIPT.read_text(encoding="utf-8")
    assert "chcp 65001" in command_text
    assert "setlocal" in command_text
    assert "-WaitOnFailure" in command_text
    assert "where pwsh.exe" in command_text
    assert "-NoLogo -NoProfile -ExecutionPolicy Bypass -File" in command_text
    assert "%*" in command_text
    assert "conda" not in command_text.lower()
    assert "uv" not in command_text.lower()
    assert "jiejian" not in command_text.lower()


@pytest.mark.process
@pytest.mark.essential
def test_default_interactive_requires_explicit_mode_when_io_is_redirected(
    tmp_path: Path,
) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    result = _run_start(
        tmp_path / "var",
        shim,
        log,
        prepare_only=False,
    )

    assert result.returncode == 40
    assert "请显式使用 -Mode Gui、-Mode Cli 或 -Mode Prepare" in result.stdout
    assert "Select-StartupMode" not in result.stdout


@pytest.mark.process
def test_prepare_only_compatibility_and_explicit_mode_conflict_are_strict(
    tmp_path: Path,
) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    result = _run_start(
        tmp_path / "var",
        shim,
        log,
        mode="Gui",
        prepare_only=True,
    )

    assert result.returncode == 40
    assert "-PrepareOnly 只能与 -Mode Prepare 组合" in result.stdout


@pytest.mark.process
@pytest.mark.essential
def test_explicit_prepare_and_gui_routes_keep_prepare_semantics_and_serve_open(
    tmp_path: Path,
) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    var_dir = tmp_path / "var"
    prepared = _run_start(var_dir, shim, log, mode="Prepare", prepare_only=False)
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    assert " serve --open " not in log.read_text(encoding="utf-8")

    gui = _run_start(var_dir, shim, log, mode="Gui", prepare_only=False)
    assert gui.returncode == 0, gui.stdout + gui.stderr
    log_text = log.read_text(encoding="utf-8")
    assert " serve --open " in log_text
    assert "--frontend-dir" in log_text


@pytest.mark.process
@pytest.mark.essential
def test_cli_mode_enters_temporary_shell_with_exact_runner_and_var_dir(
    tmp_path: Path,
) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    var_dir = tmp_path / "var"
    result = _run_start(
        var_dir,
        shim,
        log,
        mode="Cli",
        prepare_only=False,
        input_text="jiejian doctor\nexit\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "界鉴命令行已经准备完成" in result.stdout
    assert str(var_dir) in result.stdout
    log_text = log.read_text(encoding="utf-8")
    assert " run --locked --no-sync python -B -m product.backend.cli " in log_text
    assert " doctor " in log_text
    assert str(var_dir) in log_text
    assert not list(tmp_path.rglob("*PowerShell_profile.ps1"))


@pytest.mark.process
def test_direct_prepare_failure_does_not_wait_even_when_hidden_flag_is_present(
    tmp_path: Path,
) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    result = _run_start(
        tmp_path / "var",
        shim,
        log,
        mode="Prepare",
        prepare_only=False,
        extra_env={"UV_MODE": "mismatch"},
    )

    assert result.returncode == 22
    assert "按 Enter 关闭窗口" not in result.stdout


@pytest.mark.essential
def test_interactive_failure_wait_eligibility_survives_menu_selection() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assignment = "$script:WaitOnFailure = [bool]($WaitOnFailure -and"

    assert text.count(assignment) == 1
    assert text.index(assignment) < text.index("$script:FinalMode = Select-StartupMode")
