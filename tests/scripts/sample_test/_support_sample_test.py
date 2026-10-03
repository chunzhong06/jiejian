# 隔离验收脚本的共享构造器与环境输入。
from __future__ import annotations
import json
import sys
from pathlib import Path
from uuid import uuid4
from product.backend.infra.runtime.process.controlled.identity import python_environment_report

ROOT = Path(__file__).resolve().parents[3]

COMMON_IDENTITY_NAMES = {
    "JIEJIAN_PYTHON_EXECUTABLE",
    "JIEJIAN_PYTHON_ENVIRONMENT_PATH",
    "JIEJIAN_PYTHON_ENVIRONMENT_TYPE",
    "JIEJIAN_PROJECT_ROOT",
    "JIEJIAN_RUNTIME_FINGERPRINT",
    "JIEJIAN_RUNTIME_MODE",
    "JIEJIAN_VAR_DIR",
}

def _fresh_real_probe_dir() -> Path:
    """把真实 Windows 探针证据保留在稳定 var 边界，避免 pytest 清理后丢失。"""

    run_dir = ROOT / "var" / "test" / "sample-test" / "probes" / uuid4().hex
    run_dir.mkdir(parents=True)
    print(f"L5 probe artifacts: {run_dir}", flush=True)
    return run_dir

def _write_receipt(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    report = python_environment_report()
    assert report["ok"] is True, report["issues"]
    var_dir = tmp_path / "prepared-var"
    var_dir.mkdir()
    frontend = var_dir / "runtime" / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    browser = tmp_path / "browser.exe"
    browser.write_bytes(b"controlled-browser-placeholder")
    browsers_path = tmp_path / "browsers"
    browsers_path.mkdir()
    receipt = {
        "schema_version": "1",
        "project_root": str(ROOT),
        "var_dir": str(var_dir),
        "runtime_mode": "development",
        "python": {
            "executable": str(Path(sys.executable).resolve()),
            "environment_path": str(Path(sys.prefix).resolve()),
            "environment_type": "conda",
            "runtime_fingerprint": report["runtime_fingerprint"],
        },
        "playwright": {
            "executable": str(browser),
            "browsers_path": str(browsers_path),
        },
        "frontend": {"dist": str(frontend)},
    }
    receipt_path = var_dir / "runtime" / "source" / "receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path, var_dir, frontend, browser
