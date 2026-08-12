# 项目请求模型。

from __future__ import annotations

from pydantic import Field

from .common import ApiModel


class ProjectRegisterRequest(ApiModel):
    path: str = Field(min_length=1, max_length=2048)
    revalidate: bool = False


class ContractActivateRequest(ApiModel):
    path: str = Field(min_length=1, max_length=2048)
