# 历史发布包的只读校验与回执格式；没有发布、索引写入或执行入口。
from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from product.backend.core.identifiers import JOB_ID_PATTERN, PROJECT_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RUNNER_RESULT_MAX_BYTES, RunnerResult, RunnerResultType, StagedArtifact, parse_evidence, parse_runner_result
from product.backend.infra.runtime.paths import RuntimePaths

PUBLICATION_MANIFEST_NAME = "publication-manifest.json"
_LEASE_OWNER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_TERMINAL_PUBLISH_TYPES = {
    RunnerResultType.SUCCESS,
    RunnerResultType.SAFETY_STOPPED,
}






class TrustedResultReceipt(BaseModel):
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


class PublicationManifest(BaseModel):
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
    files: tuple[StagedArtifact, ...] = Field(min_length=1, max_length=4097)

    @model_validator(mode="after")
    def validate_file_set(self) -> PublicationManifest:
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
    result: RunnerResult
    manifest: PublicationManifest
    final_dir: Path




def final_run_dir(var_dir: Path, project_id: str, run_id: str) -> Path:
    root = Path(os.path.abspath(RuntimePaths(var_dir).projects))
    target = Path(os.path.abspath(root / project_id / "runs" / run_id))
    if os.path.commonpath((root, target)) != str(root):
        raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "最终运行目录越界")
    return target




def validate_published_run(
    final_dir: Path,
    *,
    known_secrets: Sequence[str] = (),
) -> ValidatedPublication:
    """重验最终 Run 目录的清单、文件身份与结果绑定，返回只读可信 publication。"""

    if _is_reparse(final_dir):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "最终运行目录是重解析点")
    final_dir = Path(os.path.abspath(final_dir))
    manifest = read_publication_manifest(final_dir / PUBLICATION_MANIFEST_NAME)
    files = _inventory_regular_files(final_dir, known_secrets)
    # 最终目录必须精确闭合：清单之外的文件同样会破坏不可变 publication。
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
        result = _parse_runner_result(
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
        or not _is_terminal_publish_result(result)
    ):
        raise JiejianError(ErrorCode.ARTIFACT_FENCE, "最终结果 fencing 关联无效")
    return ValidatedPublication(result=result, manifest=manifest, final_dir=final_dir)


def _is_terminal_publish_result(result: RunnerResult) -> bool:
    return result.result_type in _TERMINAL_PUBLISH_TYPES






def _parse_runner_result(raw: bytes, *, known_secrets: Sequence[str]) -> RunnerResult:
    """使用唯一当前结果 parser 校验 Runner 输出。"""

    if len(raw) > RUNNER_RESULT_MAX_BYTES or raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "Runner 结果大小或编码无效")
    try:
        return parse_runner_result(raw, known_secrets=known_secrets)
    except JiejianError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "Runner 结果协议校验失败") from None


def _reject_nonfinite(_: str) -> None:
    raise ValueError("non-finite number")




def read_publication_manifest(path: Path) -> PublicationManifest:
    try:
        if path.stat().st_size > RUNNER_RESULT_MAX_BYTES:
            raise ValueError("manifest too large")
        raw = path.read_bytes()
        parsed = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_nonfinite)
        if not isinstance(parsed, dict) or parsed.get("schema_version") != "1":
            raise ValueError("unsupported publication manifest schema version")
        return PublicationManifest.model_validate_json(raw, strict=True)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "发布清单无效") from None




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
) -> tuple[StagedArtifact, ...]:
    if not root.is_dir() or _is_reparse(root):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件根目录无效")
    records: list[StagedArtifact] = []
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
                    StagedArtifact(
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


def _parse_receipt(path: Path) -> TrustedResultReceipt:
    try:
        raw = path.read_bytes()
        document = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_nonfinite)
        if not isinstance(document, dict) or document.get("schema_version") != "1":
            raise ValueError("unsupported trusted receipt schema version")
        return TrustedResultReceipt.model_validate(document, strict=True)
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
