# =============================================================================
# Recording 请求快照
#
# 定位
#   Recording 提交事务与后续隔离 Runner 输入之间的不可变文件边界
#
# 职责
#   规范编码请求｜原子写入和哈希重验｜拒绝 secret、重复键和非有限值
#
# 调用链
#   RecordingSubmission → RecordingRequestStore → RecordingJobHandler
# =============================================================================

from __future__ import annotations

import hashlib
import hmac
import os
import re
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from product.backend.core.identifiers import JOB_ID_PATTERN
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RECORDING_REQUEST_MAX_BYTES, RecordingRunnerRequest, canonical_recording_json_bytes, parse_recording_request


class RecordingRequestStore:
    """用 job_id 持久化不含长期秘密的 Recording 请求。"""

    def __init__(self, var_dir: Path) -> None:
        self._root = var_dir.resolve() / "jobs"

    def write(
        self,
        job_id: str,
        request: RecordingRunnerRequest,
        *,
        known_secrets: Sequence[str] = (),
    ) -> tuple[str, bool]:
        """幂等写入 canonical 请求快照，返回内容哈希与是否新建。"""

        encoded = canonical_recording_json_bytes(
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
                    "录制请求与既有快照不一致",
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
            if not hmac.compare_digest(
                hashlib.sha256(temporary.read_bytes()).hexdigest(),
                request_hash,
            ):
                raise JiejianError(
                    ErrorCode.JOB_REQUEST_CONFLICT,
                    "录制请求写入校验失败",
                )
            os.replace(temporary, path)
            return request_hash, True
        except JiejianError:
            raise
        except OSError:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "录制请求写入失败") from None
        finally:
            temporary.unlink(missing_ok=True)

    def load(
        self,
        job_id: str,
        *,
        expected_hash: str,
        known_secrets: Sequence[str] = (),
    ) -> RecordingRunnerRequest:
        """按期望哈希重验并解析请求；大小、秘密或协议异常均拒绝进入 Runner。"""

        path = self.path_for(job_id)
        try:
            if not path.is_file() or path.stat().st_size > RECORDING_REQUEST_MAX_BYTES:
                raise JiejianError(ErrorCode.JOB_REQUEST_MISSING, "录制请求不存在")
            raw = path.read_bytes()
        except JiejianError:
            raise
        except OSError:
            raise JiejianError(ErrorCode.JOB_REQUEST_MISSING, "录制请求不可读取") from None
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_hash):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "录制请求哈希不匹配")
        request = parse_recording_request(raw, known_secrets=known_secrets)
        if canonical_recording_json_bytes(
            request,
            known_secrets=known_secrets,
        ) != raw:
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "录制请求不是规范 JSON")
        return request

    def remove_if_matches(self, job_id: str, request_hash: str) -> None:
        path = self.path_for(job_id)
        try:
            if not path.is_file() or not hmac.compare_digest(
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
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "孤儿录制请求清理失败") from None

    def path_for(self, job_id: str) -> Path:
        if re.fullmatch(JOB_ID_PATTERN, job_id) is None:
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务 ID 格式无效")
        path = self._root / job_id / "recording-request.json"
        self._ensure_inside_root(path.parent)
        return path

    def _ensure_inside_root(self, path: Path) -> None:
        if not path.resolve().is_relative_to(self._root):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "录制请求路径越界")
