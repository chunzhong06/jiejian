# =============================================================================
# CLI 输出与失败映射
#
# 定位
#   应用返回值和稳定命令行 JSON、退出码之间的唯一展示边界
#
# 职责
#   输出确定性 JSON｜脱敏错误详情｜保持稳定退出码
#
# 调用链
#   cli.commands.* → presentation → stdout / stderr / Typer exit
# =============================================================================

from __future__ import annotations

import json
from typing import NoReturn

import typer

from ..errors import ErrorCode, JiejianError


def emit_json(payload: object) -> None:
    typer.echo(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def fail(error: JiejianError) -> NoReturn:
    typer.echo(
        json.dumps(
            {"schema_version": "1", "error": error.to_dict()},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        err=True,
    )
    input_codes = {
        ErrorCode.CFG_FILE.value,
        ErrorCode.CFG_INVALID.value,
        ErrorCode.INPUT_FILE.value,
        ErrorCode.INPUT_INVALID.value,
        ErrorCode.INPUT_PATH.value,
        ErrorCode.SECRET_MISSING.value,
        ErrorCode.REPORT_NOT_FOUND.value,
        ErrorCode.RECORD_NOT_FOUND.value,
        ErrorCode.RECORD_REVIEW_STATE.value,
        ErrorCode.RECORD_DRAFT_UNCONFIRMED.value,
        ErrorCode.RECORD_DRAFT_REFERENCE.value,
        ErrorCode.RECORD_DRAFT_NOT_ADJACENT.value,
    }
    safety_codes = {
        ErrorCode.SCOPE_URL.value,
        ErrorCode.SCOPE_HOST.value,
        ErrorCode.SCOPE_PORT.value,
        ErrorCode.SCOPE_PRIVATE_NETWORK.value,
        ErrorCode.SCOPE_REDIRECT.value,
        ErrorCode.EXEC_BUDGET.value,
        ErrorCode.EXEC_RESPONSE_TOO_LARGE.value,
    }
    if error.code == ErrorCode.EXEC_CANCELLED.value:
        raise typer.Exit(code=130)
    raise typer.Exit(
        code=3 if error.code in input_codes else 5 if error.code in safety_codes else 4
    )
