from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from product.protocols.runtime.runtime_identity import RuntimeModel, Digest


ActivityId = Annotated[str, Field(pattern=r'^call_[0-9a-f]{32}$')]


class ActivityEvent(RuntimeModel):
    """宿主观察到的技术调用；不携带业务值、授权决定或提交成功的断言。"""

    event_id: ActivityId
    parent_event_id: ActivityId | None
    kind: Literal['HTTP_SERVER', 'HTTP_CLIENT', 'SQLITE', 'FILESYSTEM']
    operation: Literal['REQUEST', 'EXEC', 'PREPARE', 'RUN', 'GET', 'ALL', 'ITERATE', 'READ', 'WRITE', 'APPEND']
    started_at_us: int = Field(ge=0)
    duration_us: int = Field(ge=0)
    outcome: Literal['OK', 'ERROR', 'INCOMPLETE']
    source_location: str | None = Field(default=None, max_length=240)
    http_method: Literal['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'CONNECT', 'TRACE', 'OTHER'] | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)

    @model_validator(mode='after')
    def valid_call(self):
        operations = {'HTTP_SERVER': {'REQUEST'}, 'HTTP_CLIENT': {'REQUEST'},
            'SQLITE': {'EXEC', 'PREPARE', 'RUN', 'GET', 'ALL', 'ITERATE'}, 'FILESYSTEM': {'READ', 'WRITE', 'APPEND'}}
        if self.operation not in operations[self.kind]:
            raise ValueError('activity operation mismatch')
        if self.kind not in {'HTTP_SERVER', 'HTTP_CLIENT'} and (self.http_method is not None or self.http_status is not None):
            raise ValueError('non-http call has http attributes')
        if self.source_location is not None:
            path, separator, line = self.source_location.rpartition(':')
            if not separator or not line.isdecimal() or int(line) < 1 or path.startswith('/') or any(
                part in {'', '.', '..'} for part in path.split('/')) or any(c in self.source_location for c in '\\<>\r\n\x00'):
                raise ValueError('activity location must be an approved relative source position')
        return self


class RequestActivity(RuntimeModel):
    """一次真实请求内的有界诊断记录；complete 仅表示已启用探针的收集闭合。"""

    request_nonce: Digest
    request_digest: Digest
    collector: Literal['CONTROLLED_NODE'] = 'CONTROLLED_NODE'
    adapters: tuple[Literal['node:http', 'node:https', 'node:sqlite', 'node:fs', 'node:fs/promises', 'better-sqlite3'], ...] = Field(max_length=6)
    complete: bool
    dropped_count: int = Field(default=0, ge=0)
    events: tuple[ActivityEvent, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def valid_graph(self):
        root = self.events[0]
        if root.kind != 'HTTP_SERVER' or root.parent_event_id is not None:
            raise ValueError('activity must start at the actual server request')
        seen = set()
        for event in self.events:
            if event.event_id in seen or event is not root and event.parent_event_id not in seen:
                raise ValueError('activity parents must precede their children')
            if event.started_at_us < root.started_at_us:
                raise ValueError('activity precedes the request')
            seen.add(event.event_id)
        if len(set(self.adapters)) != len(self.adapters) or self.complete and (
            self.dropped_count or any(event.outcome == 'INCOMPLETE' for event in self.events)):
            raise ValueError('unfinished activity cannot claim complete collection')
        return self
