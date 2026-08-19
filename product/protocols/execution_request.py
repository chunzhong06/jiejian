# =============================================================================
# 持久执行请求协议
#
# 定位
# Application Core、Job 存储与 Worker 之间的唯一冻结执行快照。
#
# 职责
# 组合执行预算与项目快照｜校验秘密引用｜编码有界 canonical JSON
#
# 边界
# 不包含秘密正文、不读取 Profile 源文件，也不允许 Worker 重新解释治理配置。
#
# 调用链
# ExecutionWorkflow → ExecutionRequestStore → Worker / RunnerInput
# =============================================================================

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.runner import (
    ExecutionBudget,
    ExecutionProjectSnapshot,
    RUNNER_INPUT_MAX_BYTES,
    required_secret_refs,
)


class PersistedExecutionRequest(BaseModel):
    """Worker 使用的不可变、无路径执行快照。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    schema_version: Literal["2"] = "2"
    budget: ExecutionBudget
    project_snapshot: ExecutionProjectSnapshot

    @model_validator(mode="after")
    def validate_budget_snapshot(self) -> PersistedExecutionRequest:
        target = self.project_snapshot.target.scope
        if self.budget.max_requests != target.max_requests:
            raise ValueError("request budget max_requests does not match snapshot")
        if self.budget.max_response_bytes != target.max_response_bytes:
            raise ValueError("request response budget does not match snapshot")
        if self.budget.request_timeout_us != int(target.timeout_seconds * 1_000_000):
            raise ValueError("request timeout does not match snapshot")
        if self.budget.max_cases < len(self.project_snapshot.plan.cases):
            raise ValueError("max_cases cannot be smaller than the permission plan")
        return self


def canonical_execution_request_bytes(
    request: PersistedExecutionRequest,
    *,
    known_secrets: Sequence[str] = (),
) -> bytes:
    if not isinstance(request, PersistedExecutionRequest):
        raise TypeError("execution request serializer requires the current model")
    payload = request.model_dump(mode="json")
    _reject_known_secrets(payload, known_secrets)
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求无法规范序列化") from None
    if len(encoded) > RUNNER_INPUT_MAX_BYTES:
        raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求超过大小限制")
    return encoded


def parse_execution_request(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> PersistedExecutionRequest:
    if not isinstance(raw, bytes):
        raise TypeError("execution request parser requires bytes")
    if len(raw) > RUNNER_INPUT_MAX_BYTES or raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求格式无效")
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
        _reject_known_secrets(parsed, known_secrets)
        if not isinstance(parsed, dict) or parsed.get("schema_version") != "2":
            raise ValueError("unsupported request schema version")
        return PersistedExecutionRequest.model_validate_json(raw, strict=True)
    except JiejianError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError):
        raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求格式无效") from None


def required_secret_names(request: PersistedExecutionRequest) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(reference.removeprefix("env:") for reference in required_secret_refs(request.project_snapshot))
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    if value in {"NaN", "Infinity", "-Infinity"} or not math.isfinite(float(value)):
        raise ValueError("non-finite number")


def _reject_known_secrets(value: Any, known_secrets: Sequence[str]) -> None:
    if any(not isinstance(secret, str) for secret in known_secrets):
        raise TypeError("known_secrets must contain strings")
    secrets = tuple(secret for secret in known_secrets if secret)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str) and any(secret in item for secret in secrets):
            raise JiejianError(ErrorCode.JOB_SECRET, "任务执行请求包含敏感内容")
        if isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            pending.extend(item)
