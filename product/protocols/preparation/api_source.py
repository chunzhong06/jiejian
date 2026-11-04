"""净化后的接口来源；不持久化原始流量、脚本、认证值或响应正文。"""
from typing import Literal
import hashlib
from pydantic import Field, model_validator
from product.protocols.codec import decode_json, encode_json
from product.protocols.web.base import ProtocolModel


class SourceParameter(ProtocolModel):
    name: str = Field(min_length=1, max_length=128)
    location: Literal['PATH', 'QUERY', 'HEADER', 'BODY']
    required: bool = False
    sensitive: bool = False


class SourceRequest(ProtocolModel):
    item_id: str = Field(pattern=r'^req_[0-9a-f]{32}$')
    method: Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
    path: str = Field(min_length=1, max_length=1024)
    label: str = Field(min_length=1, max_length=256)
    pointer: str = Field(min_length=1, max_length=1024)
    parameters: tuple[SourceParameter, ...] = Field(default=(), max_length=128)


class ApiSourceReference(ProtocolModel):
    source_id: str = Field(pattern=r'^src_[0-9a-f]{32}$')
    revision: int = Field(ge=1)
    item_id: str = Field(pattern=r'^req_[0-9a-f]{32}$')
    request_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


class ApiSourceDocument(ProtocolModel):
    document_type: Literal['jiejian.api-source'] = 'jiejian.api-source'
    schema_version: Literal['1'] = '1'
    source_id: str = Field(pattern=r'^src_[0-9a-f]{32}$')
    project_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    revision: int = Field(ge=1)
    kind: Literal['OPENAPI', 'HAR', 'POSTMAN']
    name: str = Field(min_length=1, max_length=128)
    requests: tuple[SourceRequest, ...] = Field(max_length=512)
    warnings: tuple[str, ...] = Field(default=(), max_length=64)
    created_at_us: int = Field(ge=0)


class ApiImportDocument(ProtocolModel):
    document_type: Literal['jiejian.api-import'] = 'jiejian.api-import'
    schema_version: Literal['1'] = '1'
    candidate_id: str = Field(pattern=r'^imp_[0-9a-f]{32}$')
    project_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    kind: Literal['OPENAPI', 'HAR', 'POSTMAN']
    requests: tuple[SourceRequest, ...] = Field(max_length=512)
    warnings: tuple[str, ...] = Field(max_length=64)
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def content_identity(self):
        fingerprint=hashlib.sha256(encode_json(dict(kind=self.kind,
            requests=[item.model_dump(mode='json') for item in self.requests],warnings=self.warnings))).hexdigest()
        identity='imp_'+hashlib.sha256((self.project_id+fingerprint).encode()).hexdigest()[:32]
        if (self.fingerprint,self.candidate_id)!=(fingerprint,identity):
            raise ValueError('import candidate content identity mismatch')
        return self


def parse_source_document(raw, model):
    payload=decode_json(raw,limit=4_194_304)
    expected='jiejian.api-source' if model is ApiSourceDocument else 'jiejian.api-import'
    if payload.get('document_type')!=expected or payload.get('schema_version')!='1':
        raise ValueError('unsupported API source document')
    return model.model_validate_json(raw)
