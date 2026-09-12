# 当前 v3 请求与运行配置的不可变存储；竞争写入只允许相同字节，绝不覆盖已有资产。
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from pathlib import Path
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.paths import RuntimePaths
from product.protocols.check_runtime import (
    CHECK_DOCUMENT_MAX_BYTES, CheckRuntimeBundle, canonical_check_runtime_bytes, parse_check_runtime,
)
from product.protocols.execution_v3 import (
    PersistedExecutionRequestV3, canonical_execution_request_v3_bytes, parse_execution_request_v3,
)


class CheckRequestStore:
    def __init__(self, var_dir: Path):
        self._root = RuntimePaths(var_dir).jobs.resolve()

    def path_for(self, job_id: str, *, config_hash: str | None = None) -> Path:
        if re.fullmatch(r"job_[0-9a-f]{32}", job_id) is None or (
            config_hash is not None and re.fullmatch(r"[0-9a-f]{64}", config_hash) is None
        ):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务 ID 格式无效")
        path = self._root / job_id / ("request.json" if config_hash is None else f"config-{config_hash}.json")
        if path.resolve() != path or not path.resolve().is_relative_to(self._root):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求路径越界")
        return path

    def _read(self, path: Path, expected_hash: str) -> bytes:
        try:
            if not path.is_file() or path.is_symlink() or path.stat().st_size > CHECK_DOCUMENT_MAX_BYTES:
                raise ValueError("invalid immutable asset")
            with path.open("rb") as stream:
                raw = stream.read(CHECK_DOCUMENT_MAX_BYTES + 1)
            if len(raw) > CHECK_DOCUMENT_MAX_BYTES or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_hash):
                raise ValueError("asset hash mismatch")
            return raw
        except (OSError, ValueError):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求哈希不匹配") from None

    def _write(self, path: Path, raw: bytes) -> tuple[str, bool]:
        digest = hashlib.sha256(raw).hexdigest()
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.resolve() != path:
                raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求路径越界")
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # link 的目标存在时原子失败；不能用 replace 把并发提交的不同快照覆盖掉。
                os.link(temporary, path)
                created = True
            except FileExistsError:
                created = False
            if self._read(path, digest) != raw:
                raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求与既有快照不一致")
            return digest, created
        except OSError:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务执行请求写入失败") from None
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning("CHECK_TEMPORARY_CLEANUP_FAILED")

    def write(self, job_id: str, request: PersistedExecutionRequestV3) -> tuple[str, bool]:
        return self._write(self.path_for(job_id), canonical_execution_request_v3_bytes(request))

    def load(self, job_id: str, *, expected_hash: str) -> PersistedExecutionRequestV3:
        try:
            return parse_execution_request_v3(self._read(self.path_for(job_id), expected_hash))
        except ValueError:
            raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "执行快照格式无效") from None

    def write_bundle(self, job_id: str, bundle: CheckRuntimeBundle) -> tuple[str, bool]:
        raw = canonical_check_runtime_bytes(bundle)
        digest = hashlib.sha256(raw).hexdigest()
        return self._write(self.path_for(job_id, config_hash=digest), raw)

    def load_bundle(self, job_id: str, *, expected_hash: str) -> CheckRuntimeBundle:
        try:
            return parse_check_runtime(self._read(self.path_for(job_id, config_hash=expected_hash), expected_hash))
        except ValueError:
            raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "执行快照格式无效") from None

    def remove_if_matches(self, job_id: str, request_hash: str, *, config_hash: str | None = None) -> None:
        """只清理由调用者证明没有持久 Job 引用、且仍为原 hash 的单个资产。"""
        path = self.path_for(job_id, config_hash=config_hash)
        if not path.exists():
            return
        try:
            self._read(path, config_hash or request_hash)
        except JiejianError:
            return
        path.unlink()
