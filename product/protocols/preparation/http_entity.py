"""独立业务查询与目标响应的实体对应；仅证明声明的JSON字段披露。"""
from pydantic import Field, model_validator
from product.protocols.web.base import ProtocolModel
from product.protocols.web.request import HttpRequestTemplate, HttpBodyKind, ValueSlotSource, ValueSlotConsumer


class HttpEntityQuery(ProtocolModel):
    request: HttpRequestTemplate
    resource_path: str = Field(default='$.id', pattern=r'^\$(?:\.[A-Za-z_][A-Za-z0-9_]{0,63}){1,8}$')
    owner_path: str = Field(default='$.owner_id', pattern=r'^\$(?:\.[A-Za-z_][A-Za-z0-9_]{0,63}){1,8}$')
    data_path: str = Field(default='$', pattern=r'^\$(?:\.[A-Za-z_][A-Za-z0-9_]{0,63}){0,8}$')

    @model_validator(mode='after')
    def readonly_resource(self):
        slots = self.request.input_slots
        if self.request.method != 'GET' or self.request.body.kind is not HttpBodyKind.EMPTY or len(slots) != 1 or slots[0].source is not ValueSlotSource.CASE_RESOURCE_ID:
            raise ValueError('entity query requires a readonly request with one case resource')
        if self.request.headers or self.request.response_extractors:
            raise ValueError('query uses the prepared owner identity without extra credentials or extraction')
        slot = slots[0]
        marker = '{' + slot.slot_id + '}'
        path_matches = self.request.path.split('/').count(marker)
        query_matches = sum(item.slot_id == slot.slot_id for item in self.request.query)
        if path_matches + query_matches != 1 or (
            slot.consumer is ValueSlotConsumer.PATH and path_matches != 1
        ) or (slot.consumer is ValueSlotConsumer.QUERY and query_matches != 1
        ) or slot.consumer not in (ValueSlotConsumer.PATH, ValueSlotConsumer.QUERY):
            raise ValueError('query must address the exact case resource as a whole path or query value')
        forbidden = {'password','token','secret','cookie','authorization','api_key'}
        if any(set(value.lower().split('.')) & forbidden for value in (self.resource_path,self.owner_path,self.data_path)):
            raise ValueError('entity mapping cannot select authentication material')
        return self


class HttpEntityEvidence(ProtocolModel):
    effect_id: str = Field(pattern=r'^bef_[0-9a-f]{32}$')
    query: HttpEntityQuery
