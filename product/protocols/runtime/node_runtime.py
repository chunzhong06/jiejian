# 普通 Node ESM 运行清单：独立根版本，不改变既有 Python 清单或历史结果的 canonical。
from __future__ import annotations

from typing import Annotated, Literal
import hashlib
import json

from pydantic import Field, field_validator, model_validator

from product.protocols.runtime.runtime_identity import Digest, InstanceId, MAX_ARTIFACT_BYTES, RuntimeFile, RuntimeModel, runtime_source_fingerprint
ProjectId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]


class NodeRuntimeManifest(RuntimeModel):
    schema_version: Literal["1"] = "1"
    mode: Literal["CONTROLLED_NODE_ESM"] = "CONTROLLED_NODE_ESM"
    instance_id: InstanceId
    project_id: ProjectId
    entry: str = Field(min_length=1, max_length=512)
    port: int = Field(ge=1024, le=65535)
    files: tuple[RuntimeFile, ...] = Field(min_length=1, max_length=512)
    source_fingerprint: Digest
    interpreter_fingerprint: Digest
    executor_fingerprint: Digest

    @field_validator("entry")
    @classmethod
    def validate_entry(cls, value):
        RuntimeFile.safe_path(value)
        if not value.endswith(".mjs"):
            raise ValueError("controlled Node entry must be an mjs module")
        return value

    @model_validator(mode="after")
    def validate_manifest(self):
        paths = tuple(item.relative_path for item in self.files)
        if paths != tuple(sorted(paths, key=lambda path: (path.casefold(), path))) or len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("Node artifact paths must be sorted and unique")
        if self.entry not in paths or any(not path.endswith((".mjs", ".json", ".html", ".css", ".svg")) for path in paths):
            raise ValueError("Node artifact has unsupported files or missing entry")
        if sum(item.size for item in self.files) > MAX_ARTIFACT_BYTES:
            raise ValueError("Node artifact exceeds byte budget")
        if self.source_fingerprint != runtime_source_fingerprint(self.files):
            raise ValueError("Node artifact source fingerprint mismatch")
        return self


class NodeRuntimeLoadRequest(RuntimeModel):
    schema_version: Literal["1"] = "1"
    load_id: str = Field(pattern=r"^rld_[0-9a-f]{32}$")
    project_id: ProjectId
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    control_session_id: str = Field(pattern=r"^rcs_[0-9a-f]{32}$")
    preview_fingerprint: Digest
    instance_id: InstanceId
    manifest_fingerprint: Digest
    source_fingerprint: Digest
    created_at_us: int = Field(ge=0)


# 仅作为跨进程回执中的实例事实；不能从目标自报端口或字符串声明构造。
class NodeRuntimeReference(RuntimeModel):
    mode: Literal["CONTROLLED_NODE_ESM"] = "CONTROLLED_NODE_ESM"
    project_id: ProjectId
    instance_id: InstanceId
    manifest_fingerprint: Digest
    source_fingerprint: Digest
    process_id: int = Field(gt=0)
    process_created_at: int = Field(gt=0)
    port: int = Field(ge=1024, le=65535)


class NodeRuntimeLoadReceipt(RuntimeModel):
    schema_version: Literal["1"] = "1"
    load_id: str = Field(pattern=r"^rld_[0-9a-f]{32}$")
    request_fingerprint: Digest
    reference: NodeRuntimeReference
    started_at_us: int = Field(ge=0)


class NodeRuntimeCorrespondence(RuntimeModel):
    reference: NodeRuntimeReference
    before: Literal['MATCHED','UNCONFIRMED']
    after: Literal['MATCHED','UNCONFIRMED']


def node_document_fingerprint(document: RuntimeModel) -> str:
    payload = json.dumps(document.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
