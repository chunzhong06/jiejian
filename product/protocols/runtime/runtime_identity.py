# 受控 Python 启动的文件清单与启动回执；运行对应不产生或替代安全结论。
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
InstanceId = Annotated[str, Field(pattern=r"^rti_[0-9a-f]{32}$")]
MAX_MANIFEST_BYTES = 262_144
MAX_ARTIFACT_BYTES = 33_554_432


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class RuntimeFile(RuntimeModel):
    relative_path: str = Field(min_length=1, max_length=512)
    sha256: Digest
    size: int = Field(ge=0, le=MAX_ARTIFACT_BYTES)

    @field_validator("relative_path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        # Windows 别名、设备名和 ADS 也可能逃离清单，不能只过滤 ../。
        parts = value.split("/")
        reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
        if any(not part or part in {".", ".."} or part != part.strip()
               or part.endswith(".") or part.split(".")[0].casefold() in reserved
               or any(ord(c) < 32 or c in '\\:<>"|?*' for c in part) for part in parts):
            raise ValueError("runtime file requires a canonical relative path")
        return value


def runtime_source_fingerprint(files: tuple[RuntimeFile, ...]) -> str:
    """与源码快照按路径及内容计算的身份保持一致；大小仅用于读取预算。"""
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(item.sha256))
    return digest.hexdigest()


class RuntimeLaunchManifest(RuntimeModel):
    schema_version: Literal["1"] = "1"
    mode: Literal["CONTROLLED_PYTHON_DIRECTORY"] = "CONTROLLED_PYTHON_DIRECTORY"
    instance_id: InstanceId
    entry_module: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    files: tuple[RuntimeFile, ...] = Field(min_length=1, max_length=512)
    source_fingerprint: Digest
    dependency_files: tuple[str, ...] = Field(default=(), max_length=32)
    interpreter_fingerprint: Digest

    @model_validator(mode="after")
    def validate_manifest(self):
        paths = tuple(item.relative_path for item in self.files)
        if paths != tuple(sorted(paths, key=lambda path: (path.casefold(), path))) or len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("runtime files must be sorted and path-unique")
        if f"{self.entry_module}.py" not in paths:
            raise ValueError("runtime entry must be included in the artifact")
        if self.dependency_files != tuple(sorted(set(self.dependency_files))) or not set(self.dependency_files).issubset(paths):
            raise ValueError("dependency files must refer to frozen artifact files")
        if sum(item.size for item in self.files) > MAX_ARTIFACT_BYTES:
            raise ValueError("runtime artifact exceeds byte budget")
        if self.source_fingerprint != runtime_source_fingerprint(self.files):
            raise ValueError("runtime source fingerprint mismatch")
        return self


def runtime_manifest_fingerprint(manifest: RuntimeLaunchManifest) -> str:
    payload = json.dumps(manifest.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RuntimeLaunchReceipt(RuntimeModel):
    schema_version: Literal["1"] = "1"
    instance_id: InstanceId
    manifest_fingerprint: Digest
    process_id: int = Field(gt=0)
    source_fingerprint: Digest
    interpreter_fingerprint: Digest


class ControlledRuntimeReference(RuntimeModel):
    instance_id: InstanceId
    manifest_fingerprint: Digest
    source_fingerprint: Digest
    process_id: int = Field(gt=0)
    process_created_at: int = Field(gt=0)
    owner_id: Annotated[str, Field(pattern=r"^exp_[0-9a-f]{32}$")]


class RuntimeCorrespondence(RuntimeModel):
    reference: ControlledRuntimeReference
    before: Literal["MATCHED", "UNCONFIRMED"]
    after: Literal["MATCHED", "UNCONFIRMED"]


def receipt_matches(manifest: RuntimeLaunchManifest, receipt: RuntimeLaunchReceipt, *, owned_process_id: int) -> bool:
    """调用方须先确认进程树所有权和存活；PID 相同本身不能构成所有权证明。"""
    return (receipt.instance_id == manifest.instance_id
            and receipt.manifest_fingerprint == runtime_manifest_fingerprint(manifest)
            and receipt.process_id == owned_process_id
            and receipt.source_fingerprint == manifest.source_fingerprint
            and receipt.interpreter_fingerprint == manifest.interpreter_fingerprint)
