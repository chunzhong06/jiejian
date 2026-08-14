# =============================================================================
# ExecutionRequest 持久快照
#
# 定位
#   提交时应用状态与后续 Runner 输入之间的不可变文件边界
#
# 职责
#   规范编码请求｜原子写入与哈希校验｜加载时拒绝 secret、重复键和非有限值
#
# 调用链
#   ExecutionSubmissionService → ExecutionRequestStore → WorkerSupervisor / RunnerInputV1
# =============================================================================

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from ..domain.identifiers import JOB_ID_PATTERN
from ..errors import ErrorCode, JiejianError
from ..protocols import (
    RUNNER_INPUT_MAX_BYTES,
    RUNNER_V2_INPUT_MAX_BYTES,
    ExecutionBudgetV1,
    ExecutionBudgetV2,
    ExecutionProjectSnapshotV1,
    ExecutionProjectSnapshotV2,
    required_secret_refs_v2,
)


class PersistedExecutionRequestV1(BaseModel):
    """不含运行时关联字段和真实秘密的不可变执行内容。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"
    budget: ExecutionBudgetV1
    project_snapshot: ExecutionProjectSnapshotV1

    @model_validator(mode="after")
    def validate_budget_snapshot(self) -> PersistedExecutionRequestV1:
        target = self.project_snapshot.target
        if self.budget.max_requests != target.max_requests:
            raise ValueError("request budget max_requests does not match snapshot")
        if self.budget.max_response_bytes != target.max_response_bytes:
            raise ValueError("request response budget does not match snapshot")
        if self.budget.request_timeout_us != int(target.timeout_seconds * 1_000_000):
            raise ValueError("request timeout does not match snapshot")
        return self


class PersistedExecutionRequestV2(BaseModel):
    """V2 不可变执行快照；运行时 job/lease 字段仍由 Worker 注入。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["2"] = "2"
    budget: ExecutionBudgetV2
    project_snapshot: ExecutionProjectSnapshotV2

    @model_validator(mode="after")
    def validate_budget_snapshot(self) -> PersistedExecutionRequestV2:
        target = self.project_snapshot.target
        if self.budget.max_requests != target.max_requests:
            raise ValueError("request budget max_requests does not match snapshot")
        if self.budget.max_response_bytes != target.max_response_bytes:
            raise ValueError("request response budget does not match snapshot")
        if self.budget.request_timeout_us != int(target.timeout_seconds * 1_000_000):
            raise ValueError("request timeout does not match snapshot")
        if self.budget.max_cases < len(self.project_snapshot.plan.cases):
            raise ValueError("max_cases cannot be smaller than the permission plan")
        return self


PersistedExecutionRequest = PersistedExecutionRequestV1 | PersistedExecutionRequestV2


class ExecutionRequestStore:
    """以 job_id 定位请求文件，并用 request_hash 绑定数据库记录。"""

    def __init__(self, var_dir: Path) -> None:
        self._root = var_dir.resolve() / "jobs"

    def write(
        self,
        job_id: str,
        request: PersistedExecutionRequest,
        *,
        known_secrets: Sequence[str] = (),
    ) -> tuple[str, bool]:
        encoded = canonical_execution_request_bytes(
            request,
            known_secrets=known_secrets,
        )
        request_hash = hashlib.sha256(encoded).hexdigest()
        path = self.path_for(job_id)
        if path.exists():
            existing = self.load(
                job_id,
                expected_hash=request_hash,
                known_secrets=known_secrets,
            )
            if existing != request:
                raise JiejianError(
                    ErrorCode.JOB_REQUEST_CONFLICT,
                    "任务执行请求与既有快照不一致",
                )
            return request_hash, False
        temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_inside_root(path.parent)
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != request_hash:
                raise JiejianError(
                    ErrorCode.JOB_REQUEST_CONFLICT,
                    "任务执行请求写入校验失败",
                )
            os.replace(temporary, path)
            return request_hash, True
        except JiejianError:
            raise
        except OSError:
            raise JiejianError(
                ErrorCode.JOB_PERSISTENCE,
                "任务执行请求写入失败",
            ) from None
        finally:
            temporary.unlink(missing_ok=True)

    def load(
        self,
        job_id: str,
        *,
        expected_hash: str,
        known_secrets: Sequence[str] = (),
    ) -> PersistedExecutionRequest:
        path = self.path_for(job_id)
        if not path.is_file():
            raise JiejianError(
                ErrorCode.JOB_REQUEST_MISSING,
                "任务执行请求不存在",
            )
        try:
            if path.stat().st_size > RUNNER_INPUT_MAX_BYTES:
                raise JiejianError(
                    ErrorCode.JOB_REQUEST_CONFLICT,
                    "任务执行请求超过大小限制",
                )
            raw = path.read_bytes()
        except JiejianError:
            raise
        except OSError:
            raise JiejianError(
                ErrorCode.JOB_REQUEST_MISSING,
                "任务执行请求不可读取",
            ) from None
        digest = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(digest, expected_hash):
            raise JiejianError(
                ErrorCode.JOB_REQUEST_CONFLICT,
                "任务执行请求哈希不匹配",
            )
        parsed = parse_execution_request(raw, known_secrets=known_secrets)
        if canonical_execution_request_bytes(
            parsed,
            known_secrets=known_secrets,
        ) != raw:
            raise JiejianError(
                ErrorCode.JOB_REQUEST_CONFLICT,
                "任务执行请求不是规范 JSON",
            )
        return parsed

    def remove_if_matches(self, job_id: str, request_hash: str) -> None:
        """只清理本次创建且哈希仍匹配的孤儿请求。"""

        path = self.path_for(job_id)
        if not path.is_file():
            return
        try:
            if not hmac.compare_digest(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                request_hash,
            ):
                return
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass
        except OSError:
            raise JiejianError(
                ErrorCode.JOB_PERSISTENCE,
                "孤儿任务执行请求清理失败",
            ) from None

    def path_for(self, job_id: str) -> Path:
        if re.fullmatch(JOB_ID_PATTERN, job_id) is None:
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务 ID 格式无效")
        path = self._root / job_id / "request.json"
        self._ensure_inside_root(path.parent)
        return path

    def _ensure_inside_root(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(self._root):
            raise JiejianError(
                ErrorCode.JOB_REQUEST_CONFLICT,
                "任务执行请求路径越界",
            )


def canonical_execution_request_bytes(
    request: PersistedExecutionRequest,
    *,
    known_secrets: Sequence[str] = (),
) -> bytes:
    if not isinstance(request, (PersistedExecutionRequestV1, PersistedExecutionRequestV2)):
        raise TypeError("execution request serializer requires a supported model")
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
        raise JiejianError(
            ErrorCode.JOB_REQUEST_CONFLICT,
            "任务执行请求无法规范序列化",
        ) from None
    maximum = RUNNER_INPUT_MAX_BYTES if isinstance(request, PersistedExecutionRequestV1) else RUNNER_V2_INPUT_MAX_BYTES
    if len(encoded) > maximum:
        raise JiejianError(
            ErrorCode.JOB_REQUEST_CONFLICT,
            "任务执行请求超过大小限制",
        )
    return encoded


def parse_execution_request(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> PersistedExecutionRequest:
    if not isinstance(raw, bytes):
        raise TypeError("execution request parser requires bytes")
    if len(raw) > max(RUNNER_INPUT_MAX_BYTES, RUNNER_V2_INPUT_MAX_BYTES) or raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求格式无效")
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
        _reject_known_secrets(parsed, known_secrets)
        if not isinstance(parsed, dict):
            raise ValueError("request must be an object")
        version = parsed.get("schema_version")
        if version == "1":
            model = PersistedExecutionRequestV1
            maximum = RUNNER_INPUT_MAX_BYTES
        elif version == "2":
            model = PersistedExecutionRequestV2
            maximum = RUNNER_V2_INPUT_MAX_BYTES
        else:
            raise ValueError("unsupported request schema version")
        if len(raw) > maximum:
            raise ValueError("request is too large")
        return model.model_validate_json(raw, strict=True)
    except JiejianError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError):
        raise JiejianError(
            ErrorCode.JOB_REQUEST_CONFLICT,
            "任务执行请求格式无效",
        ) from None


def required_secret_names(request: PersistedExecutionRequest) -> tuple[str, ...]:
    """返回本次 Runner 实际边界需要的 env 名称，不解析或读取秘密。"""

    snapshot = request.project_snapshot
    if isinstance(request, PersistedExecutionRequestV1):
        references = [identity.secret_ref for identity in snapshot.identities]
    else:
        references = list(required_secret_refs_v2(snapshot))
    return tuple(dict.fromkeys(reference.removeprefix("env:") for reference in references))


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
