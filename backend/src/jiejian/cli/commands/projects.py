# =============================================================================
# Project CLI 命令组
#
# 定位
#   Project bundle 离线校验的命令行适配器
#
# 职责
#   解析路径｜调用共享输入校验｜输出稳定 Project 摘要
#
# 调用链
#   Typer → project commands → Verification input loader
# =============================================================================

from __future__ import annotations

from pathlib import Path

import typer

from ...errors import JiejianError
from ...verification.inputs import load_project_bundle
from ..presentation import emit_json, fail


def project_validate_command(path: Path) -> None:
    """离线校验项目、Flow、默认 Contract 及交叉引用。"""

    try:
        bundle = load_project_bundle(path)
        emit_json(
            {
                "schema_version": "1",
                "kind": "project",
                "valid": True,
                "project_id": bundle.project.id,
                "flow_id": bundle.flow.id,
                "contract_id": bundle.contract.id,
            }
        )
    except JiejianError as exc:
        fail(exc)
