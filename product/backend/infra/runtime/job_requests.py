# =============================================================================
# Execution Request 文件存储
#
# 定位
# 冻结执行请求与 Worker 按 hash 读取之间的不可变文件边界。
#
# 职责
# 有界编码请求｜原子创建快照｜按 expected hash 读取｜精确清理孤立文件
#
# 边界
# 请求不含 secret 正文；既有不同内容不得覆盖，路径和文件类型必须保持在受控 var 子树。
#
# 调用链
# ExecutionWorkflow / RunSubmission → ExecutionRequestStore → Worker
# =============================================================================

from __future__ import annotations

import hashlib
import hmac
import os
import re
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.identifiers import JOB_ID_PATTERN
from product.protocols import RUNNER_INPUT_MAX_BYTES
from product.protocols.execution_request import (
    PersistedExecutionRequest,
    canonical_execution_request_bytes,
    parse_execution_request,
    required_secret_names,
)


class ExecutionRequestStore:
    """在受控 var 子树按 job_id 原子保存请求，并用 request_hash 绑定数据库记录。"""

    def __init__(self, var_dir: Path) -> None:
        self._root = var_dir.resolve() / "jobs"

    def write(self, job_id: str, request: PersistedExecutionRequest, *, known_secrets: Sequence[str] = ()) -> tuple[str, bool]:
        """创建不可覆盖快照；相同内容幂等返回，不同内容立即冲突。"""

        encoded = canonical_execution_request_bytes(request, known_secrets=known_secrets)
        request_hash = hashlib.sha256(encoded).hexdigest()
        path = self.path_for(job_id)
        if path.exists():
            existing = self.load(job_id, expected_hash=request_hash, known_secrets=known_secrets)
            if existing != request:
                raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求与既有快照不一致")
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
                raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求写入校验失败")
            os.replace(temporary, path)
            return request_hash, True
        except JiejianError:
            raise
        except OSError:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务执行请求写入失败") from None
        finally:
            temporary.unlink(missing_ok=True)

    def load(self, job_id: str, *, expected_hash: str, known_secrets: Sequence[str] = ()) -> PersistedExecutionRequest:
        """校验文件类型、大小、hash 与协议后返回请求；任何不一致均拒绝。"""

        path = self.path_for(job_id)
        if not path.is_file():
            raise JiejianError(ErrorCode.JOB_REQUEST_MISSING, "任务执行请求不存在")
        try:
            if path.stat().st_size > RUNNER_INPUT_MAX_BYTES:
                raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求超过大小限制")
            raw = path.read_bytes()
        except JiejianError:
            raise
        except OSError:
            raise JiejianError(ErrorCode.JOB_REQUEST_MISSING, "任务执行请求不可读取") from None
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_hash):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求哈希不匹配")
        parsed = parse_execution_request(raw, known_secrets=known_secrets)
        if canonical_execution_request_bytes(parsed, known_secrets=known_secrets) != raw:
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求不是规范 JSON")
        return parsed

    def remove_if_matches(self, job_id: str, request_hash: str) -> None:
        """仅在当前文件 hash 仍匹配调用者时删除孤立快照。"""

        path = self.path_for(job_id)
        if not path.is_file():
            return
        try:
            if not hmac.compare_digest(hashlib.sha256(path.read_bytes()).hexdigest(), request_hash):
                return
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass
        except OSError:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "孤儿任务执行请求清理失败") from None

    def path_for(self, job_id: str) -> Path:
        if re.fullmatch(JOB_ID_PATTERN, job_id) is None:
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务 ID 格式无效")
        path = self._root / job_id / "request.json"
        self._ensure_inside_root(path.parent)
        return path

    def _ensure_inside_root(self, path: Path) -> None:
        if not path.resolve().is_relative_to(self._root):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求路径越界")
