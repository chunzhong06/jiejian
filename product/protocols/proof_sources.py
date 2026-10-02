# 有界来源与预检查的独立协议；只描述可读事实与关联，不接受客户端声明可靠或安全通过。
from __future__ import annotations
import hashlib
import json
import re
from typing import Annotated,Literal
from urllib.parse import unquote,urlsplit
from pydantic import Field,field_validator,model_validator
from product.protocols.runtime_identity import RuntimeModel,Digest,RuntimeFile
from product.protocols.node_runtime import NodeRuntimeReference,ProjectId
from product.protocols.check_runtime import CheckIdentity
from product.protocols.web.target import WebTargetScope

SourceId=Annotated[str,Field(pattern=r'^psr_[0-9a-f]{32}$')]
PreflightId=Annotated[str,Field(pattern=r'^ppf_[0-9a-f]{32}$')]
ScopeId=Annotated[str,Field(pattern=r'^prs_[0-9a-f]{32}$')]
OperationId=Annotated[str,Field(pattern=r'^[0-9a-f]{32}$')]
IdentityId=Annotated[str,Field(pattern=r'^tid_[0-9a-f]{32}$')]
ObjectPath=Annotated[tuple[Annotated[str,Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')],...],Field(min_length=1,max_length=8)]
MappingKey=Literal['resource_id','owner_id','state','version','effect_count','history_generation',
    'operation_id','operation_resource_id','operation_subject_id','operation_before_version','operation_after_version',
    'operation_state','unfinished_effects','title','summary','body']
ContractId=Literal['SYNC_RESOURCE_HISTORY_V1','OWNER_RESOURCE_VIEW_V1','TRANSACTION_HISTORY_V1','RESOURCE_FIELDS_V1']
SAFE_SUBJECT=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'


def safe_source_path(value):
    parsed=urlsplit(value)
    if (not value.startswith('/') or value.startswith('//') or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
        or '\\' in value or value.count('{resource_id}')!=1
        or any(part in {'.','..'} for part in unquote(value).split('/'))
        or not re.fullmatch(r'/[A-Za-z0-9_./{}-]{1,510}',value)
        or '{' in value.replace('{resource_id}','') or '}' in value.replace('{resource_id}','')):
        raise ValueError('source requires one fixed encoded resource path')
    return value


class SourceIdentityClaim(RuntimeModel):
    identity_id:IdentityId
    application_subject_id:str=Field(pattern=SAFE_SUBJECT)


class ProofSourceConfig(RuntimeModel):
    action_id:str=Field(pattern=r'^bac_[0-9a-f]{32}$')
    action_revision:int=Field(ge=1)
    effect_id:str=Field(pattern=r'^bef_[0-9a-f]{32}$')
    source_kind:Literal['JSON_HTTP_RESOURCE']='JSON_HTTP_RESOURCE'
    observation_identity_id:IdentityId
    resource_binding_id:str=Field(pattern=r'^res_[0-9a-f]{32}$')
    read_scope_id:ScopeId|None=None
    relative_path_template:str=Field(min_length=1,max_length=512)
    mappings:dict[MappingKey,ObjectPath]=Field(min_length=2,max_length=16)
    target_operation_path:ObjectPath=('operation_id',)
    source_contract_id:ContractId
    identity_claims:tuple[SourceIdentityClaim,...]=Field(min_length=1,max_length=16)
    source_files:tuple[str,...]=Field(min_length=1,max_length=16)
    max_response_bytes:int=Field(default=262144,ge=1024,le=262144)
    timeout_us:int=Field(default=5_000_000,ge=1000,le=5_000_000)

    @field_validator('relative_path_template')
    @classmethod
    def path_template(cls,value):return safe_source_path(value)

    @field_validator('source_files')
    @classmethod
    def files(cls,values):
        for value in values:RuntimeFile.safe_path(value)
        if len(set(values))!=len(values):raise ValueError('duplicate source reference')
        return tuple(sorted(values))

    @model_validator(mode='after')
    def bounded_mapping(self):
        forbidden={'password','token','cookie','authorization','secret','api_key','constructor','__proto__'}
        if any(any(part.lower() in forbidden for part in path) for path in (*self.mappings.values(),self.target_operation_path)):
            raise ValueError('secret or executable field mapping prohibited')
        if len({item.identity_id for item in self.identity_claims})!=len(self.identity_claims):
            raise ValueError('duplicate identity claim')
        if self.observation_identity_id not in {item.identity_id for item in self.identity_claims}:
            raise ValueError('observation identity claim missing')
        if not {'resource_id','owner_id'}<=set(self.mappings):raise ValueError('resource mappings required')
        return self


def safe_identity_path(value):
    if not re.fullmatch(r'/[A-Za-z0-9_./-]{1,510}', value) or value.startswith('//') or any(part in {'.','..'} for part in value.split('/')):
        raise ValueError('identity requires a fixed relative GET path')
    return value


class ManagedIdentityClaim(SourceIdentityClaim):
    request_path:str=Field(min_length=2,max_length=512)
    subject_path:ObjectPath
    role_path:ObjectPath
    application_role:str=Field(pattern=SAFE_SUBJECT)

    @field_validator('request_path')
    @classmethod
    def request(cls,value):return safe_identity_path(value)

    @field_validator('subject_path','role_path')
    @classmethod
    def nonsensitive(cls,value):
        if any(part.casefold() in {'password','token','cookie','authorization','secret','api_key','constructor','__proto__'} for part in value):
            raise ValueError('secret identity field prohibited')
        return value


class ManagedProofSourceConfig(ProofSourceConfig):
    source_kind:Literal['MANAGED_TRANSACTION_RECORDS']='MANAGED_TRANSACTION_RECORDS'
    source_contract_id:Literal['TRANSACTION_HISTORY_V1','RESOURCE_FIELDS_V1']
    collection:str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    identity_claims:tuple[ManagedIdentityClaim,...]=Field(min_length=1,max_length=16)
    source_files:tuple[str,...]=Field(default=(),max_length=16)
    target_resource_path:ObjectPath=('resource_id',)
    target_owner_path:ObjectPath=('owner_id',)
    target_data_path:tuple[Annotated[str,Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')],...]=Field(default=('data',),max_length=8)
    protected_projection:tuple[Annotated[str,Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,7}$',max_length=256)],...]=Field(default=(),max_length=64)

    @model_validator(mode='after')
    def provider_mapping(self):
        if self.relative_path_template!=f'/collections/{self.collection}/{{resource_id}}':
            raise ValueError('source path must identify its controlled collection')
        if self.mappings.get('resource_id')!=('resource_id',) or self.mappings.get('owner_id')!=('owner_id',):
            raise ValueError('controlled source identity fields cannot be remapped')
        if set(self.mappings)-{'resource_id','owner_id','state'}:
            raise ValueError('controlled source only maps resource, owner and state')
        if self.source_contract_id=='TRANSACTION_HISTORY_V1' and (len(self.mappings.get('state',()))<2 or self.mappings['state'][0]!='data'):
            raise ValueError('state must reference a protected resource data field')
        for path in (self.target_resource_path,self.target_owner_path,self.target_data_path):
            ManagedIdentityClaim.nonsensitive(path)
        if len(set(self.protected_projection))!=len(self.protected_projection):
            raise ValueError('duplicate protected projection')
        if (self.source_contract_id=='RESOURCE_FIELDS_V1') != bool(self.protected_projection):
            raise ValueError('protected projection must match disclosure source')
        return self


AnyProofSourceConfig=Annotated[ProofSourceConfig|ManagedProofSourceConfig,Field(discriminator='source_kind')]


def source_identity_paths(config, identities=()):
    if isinstance(config,ManagedProofSourceConfig):
        return tuple(sorted({item.request_path for item in config.identity_claims}))
    # 历史输入从自身冻结身份恢复路径；不在产品中继续保留某个应用的身份接口约定。
    return tuple(sorted({item.verification.request.path for item in identities if item.verification is not None}))


class ProofSourceRevision(RuntimeModel):
    schema_version:Literal['1','2']='2'
    project_id:ProjectId
    source_id:SourceId
    revision:int=Field(ge=1)
    config:AnyProofSourceConfig
    basis_id:str=Field(pattern=r'^pb_[0-9a-f]{64}$')
    fingerprint:Digest
    submitted_via:Literal['LOCAL_GUI','MCP']
    client_name:str=Field(max_length=80)
    created_at_us:int=Field(ge=0)

    @model_validator(mode='after')
    def content_identity(self):
        if self.fingerprint!=proof_fingerprint(self.config):raise ValueError('source config fingerprint mismatch')
        return self


class SourceReadScope(RuntimeModel):
    schema_version:Literal['1','2']='2'
    scope_id:ScopeId
    project_id:ProjectId
    origin:str
    path_templates:tuple[str,...]=Field(min_length=1,max_length=16)
    identity_ids:tuple[IdentityId,...]=Field(min_length=1,max_length=16)
    resource_binding_ids:tuple[Annotated[str,Field(pattern=r'^res_[0-9a-f]{32}$')],...]=Field(min_length=1,max_length=16)
    max_response_bytes:int=Field(ge=1024,le=262144)
    timeout_us:int=Field(ge=1000,le=5_000_000)
    created_at_us:int=Field(ge=0)

    @field_validator('origin')
    @classmethod
    def loopback(cls,value):
        parsed=urlsplit(value)
        if parsed.hostname!='127.0.0.1' or parsed.scheme!='http' or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or not parsed.port:
            raise ValueError('exact IPv4 loopback origin required')
        return value

    @field_validator('path_templates')
    @classmethod
    def paths(cls,values,info):
        for value in values:
            if '{resource_id}' in value:safe_source_path(value)
            else:safe_identity_path(value)
        if len(set(values))!=len(values):raise ValueError('duplicate paths')
        return values


class ProofContractAttestation(RuntimeModel):
    contract_id:ContractId
    implementation_profile:str=Field(pattern=r'^[A-Z][A-Z0-9_]{0,63}$')
    fingerprint:Digest
    approved_effect_kind:Literal['STATE_MUTATION','DATA_DISCLOSURE']


class ProofPreflightInput(RuntimeModel):
    schema_version:Literal['1','2']='2'
    preflight_id:PreflightId
    project_id:ProjectId
    source_id:SourceId
    source_revision:int=Field(ge=1)
    source_fingerprint:Digest
    config:AnyProofSourceConfig
    scope:SourceReadScope
    basis_id:str=Field(pattern=r'^pb_[0-9a-f]{64}$')
    control_session_id:str=Field(pattern=r'^pcs_[0-9a-f]{32}$')
    authority_id:str=Field(min_length=1,max_length=128)
    target:WebTargetScope
    identities:tuple[CheckIdentity,...]=Field(min_length=1,max_length=16)
    identity_roles:dict[IdentityId,Annotated[str,Field(pattern=SAFE_SUBJECT)]]
    resource_id:str=Field(pattern=r'^[\w.-]+$',min_length=1,max_length=256)
    owner_subject_id:str=Field(pattern=SAFE_SUBJECT)
    runtime_reference:NodeRuntimeReference
    contract:ProofContractAttestation|None=None
    created_at_us:int=Field(ge=0)

    @model_validator(mode='after')
    def association(self):
        if (self.project_id!=self.scope.project_id or self.project_id!=self.runtime_reference.project_id
            or self.target.base_url!=self.scope.origin or self.target.base_url!=f'http://127.0.0.1:{self.runtime_reference.port}'
            or self.source_fingerprint!=proof_fingerprint(self.config) or self.config.read_scope_id not in (None,self.scope.scope_id)
            or self.config.relative_path_template not in self.scope.path_templates
            or not set(source_identity_paths(self.config,self.identities))<=set(self.scope.path_templates)
            or self.config.resource_binding_id not in self.scope.resource_binding_ids
            or set(self.identity_roles)!={item.identity_id for item in self.identities}
            or not set(self.identity_roles)<=set(self.scope.identity_ids)
            or self.config.timeout_us>self.scope.timeout_us or self.config.max_response_bytes>self.scope.max_response_bytes
            or self.target.timeout_seconds * 1_000_000>self.config.timeout_us
            or self.target.max_response_bytes>self.config.max_response_bytes
            or self.target.allowed_origins!=(self.scope.origin,)
            or self.target.allowed_hosts!=('127.0.0.1',)
            or self.target.allowed_ports!=(self.runtime_reference.port,)
            or self.target.max_requests>len(self.identities)+1
            or {item.identity_id for item in self.config.identity_claims}!=set(self.identity_roles)):
            raise ValueError('preflight scope or source mismatch')
        return self


class ProofCheckItem(RuntimeModel):
    code:str=Field(pattern=r'^[A-Z][A-Z0-9_]{0,63}$')
    status:Literal['CONFIRMED','MISSING','UNAVAILABLE','UNSUPPORTED']
    mapping_key:MappingKey|None=None


class ProofPreflightReport(RuntimeModel):
    schema_version:Literal['1']='1'
    preflight_id:PreflightId
    job_id:str=Field(pattern=r'^job_[0-9a-f]{32}$')
    request_fingerprint:Digest
    source_fingerprint:Digest
    attempt:int=Field(ge=1)
    fencing_token:int=Field(ge=1)
    lease_owner:str=Field(min_length=1,max_length=128)
    assessment:Literal['USABLE','NEEDS_CHANGES','UNSUPPORTED']
    checks:tuple[ProofCheckItem,...]=Field(min_length=1,max_length=48)
    started_at_us:int=Field(ge=0)
    completed_at_us:int=Field(ge=0)

    @model_validator(mode='after')
    def usable_requires_all_checks(self):
        if self.completed_at_us<self.started_at_us:raise ValueError('time order invalid')
        if self.assessment=='USABLE' and any(item.status!='CONFIRMED' for item in self.checks):
            raise ValueError('usable requires confirmed checks')
        return self


class FrozenJsonProofSource(RuntimeModel):
    source_id:SourceId
    revision:int=Field(ge=1)
    source_fingerprint:Digest
    config:AnyProofSourceConfig
    contract:ProofContractAttestation
    owner_subject_id:str=Field(pattern=SAFE_SUBJECT)
    identity_roles:dict[IdentityId,Annotated[str,Field(pattern=SAFE_SUBJECT)]]


class ProofSourceAdoption(RuntimeModel):
    schema_version:Literal['1']='1'
    project_id:ProjectId
    source_id:SourceId
    revision:int=Field(ge=1)
    source_fingerprint:Digest
    preflight_id:PreflightId
    binding_fingerprint:Digest
    created_at_us:int=Field(ge=0)


class ProofRunnerInput(RuntimeModel):
    schema_version:Literal['1']='1'
    job_id:str=Field(pattern=r'^job_[0-9a-f]{32}$')
    attempt:int=Field(ge=1)
    fencing_token:int=Field(ge=1)
    lease_owner:str=Field(min_length=1,max_length=128)
    request:ProofPreflightInput
    request_fingerprint:Digest

    @model_validator(mode='after')
    def input_hash(self):
        if self.request_fingerprint!=proof_fingerprint(self.request):raise ValueError('preflight input hash mismatch')
        return self


def proof_bytes(value:RuntimeModel)->bytes:
    raw=json.dumps(value.model_dump(mode='json'),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>262144:raise ValueError('proof document exceeds limit')
    return raw


def proof_fingerprint(value:RuntimeModel)->str:
    return hashlib.sha256(proof_bytes(value)).hexdigest()
