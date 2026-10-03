# 复核受控运行回执与解释器、浏览器身份。
from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.controlled.identity import require_python_environment
import tests.acceptance.sample_test.harness.state as sample_harness_state


_MAX_SOURCE_RECEIPT_BYTES = 1_048_576


_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class SourceRuntime:
    """从受控回执复核出的本轮解释器身份与浏览器输入。"""

    environment: dict[str, str]
    playwright_executable: Path
    frontend_dir: Path


def _required_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise sample_harness_state.SampleTestError(f"source receipt 缺少有效的 {label}")
    return value


def _required_text(source: Mapping[str, object], name: str) -> str:
    value = source.get(name)
    if not isinstance(value, str) or not value:
        raise sample_harness_state.SampleTestError(f"source receipt 缺少有效的 {name}")
    return value


def _load_source_runtime(
    receipt_path: Path,
    root: Path,
    var_dir: Path,
) -> SourceRuntime:
    """只信任真实 start.cmd 在本轮隔离目录中生成的 source receipt。"""

    try:
        if receipt_path.stat().st_size > _MAX_SOURCE_RECEIPT_BYTES:
            raise sample_harness_state.SampleTestError("source receipt 超出大小限制")
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except sample_harness_state.SampleTestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise sample_harness_state.SampleTestError("source receipt 不可读取或格式无效") from None
    receipt = _required_mapping(payload, "root")
    python = _required_mapping(receipt.get("python"), "python")
    playwright = _required_mapping(receipt.get("playwright"), "playwright")
    frontend = _required_mapping(receipt.get("frontend"), "frontend")
    if _required_text(receipt, "schema_version") != "1":
        raise sample_harness_state.SampleTestError("source receipt 版本不受支持")
    executable = Path(_required_text(python, "executable")).resolve()
    environment_path = Path(_required_text(python, "environment_path")).resolve()
    fingerprint = _required_text(python, "runtime_fingerprint")
    playwright_executable = Path(_required_text(playwright, "executable")).resolve()
    browsers_path = Path(_required_text(playwright, "browsers_path")).resolve()
    frontend_dir = Path(_required_text(frontend, "dist")).resolve()
    if (
        Path(_required_text(receipt, "project_root")).resolve() != root
        or Path(_required_text(receipt, "var_dir")).resolve() != var_dir
        or executable != Path(sys.executable).resolve()
        or environment_path != Path(sys.prefix).resolve()
        or _required_text(python, "environment_type") != "conda"
        or _required_text(receipt, "runtime_mode") != "development"
        or _FINGERPRINT.fullmatch(fingerprint) is None
        or not (frontend_dir / "index.html").is_file()
        or not playwright_executable.is_file()
        or not browsers_path.is_dir()
    ):
        raise sample_harness_state.SampleTestError("source receipt 与当前受控运行输入不一致")
    system_values = {
        name: os.environ[name]
        for name in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR")
        if os.environ.get(name)
    }
    temporary = RuntimePaths(var_dir).temp
    temporary.mkdir(parents=True, exist_ok=True)
    system_root = system_values.get("SYSTEMROOT") or system_values.get("WINDIR")
    path_entries = [str(executable.parent)]
    if system_root:
        path_entries.append(str(Path(system_root) / "System32"))
    environment = {
        **system_values,
        "JIEJIAN_PYTHON_EXECUTABLE": str(executable),
        "JIEJIAN_PYTHON_ENVIRONMENT_PATH": str(environment_path),
        "JIEJIAN_PYTHON_ENVIRONMENT_TYPE": "conda",
        "JIEJIAN_PROJECT_ROOT": str(root),
        "JIEJIAN_RUNTIME_FINGERPRINT": fingerprint,
        "JIEJIAN_RUNTIME_MODE": "development",
        "JIEJIAN_VAR_DIR": str(var_dir),
        "JIEJIAN_FRONTEND_DIST": str(frontend_dir),
        "JIEJIAN_PLAYWRIGHT_EXECUTABLE": str(playwright_executable),
        "PLAYWRIGHT_BROWSERS_PATH": str(browsers_path),
        "PATH": os.pathsep.join(dict.fromkeys(path_entries)),
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    try:
        require_python_environment(environment)
    except JiejianError as exc:
        raise sample_harness_state.SampleTestError(
            f"source receipt 运行身份复核失败: {exc.code}"
        ) from None
    return SourceRuntime(
        environment=environment,
        playwright_executable=playwright_executable,
        frontend_dir=frontend_dir,
    )
