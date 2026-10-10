# 通用记录通道中的显式执行事件；只传有限标识与父引用，不接收业务正文、凭据或安全结论。
from typing import Annotated, Literal
import re
from pydantic import Field, model_validator
from product.protocols.runtime.runtime_identity import RuntimeModel, Digest
from product.protocols.runtime.transaction_records import RecordKey

TraceToken=Annotated[str,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$')]


class RecordTraceInput(RuntimeModel):
    kind:Literal['ENTRY','IDENTITY','AUTHORIZATION','PERSISTENT_EFFECT','MESSAGE','RECOVERY']
    semantic_key:str=Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    parent_event_id:RecordKey|None=None
    subject_id:RecordKey|None=None
    authorization_decision:Literal['ALLOW','DENY']|None=None
    operation_id:RecordKey|None=None
    source_component:TraceToken
    source_location:TraceToken

    @model_validator(mode='after')
    def event_meaning(self):
        if any(re.search(r'(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)\s*[:=]',value,re.I)
               for value in (self.source_component,self.source_location,self.subject_id or '')):
            raise ValueError('secret material must not enter a trace event')
        if (self.kind=='AUTHORIZATION')!=(self.authorization_decision is not None):
            raise ValueError('authorization decision must belong to its explicit event')
        if (self.kind=='ENTRY')!=(self.parent_event_id is None):
            raise ValueError('non-entry event requires its explicit parent')
        if self.kind in {'PERSISTENT_EFFECT','RECOVERY'} and self.operation_id is None:
            raise ValueError('committed effect requires an actual operation reference')
        if self.operation_id is not None and self.kind not in {'PERSISTENT_EFFECT','RECOVERY'}:
            raise ValueError('operation reference belongs to committed events')
        return self


class RecordTraceWrite(RuntimeModel):
    schema_version:Literal['1']='1'
    scope_id:RecordKey
    collection:RecordKey
    resource_id:RecordKey
    event:RecordTraceInput


class RecordTraceEvent(RecordTraceInput):
    event_id:RecordKey
    recorded_at_us:int=Field(ge=0)


class RecordTraceReceipt(RuntimeModel):
    schema_version:Literal['1']='1'
    event:RecordTraceEvent


class RecordTraceLog(RuntimeModel):
    schema_version:Literal['1']='1'
    scope_id:RecordKey
    generation:RecordKey
    request_nonce:Digest
    request_digest:Digest
    scope_state:Literal['OPEN','COMPLETE','INCOMPLETE']='OPEN'
    collection:RecordKey
    resource_id:RecordKey
    events:tuple[RecordTraceEvent,...]=Field(default=(),max_length=128)

    @model_validator(mode='after')
    def explicit_graph(self):
        seen=set()
        for event in self.events:
            if event.event_id in seen or event.parent_event_id is not None and event.parent_event_id not in seen:
                raise ValueError('trace parent is missing or event is duplicated')
            seen.add(event.event_id)
        return self
