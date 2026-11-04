"""环境的公开配置与运行快照；地址和声明版本均不构成执行授权。"""
from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

import hashlib
from product.protocols.codec import encode_json, decode_json
from product.protocols.web.base import ProtocolModel
from product.protocols.web.target import WebTargetScope


class FrozenEnvironment(ProtocolModel):
    environment_id: str = Field(pattern=r'^env_[0-9a-f]{32}$')
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    target: WebTargetScope
    deployment_label: str | None = Field(default=None, min_length=1, max_length=128)
    deployment_verification: Literal['UNVERIFIED'] = 'UNVERIFIED'

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(encode_json(self.model_dump(mode='json'))).hexdigest()

    @model_validator(mode='after')
    def public_address(self):
        url = urlsplit(self.target.base_url)
        if url.username is not None or url.password is not None or url.query or url.fragment:
            raise ValueError('environment address must not contain credentials or parameters')
        return self


class EnvironmentDocument(ProtocolModel):
    document_type: Literal['jiejian.application-environment'] = 'jiejian.application-environment'
    schema_version: Literal['1'] = '1'
    project_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    configuration: FrozenEnvironment
    created_at_us: int = Field(ge=0)


def parse_environment_document(raw):
    payload=decode_json(raw,limit=32768)
    if payload.get('document_type')!='jiejian.application-environment' or payload.get('schema_version')!='1':
        raise ValueError('unsupported application environment document')
    return EnvironmentDocument.model_validate_json(raw)
