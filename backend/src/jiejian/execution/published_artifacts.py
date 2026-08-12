# =============================================================================
# Execution 已发布工件安全
#
# 定位
#   Runner staging、publication manifest 与最终 Run 目录的文件完整性边界
#
# 职责
#   约束路径和 reparse point｜核对文件清单、大小与哈希｜形成可信 receipt
#
# 调用链
#   WorkerSupervisor / Publication / Results → validators → staging / final run directory
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..domain.identifiers import (
    JOB_ID_PATTERN,
    PROJECT_ID_PATTERN,
    RUN_ID_PATTERN,
    SHA256_PATTERN,
)
from ..errors import ErrorCode, JiejianError
from ..protocols import (
    RUNNER_RESULT_MAX_BYTES,
    RunnerResultType,
    RunnerResultV1,
    StagedArtifactV1,
    parse_runner_result,
)
from ..storage import EvidenceIndexRecord, JobRecord

PUBLICATION_MANIFEST_NAME = "publication-manifest.json"
_LEASE_OWNER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_TERMINAL_PUBLISH_TYPES = {
    RunnerResultType.SUCCESS,
    RunnerResultType.SAFETY_STOPPED,
}


@dataclass(frozen=True, slots=True)
class AttemptPaths:
    attempt_dir: Path
    input_path: Path
    cancel_path: Path
    staging_dir: Path
    result_path: Path
    receipt_path: Path


@dataclass(frozen=True, slots=True)
class StagedAttempt:
    result: RunnerResultV1
    paths: AttemptPaths


class TrustedResultReceiptV1(BaseModel):
    """Worker 完成协议、工件和当前 fence 校验后的原子标记。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    attempt: int = Field(ge=1)
    lease_owner: str = Field(pattern=_LEASE_OWNER_PATTERN)
    fencing_token: int = Field(ge=1)
    result_sha256: str = Field(pattern=SHA256_PATTERN)


class PublicationManifestV1(BaseModel):
    """随最终目录发布且不允许原地修改的 Worker manifest。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    attempt: int = Field(ge=1)
    lease_owner: str = Field(pattern=_LEASE_OWNER_PATTERN)
    fencing_token: int = Field(ge=1)
    lease_expires_at_us: int = Field(ge=0)
    published_at_us: int = Field(ge=0)
    result_sha256: str = Field(pattern=SHA256_PATTERN)
    files: tuple[StagedArtifactV1, ...] = Field(min_length=1, max_length=4097)

    @model_validator(mode="after")
    def validate_file_set(self) -> PublicationManifestV1:
        folded = {item.path.casefold() for item in self.files}
        if len(folded) != len(self.files):
            raise ValueError("publication file paths must be unique")
        if "result.json" not in folded:
            raise ValueError("publication manifest must include result.json")
        if self.published_at_us >= self.lease_expires_at_us:
            raise ValueError("publication must occur before lease expiry")
        return self


@dataclass(frozen=True, slots=True)
class ValidatedPublication:
    result: RunnerResultV1
    manifest: PublicationManifestV1
    final_dir: Path


def attempt_paths_for(var_dir: Path, job: JobRecord) -> AttemptPaths:
    """以受约束 Job ID、attempt 和 token 唯一定位当前尝试。"""

    jobs_root = (var_dir.resolve() / "jobs").resolve()
    attempt_dir = (
        jobs_root / job.job_id / "attempts" / f"{job.attempt}-{job.fencing_token}"
    ).resolve()
    if not attempt_dir.is_relative_to(jobs_root):
        raise JiejianError(ErrorCode.RUNNER_START_FAILED, "Runner 尝试路径越界")
    staging = attempt_dir / "staging"
    return AttemptPaths(
        attempt_dir=attempt_dir,
        input_path=attempt_dir / "input.json",
        cancel_path=attempt_dir / "cancel.requested",
        staging_dir=staging,
        result_path=staging / "result.json",
        receipt_path=attempt_dir / "trusted-result.json",
    )


def final_run_dir(var_dir: Path, project_id: str, run_id: str) -> Path:
    root = Path(os.path.abspath(var_dir.resolve() / "projects"))
    target = Path(os.path.abspath(root / project_id / "runs" / run_id))
    if os.path.commonpath((root, target)) != str(root):
        raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "最终运行目录越界")
    return target


def validate_runner_staging(
    paths: AttemptPaths,
    job: JobRecord,
    *,
    known_secrets: Sequence[str],
    require_receipt: bool,
) -> tuple[RunnerResultV1, tuple[StagedArtifactV1, ...]]:
    """在结果接收和发布两个安全边界复用完整目录校验。"""

    files = _inventory_regular_files(paths.staging_dir, known_secrets)
    file_map = {item.path.casefold(): item for item in files}
    result_record = file_map.get("result.json")
    if result_record is None:
        raise JiejianError(ErrorCode.RUNNER_RESULT_MISSING, "Runner 结果文件不存在")
    try:
        raw = paths.result_path.read_bytes()
        result = parse_runner_result(raw, known_secrets=known_secrets)
    except (OSError, JiejianError):
        raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "Runner 结果协议校验失败") from None
    if (
        result.run_id != job.run_id
        or result.job_id != job.job_id
        or result.attempt != job.attempt
        or result.lease_owner != job.lease_owner
        or result.fencing_token != job.fencing_token
    ):
        raise JiejianError(ErrorCode.ARTIFACT_FENCE, "Runner 结果关联信息不匹配")
    expected = {"result.json": result_record}
    expected.update({item.path.casefold(): item for item in result.artifacts})
    comparable_expected = {
        key: (item.path, item.byte_count, item.sha256) for key, item in expected.items()
    }
    comparable_actual = {
        key: (item.path, item.byte_count, item.sha256)
        for key, item in file_map.items()
        if key != PUBLICATION_MANIFEST_NAME.casefold()
    }
    if comparable_actual != comparable_expected:
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "Runner 暂存工件清单不一致")
    if require_receipt:
        receipt = _parse_receipt(paths.receipt_path)
        if (
            receipt.run_id != result.run_id
            or receipt.job_id != result.job_id
            or receipt.attempt != result.attempt
            or receipt.lease_owner != result.lease_owner
            or receipt.fencing_token != result.fencing_token
            or receipt.result_sha256 != result_record.sha256
        ):
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "可信结果回执关联信息不匹配")
    return result, tuple(expected[key] for key in sorted(expected))


def validate_published_run(
    final_dir: Path,
    *,
    known_secrets: Sequence[str] = (),
) -> ValidatedPublication:
    if _is_reparse(final_dir):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "最终运行目录是重解析点")
    final_dir = Path(os.path.abspath(final_dir))
    manifest = read_publication_manifest(final_dir / PUBLICATION_MANIFEST_NAME)
    files = _inventory_regular_files(final_dir, known_secrets)
    actual = {item.path.casefold(): item for item in files}
    manifest_record = actual.pop(PUBLICATION_MANIFEST_NAME.casefold(), None)
    if manifest_record is None:
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "最终目录缺少发布清单")
    expected = {item.path.casefold(): item for item in manifest.files}
    if actual != expected:
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "最终目录文件清单不一致")
    result_record = expected.get("result.json")
    if result_record is None or result_record.sha256 != manifest.result_sha256:
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "最终结果哈希不匹配")
    try:
        result = parse_runner_result(
            (final_dir / result_record.path).read_bytes(),
            known_secrets=known_secrets,
        )
    except (OSError, JiejianError):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "最终结果协议无效") from None
    if (
        result.job_id != manifest.job_id
        or result.run_id != manifest.run_id
        or result.attempt != manifest.attempt
        or result.lease_owner != manifest.lease_owner
        or result.fencing_token != manifest.fencing_token
        or result.result_type not in _TERMINAL_PUBLISH_TYPES
    ):
        raise JiejianError(ErrorCode.ARTIFACT_FENCE, "最终结果 fencing 关联无效")
    return ValidatedPublication(result=result, manifest=manifest, final_dir=final_dir)


def evidence_records_for_publication(
    final_dir: Path,
    result: RunnerResultV1,
    *,
    created_at_us: int,
) -> tuple[EvidenceIndexRecord, ...]:
    records: list[EvidenceIndexRecord] = []
    for artifact in result.artifacts:
        if not artifact.path.startswith("artifacts/evidence/") or not artifact.path.endswith(
            ".json"
        ):
            continue
        try:
            document = json.loads(
                (final_dir / artifact.path).read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
            )
            if not isinstance(document, dict):
                raise TypeError("evidence must be an object")
            evidence_id = document["evidence_id"]
            case_id = document["case_id"]
            evidence_hash = document["evidence_hash"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "证据索引内容无效") from None
        if Path(artifact.path).name != f"{evidence_id}.json":
            raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "证据文件名与内容不匹配")
        semantic_payload = {
            key: value
            for key, value in document.items()
            if key not in {"evidence_id", "evidence_hash"}
        }
        semantic_hash = hashlib.sha256(
            json.dumps(
                semantic_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if evidence_hash != semantic_hash or evidence_id != f"ev_{semantic_hash[:20]}":
            raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "证据内容寻址校验失败")
        records.append(
            EvidenceIndexRecord(
                evidence_id=evidence_id,
                run_id=result.run_id,
                case_id=case_id,
                artifact_path=artifact.path,
                sha256=semantic_hash,
                byte_count=artifact.byte_count,
                created_at_us=created_at_us,
            )
        )
    return tuple(sorted(records, key=lambda item: item.evidence_id))


def read_publication_manifest(path: Path) -> PublicationManifestV1:
    try:
        if path.stat().st_size > RUNNER_RESULT_MAX_BYTES:
            raise ValueError("manifest too large")
        raw = path.read_bytes()
        json.loads(raw, object_pairs_hook=_unique_object)
        return PublicationManifestV1.model_validate_json(raw, strict=True)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "发布清单无效") from None


def write_publication_manifest(path: Path, manifest: PublicationManifestV1) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    encoded = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "发布清单写入失败") from None
    finally:
        temporary.unlink(missing_ok=True)


def reject_reparse_parents(root: Path, target_parent: Path) -> None:
    root = Path(os.path.abspath(root))
    target_parent = Path(os.path.abspath(target_parent))
    if os.path.commonpath((root, target_parent)) != str(root):
        raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "发布父目录越界")
    current = root
    if _is_reparse(current):
        raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "发布根目录是重解析点")
    for part in target_parent.relative_to(root).parts:
        current /= part
        if current.exists() and _is_reparse(current):
            raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "发布父目录是重解析点")


def _inventory_regular_files(
    root: Path,
    known_secrets: Sequence[str],
) -> tuple[StagedArtifactV1, ...]:
    if not root.is_dir() or _is_reparse(root):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件根目录无效")
    records: list[StagedArtifactV1] = []
    secrets = tuple(secret.encode("utf-8") for secret in known_secrets if secret)
    try:
        for current, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            for name in tuple(directories):
                if _is_reparse(current_path / name):
                    raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件目录包含重解析点")
            for name in filenames:
                path = current_path / name
                metadata = os.lstat(path)
                if not stat.S_ISREG(metadata.st_mode) or _is_reparse(path):
                    raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件必须是普通文件")
                relative = path.relative_to(root).as_posix()
                raw = path.read_bytes()
                if any(secret in raw for secret in secrets):
                    raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件包含已知秘密")
                records.append(
                    StagedArtifactV1(
                        schema_version="1",
                        path=relative,
                        byte_count=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest(),
                    )
                )
    except JiejianError:
        raise
    except OSError:
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件目录不可读取") from None
    folded = {item.path.casefold() for item in records}
    if len(folded) != len(records):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件路径存在大小写别名")
    return tuple(sorted(records, key=lambda item: item.path))


def _parse_receipt(path: Path) -> TrustedResultReceiptV1:
    try:
        raw = path.read_bytes()
        document = json.loads(raw, object_pairs_hook=_unique_object)
        return TrustedResultReceiptV1.model_validate(document, strict=True)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "可信结果回执无效") from None


def _is_reparse(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except OSError:
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件路径不可检查") from None
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result
