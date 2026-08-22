from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[2]
START = ROOT / "scripts" / "start.ps1"
DEV = ROOT / "scripts" / "dev.ps1"
START_CMD = ROOT / "start.cmd"
STARTUP = ROOT / "scripts" / "startup"
RELEASE = STARTUP / "release.ps1"
RUNTIME = STARTUP / "runtime.ps1"
PRODUCT = STARTUP / "product.ps1"
PRESENTATION = STARTUP / "presentation.ps1"
POWERSHELL = (
    shutil.which("powershell")
    or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_product_start_uses_release_assets_without_node_or_frontend_build() -> None:
    source = _text(START)

    assert '"release.ps1"' in source
    assert "Read-ReleaseToolchain" in source
    assert "Prepare-ReleasePython" in source
    assert "Prepare-ReleaseChromium" in source
    assert "Confirm-ReleaseFrontend" in source
    assert "Write-ReleaseRuntimeState" in source
    assert "Test-NodeAndPnpm" not in source
    assert "Prepare-PythonDependencies" not in source
    assert "Prepare-Frontend" not in source
    assert "-PrepareOnly" not in source
    assert 'Node.js / pnpm" "跳过"' in source


def test_prepare_lock_precedes_state_and_runtime_mutation() -> None:
    start = _text(START)
    dev = _text(DEV)

    assert start.index("Enter-ReleasePrepareLock") < start.index("Load-PrepareState")
    assert start.index("Enter-ReleasePrepareLock") < start.index("Resolve-ReleaseUv")
    assert dev.index("Enter-PrepareLock\n    Read-State") > 0
    assert dev.index("Enter-PrepareLock\n    Read-State") < dev.index(
        'if ($Command -eq "update")'
    )


def test_development_entry_owns_lock_updates_and_fixed_release_build_tools() -> None:
    source = _text(DEV)
    project = _text(ROOT / "pyproject.toml")
    manifest = json.loads((ROOT / "product" / "config" / "toolchain.json").read_text(encoding="utf-8"))

    for command in ("bootstrap", "sync", "update", "start", "test", "shell", "package"):
        assert f'"{command}"' in source
    assert source.count('"lock"') >= 2
    assert 'Invoke-External "uv-update"' in source
    assert "Invoke-WebRequest" in source
    assert 'runtime\\build\\node' in source
    assert 'runtime\\build\\pnpm' in source
    assert '[string[]]$arguments' in source
    assert '"setuptools>=80,<84"' in project
    assert '$python -S -B -c' in source
    assert 'Test-Path -LiteralPath $script:StatePath -PathType Leaf' in source
    assert 'catch [IO.FileNotFoundException]' not in source
    assert '[string]$backup, $true' in source
    assert manifest["python"]["supported_minor"] == "3.13"
    assert manifest["uv"]["version"] == "0.11.12"
    assert manifest["node"]["build_version"] == "24.19.0"
    assert manifest["pnpm"]["version"] == "11.21.0"
    assert manifest["pnpm"]["integrity"].startswith("sha512-")


def test_uv_partial_download_keeps_zip_extension_for_expand_archive() -> None:
    for path in (DEV, RELEASE):
        source = _text(path)
        assert 'cache\\downloads\\.tmp-{0}-{1}' in source
        assert "Expand-Archive -LiteralPath $partial" in source
        assert 'cache\\downloads\\{0}.partial' not in source


def test_release_identity_runs_from_outside_repository_and_installs_wheel() -> None:
    source = _text(RELEASE)

    assert "Push-Location -LiteralPath $script:ReleaseLaunchRoot" in source
    assert '"--no-install-project"' in source
    assert '"--no-dev"' in source
    assert '"pip",' in source and '"install",' in source and '"--no-deps"' in source
    assert 'JIEJIAN_RUNTIME_MODE = "release"' in source
    assert 'runtime\\release-artifacts' in source
    assert 'Join-Path $script:ProjectRoot "dist"' not in source
    assert "package_origins.product" in source
    assert '"frontend\\dist"' in source
    assert "JIEJIAN_NODE_EXECUTABLE" in source
    assert "Remove-Item Env:JIEJIAN_NODE_EXECUTABLE" in source


def test_startup_uses_new_database_and_frontend_paths() -> None:
    product = _text(PRODUCT)
    start = _text(START)

    assert 'Join-Path $script:VarDir "data\\jiejian.db"' in product
    assert 'Join-Path $script:VarDir "jiejian.db"' not in product
    assert '"--frontend-dir", $script:FrontendDist' in start
    assert '"--frontend-dir", (Join-Path $script:ProjectRoot' not in start
    assert 'runtime\\release-artifacts' in _text(DEV)


def test_external_command_wrapper_preserves_single_argument_arrays() -> None:
    assert "[string[]]$arguments" in _text(DEV)
    assert "[object[]]$invokeArguments" in _text(RUNTIME)


def test_startup_powershell_files_parse_and_keep_utf8_bom() -> None:
    files = (START, DEV, *sorted(STARTUP.glob("*.ps1")))
    for path in files:
        literal = str(path).replace("'", "''")
        command = (
            "$tokens=$null;$errors=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{literal}',"
            "[ref]$tokens,[ref]$errors)|Out-Null;"
            "if($errors.Count -gt 0){$errors|ForEach-Object{Write-Error $_.Message};exit 1}"
        )
        result = subprocess.run(
            [POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"{path}\n{result.stdout}{result.stderr}"
        assert path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_root_batch_is_ascii_without_bom_and_preserves_exit_code() -> None:
    payload = START_CMD.read_bytes()
    source = payload.decode("ascii")

    assert not payload.startswith(b"\xef\xbb\xbf")
    assert '"%POWERSHELL_EXE%"' in source
    assert "%*" in source
    assert "set \"START_EXIT=%ERRORLEVEL%\"" in source
    assert "exit /b %START_EXIT%" in source
    assert "pause >nul" in source


def test_display_result_keeps_chinese_labels_and_selection_hint() -> None:
    presentation = _text(PRESENTATION)

    assert "↑ ↓ 选择" in presentation
    assert "Enter 确认" in presentation
    assert '"图形界面"' in presentation
    assert '"命令行"' in presentation
    assert '"仅完成环境准备"' in presentation
