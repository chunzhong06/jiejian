# Project CLI 命令组
# 解析 WebExecutionProfile 路径并调用共享输入校验，输出稳定 Project 摘要。

from __future__ import annotations

from pathlib import Path

import typer

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import parse_web_execution_profile
from product.backend.cli.presentation import emit_json, fail


def project_validate_command(path: Path) -> None:
    """离线校验当前 Web 执行配置及其治理引用。"""

    try:
        profile = parse_web_execution_profile(path.read_bytes())
        emit_json(
            {
                "schema_version": "1",
                "kind": "project",
                "valid": True,
                "project_id": profile.project_id,
                "profile_id": profile.profile_id,
                "contract_id": profile.contract_id,
                "contract_version": profile.contract_version,
            }
        )
    except JiejianError as exc:
        fail(exc)
    except (OSError, ValueError):
        fail(JiejianError(ErrorCode.INPUT_FILE, "Web 执行配置（WebExecutionProfile）文件不可读取"))
