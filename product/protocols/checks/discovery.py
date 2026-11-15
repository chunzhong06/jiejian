"""检查时的业务线索核对快照；关联要求与实际执行分别表达，不参与权限判断。"""
from typing import Literal
from pydantic import Field, model_validator
from product.protocols.web.base import ProtocolModel


class DiscoveryItem(ProtocolModel):
    key: str = Field(min_length=1, max_length=160)
    kind: Literal['ROLE', 'ACTION', 'REQUEST']
    label: str = Field(min_length=1, max_length=256)
    status: Literal['PENDING', 'RELATED', 'EXCLUDED', 'RECHECK']
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_id: str | None = None
    action_id: str | None = None
    source_id: str | None = None
    request_id: str | None = None
    in_execution: bool | None = Field(default=None, exclude_if=lambda value: value is None)


class DiscoveryCoverage(ProtocolModel):
    """总数和指纹覆盖完整清单，摘要最多128条；详情优先携带指定请求，省略数量明确显示。"""
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    pending_count: int = Field(ge=0)
    related_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    recheck_count: int = Field(ge=0)
    unexecuted_request_count: int | None = Field(default=None, ge=0, exclude_if=lambda value: value is None)
    items: tuple[DiscoveryItem, ...] = Field(max_length=128)
    omitted_count: int = Field(ge=0)

    @model_validator(mode='after')
    def counts_match(self):
        counts = {'PENDING': self.pending_count, 'RELATED': self.related_count,
            'EXCLUDED': self.excluded_count, 'RECHECK': self.recheck_count}
        if sum(counts.values()) != len(self.items) + self.omitted_count:
            raise ValueError('discovery inventory count mismatch')
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError('duplicate discovery item')
        if any(sum(item.status == status for item in self.items) > count for status, count in counts.items()):
            raise ValueError('discovery status count mismatch')
        return self
