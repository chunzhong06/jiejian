# =============================================================================
# Runner staging 写入
#
# 定位
#   隔离 Runner 的结果与 Evidence 原子落盘边界。
#
# 职责
#   有界原子写入｜staging 工件清单生成｜统一写入失败码。
#
# 边界
#   不执行目标、不决定 Verdict、不发布 Run 或 Report。
# =============================================================================

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import StagedArtifact, canonical_runner_json_bytes


def atomic_write(path: Path, data: bytes) -> None:
    """在既有 staging 父目录内以临时文件替换目标文件。"""

    temporary = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        raise JiejianError(ErrorCode.ARTIFACT_WRITE, "Runner staging 写入失败") from None
    finally:
        temporary.unlink(missing_ok=True)


def write_evidence(staging: Path, evidence, *, known_secrets=()) -> StagedArtifact:
    """把单个 Evidence 写入 staging，并返回内容寻址工件记录。"""

    encoded = canonical_runner_json_bytes(evidence, known_secrets=known_secrets)
    path = staging / "artifacts" / "evidence" / f"{evidence.evidence_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, encoded)
    return StagedArtifact(path=path.relative_to(staging).as_posix(), byte_count=len(encoded), sha256=hashlib.sha256(encoded).hexdigest())

