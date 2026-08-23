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
SOURCE = STARTUP / "source.ps1"
RUNTIME = STARTUP / "runtime.ps1"
PRESENTATION = STARTUP / "presentation.ps1"
POWERSHELL = (
    shutil.which("powershell")
    or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)


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
    assert "Wheel" in source  # 文件信息卡明确 Wheel 不参与普通启动。
    assert "Get-ReleaseWheel" not in source
    assert "Prepare-ReleasePython" not in source


def test_development_prepare_lock_precedes_state_and_runtime_mutation() -> None:
    dev = _text(DEV)

    assert dev.index("Enter-PrepareLock\n    Read-State") > 0
    assert dev.index("Enter-PrepareLock\n    Read-State") < dev.index(
        'if ($Command -eq "update")'
    )


def test_development_entry_owns_lock_updates_and_fixed_build_tools() -> None:
    source = _text(DEV)
    project = _text(ROOT / "pyproject.toml")
    manifest = json.loads((ROOT / "product" / "config" / "toolchain.json").read_text(encoding="utf-8"))

    for command in (
        "bootstrap",
        "sync",
        "update",
        "prepare",
        "start",
        "cli",
        "test",
        "frontend-test",
        "shell",
        "package",
    ):
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
    source = _text(DEV)
    assert 'cache\\downloads\\.tmp-{0}-{1}' in source
    assert "Expand-Archive -LiteralPath $partial" in source
    assert 'cache\\downloads\\{0}.partial' not in source


def test_source_receipt_requires_editable_current_repository_and_var_frontend() -> None:
    source = _text(SOURCE)
    dev = _text(DEV)

    assert '"prepare"' in source
    assert "project_distribution.editable" in source
    assert "project_distribution.source_root" in source
    assert 'runtime\\frontend' in source
    assert 'runtime\\source\\receipt.json' in source
    assert 'JIEJIAN_RUNTIME_MODE = "development"' in source
    assert "Get-ReleaseWheel" not in source + dev
    assert "pip install" not in source
    assert "frontend-receipt.json" in dev
    assert 'runtime\\build\\frontend-workspace' in dev
    assert "recordHit" in dev
    assert source.index("Invoke-SourcePreparation") < source.index("Import-SourceReceipt")


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
        "schema_version": "1",
        "project_root": str(project_root),
        "var_dir": str(var_dir),
        "runtime_mode": "development",
        "python": {
            "executable": str(python),
            "version": "3.13.test",
            "environment_path": str(environment_path),
            "environment_type": "conda",
            "runtime_fingerprint": "relocated-test",
            "report": {
                "ok": True,
                "project_distribution": {
                    "editable": True,
                    "source_root": str(project_root),
                },
            },
        },
        "uv": {"executable": str(uv), "version": "test"},
        "node": {"executable": "", "version": ""},
        "pnpm": {"executable": "", "version": ""},
        "playwright": {
            "executable": str(chromium),
            "browsers_path": str(browsers),
        },
        "frontend": {
            "dist": str(frontend),
            "dependencies": "test",
            "build_state": "test",
        },
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    command = (
        "function Fail-Start { param($Code,$Stage,$Message,$Recovery); "
        "throw ($Stage + ':' + $Message) };"
        "function Get-RecoveryCommand { return 'recover' };"
        f"$script:ProjectRoot={_powershell_literal(project_root)};"
        f"$script:VarDir={_powershell_literal(var_dir)};"
        f"$script:ToolchainPath={_powershell_literal(project_root / 'product/config/toolchain.json')};"
        f". {_powershell_literal(SOURCE)};"
        "Import-SourceReceipt;"
        "if (-not (Test-ExactPath $env:JIEJIAN_PROJECT_ROOT $script:ProjectRoot)) { exit 91 };"
        "Write-Output 'RECEIPT_OK'"
    )

    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    accepted = subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert "RECEIPT_OK" in accepted.stdout

    receipt["project_root"] = str(ROOT.resolve())
    receipt["python"]["report"]["project_distribution"]["source_root"] = str(
        ROOT.resolve()
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    rejected = subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-Command", command],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode != 0


def test_startup_uses_new_database_and_frontend_paths() -> None:
    start = _text(START)
    dev = _text(DEV)

    assert "default_database_path" in dev
    assert 'Join-Path $script:VarDir "jiejian.db"' not in dev
    assert '"--frontend-dir", $script:FrontendDist' in start
    assert '"--frontend-dir", (Join-Path $script:ProjectRoot' not in start
    assert 'runtime\\frontend' in dev
    assert 'runtime\\release-artifacts' in dev
    assert 'JIEJIAN_FRONTEND_OUT_DIR' in _text(ROOT / "product" / "frontend" / "vite.config.ts")
    assert 'JIEJIAN_FRONTEND_CACHE_DIR' in _text(ROOT / "product" / "frontend" / "vite.config.ts")


def test_frontend_install_build_test_and_package_stay_outside_source_tree() -> None:
    dev = _text(DEV)

    assert 'function Get-FrontendSourceInputs' in dev
    assert 'Prepare-FrontendWorkspace $Toolchain $inputs $fingerprint' in dev
    assert 'Invoke-External "frontend-test"' in dev
    assert '$modules = Join-Path $frontend' not in dev
    assert 'Push-Location -LiteralPath $frontend' not in dev
    assert 'Prepare-PackageFrontend' not in dev
    for legacy in ("node_modules", "dist", "tsconfig.tsbuildinfo"):
        assert f'(Join-Path $frontend "{legacy}")' in dev


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
