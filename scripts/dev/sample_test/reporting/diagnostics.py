# 输出有界且无秘密的失败位置与验收汇总。
from __future__ import annotations

import json
import os
import re
import traceback
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import Error as PlaywrightError
import scripts.dev.sample_test.harness.state as sample_harness_state


def _write_summary(audit_dir: Path, payload: dict[str, object]) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / "sample-test-summary.json"
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _failure_identity(error: Exception) -> tuple[str, str]:
    """把主错误压缩成稳定、无秘密的审计字段。"""

    if isinstance(error, sample_harness_state.SampleTestError):
        summary = str(error)
        token = summary.split(":", 1)[0]
        code = token if re.fullmatch(r"[A-Z][A-Z0-9_]+", token) else type(error).__name__.upper()
        return code, summary[:512]
    if isinstance(error, PlaywrightError):
        return "PLAYWRIGHT_ERROR", "Playwright 自动化边界失败"
    return type(error).__name__.upper(), "自动 L5 出现未分类失败"


def _write_failure(
    audit_dir: Path,
    error: Exception,
    state: sample_harness_state.HarnessState,
    cleanup: Mapping[str, object],
    *,
    control_closed: bool,
    sample_closed: bool | None,
    process_tree_closed: bool,
) -> None:
    code, summary = _failure_identity(error)
    # 只保留本仓库脚本帧，定位失败动作；不记录可能含会话/凭据的浏览器异常正文。
    location = []
    cause = error
    for _ in range(4):
        if cause is None:
            break
        location.extend(f"{Path(frame.filename).resolve().relative_to(Path(__file__).resolve().parents[1]).as_posix()}:{frame.lineno}:{frame.name}"
                        for frame in traceback.extract_tb(cause.__traceback__)
                        if Path(frame.filename).resolve().is_relative_to(Path(__file__).resolve().parents[1]))
        cause = cause.__cause__ or cause.__context__
    location = location[-12:]
    screenshots = [path.relative_to(audit_dir).as_posix() for path in sorted(audit_dir.glob("*.png"))]
    _write_summary(
        audit_dir,
        {
            "schema_version": "1",
            "l5_stage": state.stage,
            "failure_code": code,
            "primary_failure": summary,
            "failure_location": location,
            "active_run_id": state.active_run_id,
            "active_run_job_id": state.active_run_job_id,
            "cleanup": dict(cleanup),
            "resources": {
                "control_port_closed": control_closed,
                "sample_port_closed": sample_closed,
                "owned_process_tree_closed": process_tree_closed,
            },
            "logs": ["../../logs/sample-test-start.log"],
            "screenshots": screenshots,
        },
    )
    (audit_dir / "sample-test-summary.json").replace(audit_dir / "failure.json")
