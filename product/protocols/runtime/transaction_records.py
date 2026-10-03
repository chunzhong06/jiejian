# 通用事务记录组件的有界输入与回执；业务数据和变化事实同事务保存，不接受安全结论。
from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator

from product.protocols.runtime.runtime_identity import RuntimeModel, Digest, InstanceId
from product.protocols.runtime.node_runtime import ProjectId

RecordKey = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
FieldName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")]


def bounded_record_data(value):
    """只接受有限 JSON 业务值；凭据不能借业务字段进入记录库。"""
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 8 or count > 512:
            raise ValueError("record data structure exceeds budget")
        if type(item) is dict:
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 64 or key.casefold() in {
                    "password", "cookie", "token", "secret", "authorization", "api_key", "__proto__", "constructor",
                }:
                    raise ValueError("record data contains prohibited field")
                pending.append((child, depth + 1))
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif item is not None and type(item) not in {str, int, float, bool}:
            raise ValueError("record value is not JSON")
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode("utf-8")) > 8192:
        raise ValueError("record data exceeds byte budget")
    return json.loads(raw)


class RecordChange(RuntimeModel):
    path: tuple[FieldName, ...] = Field(min_length=1, max_length=8)
    value: Any

    @field_validator("path")
    @classmethod
    def safe_path(cls, value):
        bounded_record_data({key: None for key in value})
        return value

    @field_validator("value")
    @classmethod
    def bounded_value(cls, value):
        return bounded_record_data(value)


class RecordSeed(RuntimeModel):
    schema_version: Literal["1"] = "1"
    collection: RecordKey
    resource_id: RecordKey
    owner_id: RecordKey
    data: dict[str, Any]

    @field_validator("data")
    @classmethod
    def bounded_data(cls, value):
        return bounded_record_data(value)


class RecordTransaction(RuntimeModel):
    schema_version: Literal["1"] = "1"
    collection: RecordKey
    resource_id: RecordKey
    subject_id: RecordKey
    request_key: RecordKey
    scope_id: RecordKey | None = None
    expected_version: int = Field(ge=0, le=9_007_199_254_740_990)
    changes: tuple[RecordChange, ...] = Field(max_length=8)


class RecordSnapshot(RuntimeModel):
    schema_version: Literal["1"] = "1"
    generation: RecordKey
    collection: RecordKey
    resource_id: RecordKey
    owner_id: RecordKey
    version: int = Field(ge=0)
    data: dict[str, Any]
    last_operation_id: RecordKey | None = None


class RecordTransition(RuntimeModel):
    ordinal: int = Field(ge=0, le=7)
    before: dict[str, Any]
    after: dict[str, Any]


class RecordOperation(RuntimeModel):
    schema_version: Literal["1"] = "1"
    operation_id: RecordKey
    generation: RecordKey
    collection: RecordKey
    resource_id: RecordKey
    owner_id: RecordKey
    subject_id: RecordKey
    request_key: RecordKey
    scope_id: RecordKey | None = None
    before_version: int = Field(ge=0)
    after_version: int = Field(ge=1)
    state: Literal["COMMITTED"] = "COMMITTED"
    transitions: tuple[RecordTransition, ...] = Field(max_length=8)


class RecordProviderReference(RuntimeModel):
    schema_version: Literal["1"] = "1"
    project_id: ProjectId
    instance_id: InstanceId
    owner_tree_name: str = Field(pattern=r"^Local\\JiejianWorker-[0-9a-f]{64}$")
    owner_process_id: int = Field(gt=0)
    owner_process_created_at: int = Field(gt=0)
    port: int = Field(ge=1, le=65535)
    implementation_fingerprint: Digest


class RecordProofRequest(RuntimeModel):
    schema_version: Literal['1'] = '1'
    collection: RecordKey
    resource_id: RecordKey
    operation_id: RecordKey | None = None
    request_nonce: Digest | None = None


class RecordRequestScope(RuntimeModel):
    """宿主独立记录的请求完成边界；应用不能通过业务事务声明完成。"""
    schema_version: Literal['1'] = '1'
    scope_id: RecordKey
    generation: RecordKey
    request_nonce: Digest
    request_digest: Digest
    state: Literal['OPEN', 'COMPLETE', 'INCOMPLETE'] = 'OPEN'


class RecordProofView(RuntimeModel):
    schema_version: Literal['1'] = '1'
    snapshot: RecordSnapshot
    operation: RecordOperation | None = None
    scope: RecordRequestScope | None = None
    operations: tuple[RecordOperation, ...] = Field(default=(), max_length=32)
