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
    (state / "chromium.exe").write_bytes(b"fixture")
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
        '>>"%SHIM_LOG%" echo node %*\nif "%1"=="--version" echo v24.13.0\nexit /b 0',
    )
    _write_cmd(
        shim / "pnpm.cmd",
        '>>"%SHIM_LOG%" echo pnpm %*\n'
        'if "%1"=="--version" goto version\n'
        'if "%1"=="install" goto install\n'
        'if "%1"=="build" goto build\n'
        'exit /b 0\n'
        ':install\n'
        'if not exist node_modules\\.bin mkdir node_modules\\.bin\n'
        'if not exist "%SHIM_STORE_DIR%" mkdir "%SHIM_STORE_DIR%"\n'
        'if not exist "%SHIM_VIRTUAL_STORE_DIR%" mkdir "%SHIM_VIRTUAL_STORE_DIR%"\n'
        '>node_modules\\.modules.yaml echo {& '
        '>>node_modules\\.modules.yaml echo   "storeDir": "%SHIM_STORE_DIR%",& '
        '>>node_modules\\.modules.yaml echo   "virtualStoreDir": "%SHIM_VIRTUAL_STORE_DIR%"& '
        '>>node_modules\\.modules.yaml echo }& '
        '>node_modules\\.bin\\tsc.cmd echo @exit /b 0& '
        '>node_modules\\.bin\\vite.cmd echo @exit /b 0\n'
        'exit /b 0\n'
        ':build\n'
        'if not exist dist mkdir dist\n'
        '>dist\\index.html echo built\n'
        'exit /b 0\n'
        ':version\n'
        'if not "%COREPACK_ENABLE_DOWNLOAD_PROMPT%"=="0" exit /b 29\n'
        'if exist package.json goto pinned_version\n'
        'echo 11.22.0\n'
        'exit /b 0\n'
        ':pinned_version\n'
        'echo 11.21.0\n'
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
            'echo %* | findstr /c:"sys.executable" >nul\nif not errorlevel 1 (echo D:\\Miniconda\\envs\\jiejian_env\\python.exe& exit /b 0)\n'
            'echo %* | findstr /c:"require_python_environment" >nul\nif not errorlevel 1 (echo {"ok":true,"user_site_on_sys_path":false,"package_origins":{}}& exit /b 0)\n'
            'echo %* | findstr /c:"playwright install" >nul\nif not errorlevel 1 (>>"%SHIM_STATE%\\chromium-ready" echo 1& exit /b 0)\n'
            'echo %* | findstr /c:"playwright.sync_api" >nul\nif not errorlevel 1 if exist "%SHIM_STATE%\\chromium-ready" (echo %SHIM_CHROMIUM%& exit /b 0)\nif not errorlevel 1 if not exist "%SHIM_STATE%\\chromium-ready" exit /b 1\n'
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
            'echo %* | findstr /c:"sys.executable" >nul\nif not errorlevel 1 (echo D:\\Miniconda\\envs\\jiejian_env\\python.exe& exit /b 0)\n'
            'if "%1"=="lock" if "%UV_MODE%"=="mismatch" exit /b 7\n'
            'if "%1"=="sync" if not exist "%UV_PROJECT_ENVIRONMENT%" mkdir "%UV_PROJECT_ENVIRONMENT%"\n'
            'if "%1"=="run" goto run\nexit /b 0\n'
            ':run\n'
            'echo %* | findstr /c:"require_python_environment" >nul\nif not errorlevel 1 (echo {"ok":true,"user_site_on_sys_path":false,"package_origins":{}}& exit /b 0)\n'
            'echo %* | findstr /c:"playwright install" >nul\nif not errorlevel 1 (>>"%SHIM_STATE%\\chromium-ready" echo 1& exit /b 0)\n'
            'echo %* | findstr /c:"playwright.sync_api" >nul\nif not errorlevel 1 if exist "%SHIM_STATE%\\chromium-ready" (echo %SHIM_CHROMIUM%& exit /b 0)\nif not errorlevel 1 if not exist "%SHIM_STATE%\\chromium-ready" exit /b 1\n'
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
            "SHIM_CHROMIUM": str(shim_root / "state" / "chromium.exe"),
            "PYTHONPATH": str(ROOT),
            "SHIM_MIGRATION_HELPER": str(shim_root / "migration_helper.py"),
            "SHIM_REVISION_HELPER": str(shim_root / "revision_helper.py"),
            "SHIM_VAR_DIR": str(var_dir),
            "SHIM_STORE_DIR": (var_dir / "cache" / "pnpm-store" / "v11").as_posix(),
            "SHIM_VIRTUAL_STORE_DIR": (effective_cwd / "product" / "frontend" / "node_modules" / ".pnpm").as_posix(),
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
    return var_dir / "cache" / "startup" / "prepare-state.json"


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
    (project / "product" / "frontend" / "package.json").write_text(
        '{"name":"fixture","engines":{"node":">=24.13.0 <25"},"packageManager":"pnpm@11.21.0","scripts":{"build":"vite build"}}\n',
        encoding="utf-8",
    )
    (project / "product" / "frontend" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (project / "product" / "frontend" / "pnpm-workspace.yaml").write_text(
        "allowBuilds:\n  esbuild: true\nstoreDir: ../../var/cache/pnpm-store\n",
        encoding="utf-8",
    )
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
        assert (expected_var_dir / "cache" / "python" / "requirements.txt").read_text(
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
    assert f"uv · {tmp_path / 'var' / 'runtime' / 'python' / 'env'}" in result.stdout
    startup_log = next((tmp_path / "var" / "logs" / "startup").glob("*.log")).read_text(encoding="utf-8")
    assert "uv=uv 0.11.12" in startup_log


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
    startup_logs = [path.read_text(encoding="utf-8") for path in (var_dir / "logs" / "startup").glob("*.log")]
    assert any("[python_dependencies] 跳过" in content for content in startup_logs)
    assert any("[node_dependencies] 跳过" in content for content in startup_logs)
    assert any("[frontend_build] 跳过" in content for content in startup_logs)


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
    assert second.stdout.count("本地数据") == 1
    assert "修订 0001_initial · 已是最新" in second.stdout
    assert second.stdout.count("前端依赖") == 1
    assert second.stdout.count("前端构建") == 1
    assert "Write-DisplaySubtask" not in second.stdout


@pytest.mark.process
def test_toolchain_state_records_confirmed_runner_and_python_resolution(tmp_path: Path) -> None:
    project, shim, log, result = _run_isolated_fixture(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    state = json.loads(_state_path(tmp_path / "var").read_text(encoding="utf-8"))
    facts = state["phases"]["toolchain"]["facts"]
    assert facts["node_version"] == "v24.13.0"
    assert facts["pnpm_version"] == "11.21.0"
    assert Path(facts["node_path"]).name == "node.cmd"
    assert Path(facts["pnpm_path"]).name == "pnpm.cmd"
    assert state["phases"]["toolchain"]["fingerprint"]
    startup_log = next((tmp_path / "var" / "logs" / "startup").glob("*.log")).read_text(encoding="utf-8")
    assert "Python 实际可执行文件: D:\\Miniconda\\envs\\jiejian_env\\python.exe" in startup_log


@pytest.mark.process
def test_invalid_package_manager_source_fails_before_frontend_or_download(tmp_path: Path) -> None:
    project, shim, log, first = _run_isolated_fixture(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    package_path = project / "product" / "frontend" / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["packageManager"] = "pnpm"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    result = _run_start(tmp_path / "var", shim, log, cwd=project, script_path=project / "scripts" / "start.ps1")

    assert result.returncode == 31
    assert "packageManager" in result.stdout
    assert not list((tmp_path / "var" / "temp" / "downloads").glob("node-*"))


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
    assert "Start-Sleep -Milliseconds 130" in text


def test_startup_var_dir_paths_follow_final_lifecycle_layout() -> None:
    start = SCRIPT.read_text(encoding="utf-8-sig")
    runtime = (ROOT / "scripts" / "startup" / "runtime.ps1").read_text(encoding="utf-8-sig")

    assert 'Join-Path $script:VarDir "logs\\startup"' in start
    assert 'Join-Path $script:VarDir "cache\\startup"' in start
    assert '"cache\\python\\requirements.txt"' in runtime
    assert '"runtime\\python\\env"' in runtime
    assert '"runtime\\python\\installations"' in runtime
    assert '"runtime\\uv\\0.11.12\\{0}"' in runtime
    assert '"temp\\downloads\\node-{0}"' in runtime
    assert '"temp\\downloads\\uv-{0}"' in runtime
    assert '"runtime\\playwright"' in start
    assert "LOCALAPPDATA" not in runtime


def test_startup_isolates_python_and_reports_actual_runtime() -> None:
    start = SCRIPT.read_text(encoding="utf-8-sig")
    runtime = (ROOT / "scripts" / "startup" / "runtime.ps1").read_text(encoding="utf-8-sig")
    product = (ROOT / "scripts" / "startup" / "product.ps1").read_text(encoding="utf-8-sig")

    assert '$env:PYTHONNOUSERSITE = "1"' in start
    assert "Remove-Item Env:PYTHONPATH" in start
    assert "Remove-Item Env:PYTHONHOME" in start
    assert "JIEJIAN_PYTHON_EXECUTABLE" in start + runtime
    assert "require_python_environment" in runtime
    assert "当前界鉴运行环境" in product
    for label in ("Python", "Node.js", "pnpm", "Chromium"):
        assert label in product
    assert "__JIEJIAN_SERVE_READY__:" in runtime
    assert "界鉴网页已打开" in runtime
    assert "退出界鉴" in runtime
    assert "Ctrl+C" in runtime


@pytest.mark.process
def test_startup_logs_are_nested_and_keep_only_twenty_runs(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=False, uv=True)
    var_dir = tmp_path / "var"
    startup_logs = var_dir / "logs" / "startup"
    startup_logs.mkdir(parents=True)
    for index in range(22):
        path = startup_logs / f"old-{index:02d}.log"
        path.write_text(str(index), encoding="utf-8")
        os.utime(path, (index + 1, index + 1))

    result = _run_start(var_dir, shim, log)

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list(startup_logs.glob("*.log"))) == 20


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
        ("node_input", lambda project: (project / "product" / "frontend" / "package.json").write_text('{"name":"fixture-changed","engines":{"node":">=24.13.0 <25"},"packageManager":"pnpm@11.21.0","scripts":{"build":"vite build"}}\n', encoding="utf-8"), {"pnpm_install": 1, "pnpm_build": 1}),
        ("pnpm_workspace_input", lambda project: (project / "product" / "frontend" / "pnpm-workspace.yaml").write_text("allowBuilds:\n  esbuild: false\nstoreDir: ../../var/cache/pnpm-store\n", encoding="utf-8"), {"pnpm_install": 1, "pnpm_build": 1}),
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
@pytest.mark.parametrize("missing", ["node_modules", "corrupt_node_modules", "pnpm_storage", "dist", "chromium", "database"])
def test_isolated_output_and_runtime_missingness_rebuilds_only_required_stage(tmp_path: Path, missing: str) -> None:
    project, shim, log, first = _run_isolated_fixture(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    before = _command_counts(log)
    if missing == "node_modules":
        shutil.rmtree(project / "product" / "frontend" / "node_modules")
    elif missing == "corrupt_node_modules":
        (project / "product" / "frontend" / "node_modules" / ".bin" / "tsc.cmd").unlink()
    elif missing == "pnpm_storage":
        shutil.rmtree(tmp_path / "var" / "cache" / "pnpm-store")
        shutil.rmtree(project / "product" / "frontend" / "node_modules" / ".pnpm")
    elif missing == "dist":
        shutil.rmtree(project / "product" / "frontend" / "dist")
    elif missing == "chromium":
        (tmp_path / "state" / "chromium-ready").unlink()
    elif missing == "database":
        (tmp_path / "var" / "jiejian.db").unlink()
    second = _run_start(tmp_path / "var", shim, log, cwd=project, script_path=project / "scripts" / "start.ps1")
    assert second.returncode == 0, f"{missing}: {second.stdout}{second.stderr}"
    assert not (project / "product" / "frontend" / "var").exists()
    after = _command_counts(log)
    expected = {
        "node_modules": {"pnpm_install": 1, "pnpm_build": 1},
        "corrupt_node_modules": {"pnpm_install": 1, "pnpm_build": 1},
        "pnpm_storage": {"pnpm_install": 1, "pnpm_build": 1},
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
    manifest.write_text('{\n  "storeDir": "D:\\\\stale-pnpm-store\\\\v11"\n}\n', encoding="utf-8")
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
    startup_log = next((var_dir / "logs" / "startup").glob("*.log")).read_text(encoding="utf-8")
    assert "损坏或版本未知" in startup_log
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
        'echo %* | findstr /c:"sys.executable" >nul\nif not errorlevel 1 (echo D:\\Miniconda\\envs\\jiejian_env\\python.exe& exit /b 0)\n'
        'echo %* | findstr /c:"require_python_environment" >nul\nif not errorlevel 1 (echo {"ok":true,"user_site_on_sys_path":false,"package_origins":{}}& exit /b 0)\n'
        'echo %* | findstr /c:"playwright install" >nul\nif not errorlevel 1 (>>"%SHIM_STATE%\\chromium-ready" echo 1& exit /b 0)\n'
        'echo %* | findstr /c:"playwright.sync_api" >nul\nif not errorlevel 1 if exist "%SHIM_STATE%\\chromium-ready" (echo %SHIM_CHROMIUM%& exit /b 0)\nif not errorlevel 1 if not exist "%SHIM_STATE%\\chromium-ready" exit /b 1\n'
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
        f"}}\n$env:SHIM_PYTHON = '{r'D:\Miniconda\envs\jiejian_env\python.exe'}'\n$env:SHIM_CHROMIUM = '{tmp_path / 'state' / 'chromium.exe'}'\n$env:SHIM_MIGRATION_HELPER = '{migration_helper}'\n$env:SHIM_REVISION_HELPER = '{revision_helper}'\n$env:SHIM_VAR_DIR = '{tmp_path / 'var'}'\n$env:SHIM_STORE_DIR = '{(tmp_path / 'var' / 'cache' / 'pnpm-store' / 'v11').as_posix()}'\n$env:SHIM_VIRTUAL_STORE_DIR = '{(project / 'product' / 'frontend' / 'node_modules' / '.pnpm').as_posix()}'\n. '{project / 'scripts' / 'start.ps1'}' -PrepareOnly -VarDir '{tmp_path / 'var'}'\n"
        f"if (Get-ChildItem -LiteralPath '{tmp_path / 'var' / 'logs' / 'startup'}' -Filter '*.log' | Get-Content | Select-String '失败阶段') {{ exit 21 }}\n",
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
    assert (tmp_path / "var" / "runtime" / "uv" / "0.11.12" / "x64" / "uv.cmd").is_file()
    assert len(list((tmp_path / "var" / "temp" / "downloads").glob("uv-*"))) == 0
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
    assert not list((tmp_path / "var" / "temp" / "downloads").glob("uv-*"))


@pytest.mark.essential
def test_start_script_is_the_only_startup_script() -> None:
    assert [path.name for path in ROOT.glob("start*.cmd")] == ["start.cmd"]
    assert [path.name for path in (ROOT / "scripts").iterdir() if path.suffix.lower() in {".ps1", ".cmd"}] == ["start.ps1"]
    assert not (ROOT / "scripts" / "setup-conda.ps1").exists()


@pytest.mark.essential
def test_frontend_declares_the_supported_node_line_and_exact_pnpm() -> None:
    package = json.loads(
        (ROOT / "product" / "frontend" / "package.json").read_text(
            encoding="utf-8"
        )
    )

    assert package["engines"]["node"] == ">=24.13.0 <25"
    assert package["packageManager"] == "pnpm@11.21.0"


@pytest.mark.essential
def test_node_runtime_uses_package_source_and_private_download_contract() -> None:
    runtime = (ROOT / "scripts" / "startup" / "runtime.ps1").read_text(encoding="utf-8-sig")
    product = (ROOT / "scripts" / "startup" / "product.ps1").read_text(encoding="utf-8-sig")
    start = SCRIPT.read_text(encoding="utf-8-sig")
    assert "Read-FrontendToolRequirements" in runtime
    assert "Get-Command pnpm" in runtime
    assert runtime.index('Push-Location -LiteralPath $frontend') < runtime.index("Get-Command pnpm")
    assert '$env:COREPACK_ENABLE_DOWNLOAD_PROMPT = "0"' in runtime
    assert "$script:SavedCorepackDownloadPrompt" in start
    assert "Remove-Item Env:COREPACK_ENABLE_DOWNLOAD_PROMPT" in start
    assert "$script:SavedJiejianCorepackExecutable" in start
    assert "Remove-Item Env:JIEJIAN_COREPACK_EXECUTABLE" in start
    assert 'Join-Path $env:PNPM_HOME "pnpm.cmd"' in runtime
    assert 'call `"%JIEJIAN_COREPACK_EXECUTABLE%`" pnpm %*' in runtime
    presentation = (ROOT / "scripts" / "startup" / "presentation.ps1").read_text(encoding="utf-8-sig")
    for label in (
        "正在查找 Node.js",
        "正在检查 pnpm",
        "正在查找 Python 环境",
        "正在验证 Python 环境",
        "正在准备 Python 依赖",
        "正在检查 Chromium",
        "正在准备 Chromium",
        "正在检查本地数据",
        "正在升级本地数据",
        "正在准备前端依赖",
        "正在构建界面",
        "正在启动界面",
    ):
        assert label in presentation
    for stage in ("node-search", "pnpm-check", "python-search", "python-verify", "chromium-check"):
        assert f'Start-WaitIndicator "{stage}"' in runtime
    assert "Get-Command pnpm).Source" not in product
    assert "https://nodejs.org/dist/v24.19.0/node-v24.19.0-win-x64.zip" in runtime
    assert "https://nodejs.org/dist/v24.19.0/node-v24.19.0-win-arm64.zip" in runtime
    assert "57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73" in runtime
    assert "8502f4a50b458d4cc38ed8f2001556c2cd239d464920f74017926ccb1e1c157f" in runtime
    assert "corepack enable" not in runtime.lower()


@pytest.mark.process
def test_corepack_fallback_exposes_pnpm_executable_to_downstream_processes(tmp_path: Path) -> None:
    shim, log = _make_shims(tmp_path, conda=True, uv=False, existing_env=True)
    (shim / "pnpm.cmd").unlink()
    _write_cmd(
        shim / "corepack.cmd",
        '>>"%SHIM_LOG%" echo corepack %*\n'
        'if not "%1"=="pnpm" exit /b 1\n'
        'if "%2"=="--version" (echo 11.21.0& exit /b 0)\n'
        'if "%2"=="install" goto install\n'
        'if "%2"=="build" goto build\n'
        'exit /b 1\n'
        ':install\n'
        'if not exist node_modules\\.bin mkdir node_modules\\.bin\n'
        'if not exist "%SHIM_STORE_DIR%" mkdir "%SHIM_STORE_DIR%"\n'
        'if not exist "%SHIM_VIRTUAL_STORE_DIR%" mkdir "%SHIM_VIRTUAL_STORE_DIR%"\n'
        '>node_modules\\.modules.yaml echo {& '
        '>>node_modules\\.modules.yaml echo   "storeDir": "%SHIM_STORE_DIR%",& '
        '>>node_modules\\.modules.yaml echo   "virtualStoreDir": "%SHIM_VIRTUAL_STORE_DIR%"& '
        '>>node_modules\\.modules.yaml echo }& '
        '>node_modules\\.bin\\tsc.cmd echo @exit /b 0& '
        '>node_modules\\.bin\\vite.cmd echo @exit /b 0\n'
        'exit /b 0\n'
        ':build\n'
        'if not exist dist mkdir dist\n'
        '>dist\\index.html echo built\n'
        'exit /b 0',
    )
    var_dir = tmp_path / "var"

    first = _run_start(var_dir, shim, log)
    assert first.returncode == 0, first.stdout + first.stderr
    private_shim = var_dir / "runtime" / "pnpm" / "pnpm.cmd"
    assert private_shim.read_bytes() == (
        b'@echo off\r\ncall "%JIEJIAN_COREPACK_EXECUTABLE%" pnpm %*\r\n'
    )
    state = json.loads(_state_path(var_dir).read_text(encoding="utf-8"))
    facts = state["phases"]["toolchain"]["facts"]
    assert Path(facts["pnpm_path"]) == private_shim
    assert facts["pnpm_runner"] == str(private_shim)

    second = _run_start(var_dir, shim, log)
    assert second.returncode == 0, second.stdout + second.stderr
    assert private_shim.is_file()
    assert not list((var_dir / "temp" / "downloads").glob("node-*"))


@pytest.mark.essential
def test_banner_menu_and_tree_contracts_are_frozen_in_the_startup_modules() -> None:
    presentation = (ROOT / "scripts" / "startup" / "presentation.ps1").read_text(
        encoding="utf-8-sig"
    )
    start = SCRIPT.read_text(encoding="utf-8-sig")
    product = (ROOT / "scripts" / "startup" / "product.ps1").read_text(
        encoding="utf-8-sig"
    )

    assert presentation.count("38;2;") == 1
    for rgb in (
        "@(0, 102, 153)",
        "@(0, 126, 174)",
        "@(0, 151, 194)",
        "@(32, 174, 211)",
        "@(82, 197, 226)",
        "@(145, 222, 239)",
    ):
        assert rgb in presentation
    assert "Write-Host $lines[$index] -ForegroundColor Cyan" in presentation
    assert "↑ ↓ 选择    Enter 确认" in presentation
    assert "输入编号后按 Enter 确认" in presentation
    assert 'Join-Path $script:ProjectRoot "scripts\\start.ps1"' in presentation
    assert "$PSCommandPath.Replace" not in presentation
    assert "SupportsVirtualTerminal" in start
    assert presentation.count("Read-StartupMenu \"") == 2
    assert "引导模式（推荐）" in presentation
    assert "普通命令行" in presentation
    assert "Write-DisplaySubtask" not in presentation + start + product
    assert 'Write-DisplayResult "本地数据" "完成" $true $script:MigrationDetail' in start
    first_option_draw = presentation.index("for ($index = 0; $index -lt $Items.Count; $index += 1)")
    footer = presentation.index('Write-Host "↑ ↓ 选择    Enter 确认"')
    assert presentation.index("Write-Host $Title") < first_option_draw < footer
    assert presentation.index('(\"{0}[s{0}[{1}A{0}[1G\"', footer) > footer
    assert presentation.index('(\"{0}[u\"', footer) > footer
    assert '" " * ($width - (Get-DisplayCellWidth $line))' not in presentation


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
        input="\n",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 37
    forwarded = forwarded_path.read_text(encoding="utf-8-sig").strip()
    assert forwarded == '-ForcePrepare|-PrepareOnly|-VarDir|"D:\\tmp\\界鉴-test"'
    command_text = CMD_SCRIPT.read_text(encoding="utf-8")
    assert "chcp 65001" in command_text
    assert "setlocal" in command_text
    assert 'if not "%START_EXIT%"=="0"' in command_text
    assert "pause >nul" in command_text
    assert "Startup failed. Press any key to close this window." in result.stdout
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
    product_text = (ROOT / "scripts" / "startup" / "product.ps1").read_text(encoding="utf-8-sig")
    assert "& $pythonLiteral -B -m product.backend.cli --var-dir `$varDir" in product_text
    assert "PackageRunner" not in product_text[product_text.index("function Invoke-CliShell"):]
    assert log_text.count(" run --locked --no-sync python -B -m product.backend.cli ") == 1
    assert not list(tmp_path.rglob("*PowerShell_profile.ps1"))


@pytest.mark.process
def test_direct_prepare_failure_returns_without_waiting(
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
def test_failure_pause_is_owned_by_root_start_cmd() -> None:
    command_text = CMD_SCRIPT.read_text(encoding="utf-8")
    powershell_text = "\n".join(
        path.read_text(encoding="utf-8-sig") for path in POWERSHELL_SCRIPTS
    )

    assert 'if not "%START_EXIT%"=="0"' in command_text
    assert "pause >nul" in command_text
    assert "WaitOnFailure" not in command_text + powershell_text
    assert "Wait-StartupFailureInput" not in powershell_text
