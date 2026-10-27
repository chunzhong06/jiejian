# 读写不可变录制 Flow，统一路径、摘要、规范编码与原子发布。
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.storage.preparation.recordings import RecordingRecord
from product.protocols.recording.recording_flow import Flow

def recorded_flow_path(var_dir: Path, recording: RecordingRecord) -> Path:
    root = RuntimePaths(var_dir).projects / recording.project_id / "recordings"
    path = (root / recording.recording_id / "flow.json").resolve()
    if not path.is_relative_to(root.resolve()):
        raise JiejianError(ErrorCode.RECORD_FLOW_PUBLISH, "最终 Flow 路径越界")
    return path


def read_recorded_flow(path: Path, *, expected_hash: str | None = None) -> Flow:
    try:
        raw = path.read_bytes()
        from product.protocols.recording.flow_draft import _strict_json, FLOW_DRAFT_MAX_BYTES
        parsed = _strict_json(raw, FLOW_DRAFT_MAX_BYTES, ())
        if expected_hash is not None and hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError("flow hash mismatch")
        if not isinstance(parsed, dict) or (parsed.get("schema_version") != "1" or parsed.get("document_type") != "jiejian.recorded-flow"):
            raise ValueError("unsupported flow schema version")
        flow = Flow.model_validate_json(raw, strict=True)
        if canonical_flow_bytes(flow) != raw:
            raise ValueError("flow must be canonical")
        return flow
    except (OSError, ValueError):
        raise JiejianError(
            ErrorCode.RECORD_FLOW_PUBLISH,
            "最终 Flow 不可读取",
        ) from None


def publish_recorded_flow(path: Path, encoded: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != encoded:
                raise JiejianError(
                    ErrorCode.RECORD_FLOW_PUBLISH,
                    "最终 Flow 已存在且内容冲突",
                )
            return
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid4().hex}")
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except JiejianError:
        raise
    except OSError:
        raise JiejianError(
            ErrorCode.RECORD_FLOW_PUBLISH,
            "最终 Flow 发布失败",
        ) from None
    finally:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)


def canonical_flow_bytes(flow: Flow) -> bytes:
    try:
        return json.dumps(
            flow.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise JiejianError(ErrorCode.RECORD_FLOW_PUBLISH, "最终 Flow 无法序列化") from None
