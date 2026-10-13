# 创建检查的独立记录协议：区分演示编号、真实对象实例和本次宿主请求，不保存业务正文。
from typing import Literal
from pydantic import Field, model_validator
from product.protocols.runtime.runtime_identity import RuntimeModel, Digest
from product.protocols.runtime.transaction_records import RecordKey, RecordSeed, RecordRequestScope


class ScopedRecordSeed(RecordSeed):
    schema_version: Literal['2'] = '2'
    scope_id: RecordKey


class RecordRemove(RuntimeModel):
    schema_version: Literal['1'] = '1'
    collection: RecordKey
    resource_id: RecordKey
    scope_id: RecordKey
    expected_version: int = Field(ge=0)


class CreationMember(RuntimeModel):
    resource_id: RecordKey
    owner_id: RecordKey
    incarnation: RecordKey
    version: int = Field(ge=0)
    data_digest: Digest


class CreationEvent(RuntimeModel):
    sequence: int = Field(ge=1)
    scope_id: RecordKey | None = None
    kind: Literal['CREATE', 'REMOVE']
    member: CreationMember


class CreationView(RuntimeModel):
    schema_version: Literal['1'] = '1'
    generation: RecordKey
    collection: RecordKey
    watermark: int = Field(ge=0)
    members: tuple[CreationMember, ...] = Field(max_length=256)
    scope: RecordRequestScope | None = None
    events: tuple[CreationEvent, ...] = Field(default=(), max_length=32)
    foreign_mutations: bool = False

    @model_validator(mode='after')
    def exact_collection(self):
        ids = [item.resource_id for item in self.members]
        if ids != sorted(set(ids)):
            raise ValueError('creation collection is not unique and ordered')
        sequences = [item.sequence for item in self.events]
        if sequences != sorted(set(sequences)) or any(item > self.watermark for item in sequences):
            raise ValueError('creation event sequence mismatch')
        if self.scope is not None and self.scope.generation != self.generation:
            raise ValueError('creation scope generation mismatch')
        if any(self.scope is None or event.scope_id != self.scope.scope_id for event in self.events):
            raise ValueError('creation event belongs to another request')
        return self
