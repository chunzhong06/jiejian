# 通用事务记录组件的有界输入与回执；业务数据和变化事实同事务保存，不接受安全结论。
from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, field_validator, model_validator

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


class LegacyRecordTransaction(RuntimeModel):
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


class LegacyRecordOperation(RuntimeModel):
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


class LegacyRecordProofView(RuntimeModel):
    schema_version: Literal['1'] = '1'
    snapshot: RecordSnapshot
    operation: LegacyRecordOperation | None = None
    scope: RecordRequestScope | None = None
    operations: tuple[LegacyRecordOperation, ...] = Field(default=(), max_length=32)


# 新宿主的一次调用形成一次原子提交；旧根继续由独立分支严格读取，不能默认补新含义。
class RecordTransaction(LegacyRecordTransaction):
    schema_version: Literal['2'] = '2'


class RecordOperation(LegacyRecordOperation):
    schema_version: Literal['2'] = '2'
    scope_ordinal: int | None = Field(default=None, ge=0, le=31)
    commit_semantics: Literal['ATOMIC_COMMIT'] = 'ATOMIC_COMMIT'

    @model_validator(mode='after')
    def exact_commit(self):
        if (self.scope_id is None) != (self.scope_ordinal is None):
            raise ValueError('scope ordinal must accompany the exact request scope')
        if self.after_version != self.before_version + 1:
            raise ValueError('commit versions must be consecutive')
        for index,transition in enumerate(self.transitions):
            bounded_record_data(transition.before);bounded_record_data(transition.after)
            if transition.ordinal != index or (index and transition.before != self.transitions[index-1].after):
                raise ValueError('transaction transitions must be continuous')
        return self


class RecordProofView(RuntimeModel):
    schema_version: Literal['2'] = '2'
    snapshot: RecordSnapshot
    operation: RecordOperation | None = None
    scope: RecordRequestScope | None = None
    operations: tuple[RecordOperation, ...] = Field(default=(), max_length=32)

    @model_validator(mode='after')
    def complete_scope_sequence(self):
        bounded_record_data(self.snapshot.data)
        if len({item.operation_id for item in self.operations})!=len(self.operations):
            raise ValueError('duplicate committed operation')
        for index,item in enumerate(self.operations):
            if self.scope is None or item.scope_id!=self.scope.scope_id or item.scope_ordinal!=index or item.generation!=self.scope.generation:
                raise ValueError('request commit sequence mismatch')
        return self


class RecordStateMigration(RuntimeModel):
    schema_version: Literal['1'] = '1'
    source_generation: RecordKey
    target_generation: RecordKey
    source_history_sha256: Digest
    source_state_sha256: Digest
    target_state_sha256: Digest
    resource_count: int = Field(ge=0)

    @model_validator(mode='after')
    def preserve_business_state(self):
        if self.source_generation == self.target_generation or self.source_state_sha256 != self.target_state_sha256:
            raise ValueError('migration must preserve state in a new generation')
        return self


def read_record_proof(raw: str | bytes):
    """按原根版本解析；历史字节不升级、不补字段，也不重新计算旧记录。"""
    return TypeAdapter(Annotated[LegacyRecordProofView | RecordProofView, Field(discriminator='schema_version')]).validate_json(raw)
