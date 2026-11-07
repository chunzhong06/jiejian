# 有界来源与预检查的独立协议；只描述可读事实与关联，不接受客户端声明可靠或安全通过。
from __future__ import annotations
import hashlib
import json
import re
from typing import Annotated,Literal
from urllib.parse import unquote,urlsplit
from product.protocols.codec import decode_document, encode_json
from pydantic import Field,field_validator,model_validator
from product.protocols.runtime.runtime_identity import RuntimeModel, Digest, RuntimeFile
from product.protocols.runtime.node_runtime import NodeRuntimeReference, ProjectId
from product.protocols.checks.identity import CheckIdentity
from product.protocols.web.target import WebTargetScope
from product.protocols.checks.business_facts import ArtifactManifestReference
from product.protocols.runtime.database_capture import DatabaseCapture

SourceId=Annotated[str,Field(pattern=r'^psr_[0-9a-f]{32}$')]
PreflightId=Annotated[str,Field(pattern=r'^ppf_[0-9a-f]{32}$')]
ScopeId=Annotated[str,Field(pattern=r'^prs_[0-9a-f]{32}$')]
OperationId=Annotated[str,Field(pattern=r'^[0-9a-f]{32}$')]
IdentityId=Annotated[str,Field(pattern=r'^tid_[0-9a-f]{32}$')]
ObjectPath=Annotated[tuple[Annotated[str,Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')],...],Field(min_length=1,max_length=8)]
MappingKey=Literal['resource_id','owner_id','state','tenant','condition_state','version','effect_count','history_generation',
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
    tenant_path:ObjectPath|None=Field(default=None,exclude_if=lambda value:value is None)

    @field_validator('request_path')
    @classmethod
    def request(cls,value):return safe_identity_path(value)

    @field_validator('subject_path','role_path','tenant_path')
    @classmethod
    def nonsensitive(cls,value):
        if value is None:return value
        if any(part.casefold() in {'password','token','cookie','authorization','secret','api_key','constructor','__proto__'} for part in value):
            raise ValueError('secret identity field prohibited')
        return value


class RelationshipSourceMapping(RuntimeModel):
    application_action: str = Field(pattern=SAFE_SUBJECT)
    scope_complete_path: ObjectPath | None = None
    source_time_path: ObjectPath | None = None
    subject_organizations_path: ObjectPath | None = None
    subject_groups_path:ObjectPath|None=None
    resource_organization_path: ObjectPath | None = None
    organization_parents_path: ObjectPath | None = None
    subject_roles_path: ObjectPath | None = None
    role_inheritance_path: ObjectPath | None = None
    grants_path: ObjectPath | None = None
    clock_uncertainty_us: int = Field(default=0, ge=0, le=5_000_000)

    @model_validator(mode='after')
    def public_paths(self):
        paths = [getattr(self, name) for name in type(self).model_fields if name.endswith('_path')]
        if not any(paths):
            raise ValueError('relationship source requires explicit field mappings')
        for path in paths:
            ManagedIdentityClaim.nonsensitive(path)
        return self

    def supports(self, requirement):
        if self.scope_complete_path is None:
            return False
        if requirement.kind == 'ORGANIZATION':
            return (self.subject_organizations_path is not None and self.resource_organization_path is not None
                and (requirement.organization_scope == 'SAME' or self.organization_parents_path is not None))
        if requirement.kind == 'ROLE_INHERITANCE':
            return self.subject_roles_path is not None and self.role_inheritance_path is not None
        return self.grants_path is not None and self.source_time_path is not None


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
    relationship_mapping: RelationshipSourceMapping | None = Field(default=None, exclude_if=lambda value: value is None)
    state_field_optional: bool = Field(default=False, exclude_if=lambda value: not value)

    @model_validator(mode='after')
    def provider_mapping(self):
        if self.relative_path_template!=f'/collections/{self.collection}/{{resource_id}}':
            raise ValueError('source path must identify its controlled collection')
        if self.mappings.get('resource_id')!=('resource_id',) or self.mappings.get('owner_id')!=('owner_id',):
            raise ValueError('controlled source identity fields cannot be remapped')
        if set(self.mappings)-{'resource_id','owner_id','state','tenant','condition_state'}:
            raise ValueError('controlled source only maps resource, owner and state')
        if any(path[0] != 'data' or len(path) < 2 for key,path in self.mappings.items() if key in {'tenant','condition_state'}):
            raise ValueError('conditions must reference declared public resource data fields')
        if self.source_contract_id=='TRANSACTION_HISTORY_V1' and (len(self.mappings.get('state',()))<2 or self.mappings['state'][0]!='data'):
            raise ValueError('state must reference a protected resource data field')
        for path in (self.target_resource_path,self.target_owner_path,self.target_data_path):
            ManagedIdentityClaim.nonsensitive(path)
        if len(set(self.protected_projection))!=len(self.protected_projection):
            raise ValueError('duplicate protected projection')
        if (self.source_contract_id=='RESOURCE_FIELDS_V1') != bool(self.protected_projection):
            raise ValueError('protected projection must match disclosure source')
        return self



def source_identity_paths(config, identities=()):
    if isinstance(config,ManagedProofSourceConfig):
        return tuple(sorted({item.request_path for item in config.identity_claims}))
    # JSON 来源的身份路径取自本次冻结身份，不约定某个应用的接口。
    return tuple(sorted({item.verification.request.path for item in identities if item.verification is not None}))


def source_read_paths(config, identities=()):
    paths = {*source_identity_paths(config, identities), config.relative_path_template}
    export=getattr(config,'async_export',None)
    if export is not None:
        paths.update((export.status_path_template,export.file_path_template))
    if config.source_kind in {'CREATED_OBJECT_RECORDS','SQLITE_OBJECTS'}:
        paths.add(f'/collections/{config.collection}')
    return tuple(sorted(paths))


class ProofCheckItem(RuntimeModel):
    code:str=Field(pattern=r'^[A-Z][A-Z0-9_]{0,63}$')
    status:Literal['CONFIRMED','MISSING','UNAVAILABLE','UNSUPPORTED']
    mapping_key:MappingKey|None=None


class ProofSourceAdoption(RuntimeModel):
    schema_version:Literal['1']='1'
    project_id:ProjectId
    source_id:SourceId
    revision:int=Field(ge=1)
    source_fingerprint:Digest
    preflight_id:PreflightId
    binding_fingerprint:Digest
    created_at_us:int=Field(ge=0)


class AtomicProofSourceConfig(ManagedProofSourceConfig):
    source_contract_id:Literal['TRANSACTION_HISTORY_V2','RESOURCE_FIELDS_V1']

    @model_validator(mode='after')
    def atomic_mapping(self):
        if self.source_contract_id=='TRANSACTION_HISTORY_V2' and (len(self.mappings.get('state',()))<2 or self.mappings['state'][0]!='data'):
            raise ValueError('atomic state must reference a protected resource data field')
        return self


class SqliteProofSourceConfig(AtomicProofSourceConfig):
    source_kind: Literal['SQLITE_AUDIT'] = 'SQLITE_AUDIT'
    source_contract_id: Literal['TRANSACTION_HISTORY_V2'] = 'TRANSACTION_HISTORY_V2'
    database_path: str = Field(min_length=1, max_length=512)
    table: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    resource_column: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    owner_column: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    protected_column: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    observed_columns:tuple[Annotated[str,Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')],...]=Field(default=(),max_length=8)

    @model_validator(mode='after')
    def sqlite_projection(self):
        RuntimeFile.safe_path(self.database_path)
        if self.collection != self.table or self.mappings.get('state') != ('data', self.protected_column):
            raise ValueError('SQLite source must use the declared table and protected column')
        allowed = set(self.observed_columns or (self.protected_column,))
        if any(len(path) != 2 or path[1] not in allowed for key,path in self.mappings.items() if key in {'tenant','condition_state'}):
            raise ValueError('condition column is outside the declared SQLite capture')
        if self.relationship_mapping is not None:
            for name in ('resource_organization_path', 'organization_parents_path', 'role_inheritance_path', 'grants_path', 'scope_complete_path', 'source_time_path'):
                path = getattr(self.relationship_mapping, name)
                if path is not None and path[0] not in allowed:
                    raise ValueError('relationship column is outside the declared SQLite capture')
        return self


class AsyncExportMapping(RuntimeModel):
    dispatch_task_path:ObjectPath
    status_path_template:str=Field(min_length=2,max_length=512)
    file_path_template:str=Field(min_length=2,max_length=512)
    task_path:ObjectPath
    state_path:ObjectPath
    resource_path:ObjectPath
    owner_path:ObjectPath
    subject_path:ObjectPath
    request_nonce_path:ObjectPath
    states:dict[Annotated[str,Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')],Literal['QUEUED','RUNNING','SUCCESS','FAILED','TIMED_OUT','CANCELLED']]=Field(min_length=3,max_length=16)
    max_polls:int=Field(default=16,ge=1,le=32)
    poll_interval_us:int=Field(default=100_000,ge=10_000,le=1_000_000)
    timeout_us:int=Field(default=5_000_000,ge=100_000,le=15_000_000)
    max_response_bytes:int=Field(default=262144,ge=1024,le=262144)

    @model_validator(mode='after')
    def bounded_mapping(self):
        for path in (self.status_path_template,self.file_path_template):
            safe_source_path(path.replace('{task_id}','{resource_id}'))
            if path.count('{task_id}')!=1:raise ValueError('async export requires one fixed task_id path')
        if self.status_path_template==self.file_path_template:raise ValueError('status and final entity require separate paths')
        for name in type(self).model_fields:
            if name.endswith('_path'):ManagedIdentityClaim.nonsensitive(getattr(self,name))
        if 'SUCCESS' not in self.states.values() or not {'FAILED','CANCELLED','TIMED_OUT'}&set(self.states.values()):
            raise ValueError('async export requires success and failure mappings')
        return self


class FileProofSourceConfig(AtomicProofSourceConfig):
    source_kind:Literal['REFERENCE_FILE']='REFERENCE_FILE'
    source_contract_id:Literal['FILE_RESPONSE_CONTENT_V1']='FILE_RESPONSE_CONTENT_V1'
    reference_artifact:ArtifactManifestReference|None=None
    reference_origin:Literal['UPLOAD','REFERENCE_CAPTURE']|None=None
    reference_resource_id:str=Field(min_length=1,max_length=256)
    reference_owner_identity_id:IdentityId
    async_export:AsyncExportMapping|None=Field(default=None,exclude_if=lambda value:value is None)

    @model_validator(mode='after')
    def reference_pair(self):
        if (self.reference_artifact is None)!=(self.reference_origin is None):raise ValueError('file reference origin mismatch')
        if self.async_export is not None and (self.async_export.timeout_us>self.timeout_us or self.async_export.max_response_bytes>self.max_response_bytes):
            raise ValueError('async export exceeds the source read budget')
        return self


class CreationProofSourceConfig(AtomicProofSourceConfig):
    source_kind:Literal['CREATED_OBJECT_RECORDS']='CREATED_OBJECT_RECORDS'
    source_contract_id:Literal['OBJECT_CREATION_V1']='OBJECT_CREATION_V1'

    @model_validator(mode='after')
    def creation_mapping(self):
        if set(self.mappings)!={'resource_id','owner_id'}:
            raise ValueError('creation source uses only object and owner mappings')
        return self


class SqliteCreationProofSourceConfig(CreationProofSourceConfig):
    source_kind:Literal['SQLITE_OBJECTS']='SQLITE_OBJECTS'
    database_path:str=Field(min_length=1,max_length=512)
    table:str=Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    resource_column:str=Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    owner_column:str=Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    protected_column:str=Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    observed_columns:tuple[Annotated[str,Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')],...]=Field(default=(),max_length=8)

    @model_validator(mode='after')
    def sqlite_mapping(self):
        RuntimeFile.safe_path(self.database_path)
        if self.collection!=self.table:raise ValueError('SQLite collection must name its table')
        return self


class DatabaseProofSourceConfig(AtomicProofSourceConfig):
    source_kind:Literal['DATABASE_AUDIT']='DATABASE_AUDIT'
    source_contract_id:Literal['TRANSACTION_HISTORY_V2']='TRANSACTION_HISTORY_V2'
    database_capture:DatabaseCapture
    protected_column:str=Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')

    @model_validator(mode='after')
    def declared_projection(self):
        declared=self.database_capture
        if (self.collection!=declared.table or self.protected_column not in declared.fields
                or self.mappings.get('state')!=('data',self.protected_column)):
            raise ValueError('database source must use its declared resource projection')
        if any(path[0]!='data' or len(path)!=2 or path[1] not in declared.fields
                for key,path in self.mappings.items() if key in {'tenant','condition_state'}):
            raise ValueError('condition is outside database projection')
        if self.relationship_mapping is not None:
            for name in ('resource_organization_path','organization_parents_path','role_inheritance_path','grants_path','scope_complete_path','source_time_path'):
                path=getattr(self.relationship_mapping,name)
                if path is not None and path[0] not in declared.fields:
                    raise ValueError('relationship is outside database projection')
        return self


CurrentProofSourceConfig=Annotated[AtomicProofSourceConfig|FileProofSourceConfig|CreationProofSourceConfig|SqliteProofSourceConfig|SqliteCreationProofSourceConfig|DatabaseProofSourceConfig,Field(discriminator='source_kind')]


class ProofContractAttestation(RuntimeModel):
    contract_id:Literal['TRANSACTION_HISTORY_V2','RESOURCE_FIELDS_V1','FILE_RESPONSE_CONTENT_V1','OBJECT_CREATION_V1']
    implementation_profile:Literal['CONTROLLED_TRANSACTION_RECORDS_V2','CONTROLLED_FILE_RECEIPT_V1','CONTROLLED_CREATION_V1','SQLITE_ROW_HISTORY_V1','SQLITE_CREATION_HISTORY_V1','POSTGRESQL_ROW_HISTORY_V1','MYSQL_ROW_HISTORY_V1']='CONTROLLED_TRANSACTION_RECORDS_V2'
    fingerprint:Digest
    approved_effect_kind:Literal['STATE_MUTATION','DATA_DISCLOSURE','FILE_CONTENT_DELIVERY','OBJECT_CREATION']

    @model_validator(mode='after')
    def matching_profile(self):
        if (self.contract_id=='FILE_RESPONSE_CONTENT_V1')!=(self.implementation_profile=='CONTROLLED_FILE_RECEIPT_V1'):
            raise ValueError('file contract profile mismatch')
        if (self.contract_id=='OBJECT_CREATION_V1')!=(self.implementation_profile in {'CONTROLLED_CREATION_V1','SQLITE_CREATION_HISTORY_V1'}):
            raise ValueError('creation contract profile mismatch')
        expected={'OBJECT_CREATION_V1':'OBJECT_CREATION','FILE_RESPONSE_CONTENT_V1':'FILE_CONTENT_DELIVERY','TRANSACTION_HISTORY_V2':'STATE_MUTATION','RESOURCE_FIELDS_V1':'DATA_DISCLOSURE'}
        if self.approved_effect_kind!=expected[self.contract_id]:raise ValueError('source contract effect mismatch')
        return self


class ProofSourceRevision(RuntimeModel):
    schema_version: Literal["1"] = "1"
    project_id:ProjectId
    source_id:SourceId
    revision:int=Field(ge=1)
    config:CurrentProofSourceConfig
    basis_id:str=Field(pattern=r'^pb_[0-9a-f]{64}$')
    fingerprint:Digest
    submitted_via:Literal['LOCAL_GUI','MCP']
    client_name:str=Field(max_length=80)
    created_at_us:int=Field(ge=0)

    @model_validator(mode='after')
    def content_identity(self):
        if self.fingerprint!=proof_fingerprint(self.config):raise ValueError('source config fingerprint mismatch')
        return self

    document_type: Literal["jiejian.proof-source-revision"] = "jiejian.proof-source-revision"


class SqliteReadSelection(RuntimeModel):
    database_path:str=Field(min_length=1,max_length=512)
    table:str=Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    columns:tuple[Annotated[str,Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')],...]=Field(min_length=1,max_length=10)

    @field_validator('database_path')
    @classmethod
    def database(cls,value):
        RuntimeFile.safe_path(value)
        return value


def sqlite_read_selections(config):
    return (SqliteReadSelection(database_path=config.database_path,table=config.table,
        columns=tuple(sorted({config.resource_column,config.owner_column,*(config.observed_columns or (config.protected_column,))}))),) if config.source_kind in {'SQLITE_AUDIT','SQLITE_OBJECTS'} else ()


class SourceReadScope(RuntimeModel):
    schema_version: Literal["1"] = "1"
    scope_id:ScopeId
    project_id:ProjectId
    origin:str
    path_templates:tuple[str,...]=Field(min_length=1,max_length=16)
    identity_ids:tuple[IdentityId,...]=Field(min_length=1,max_length=16)
    resource_binding_ids:tuple[Annotated[str,Field(pattern=r'^res_[0-9a-f]{32}$')],...]=Field(min_length=1,max_length=16)
    max_response_bytes:int=Field(ge=1024,le=262144)
    timeout_us:int=Field(ge=1000,le=5_000_000)
    created_at_us:int=Field(ge=0)
    sqlite:tuple[SqliteReadSelection,...]=Field(default=(),max_length=4,exclude_if=lambda value:not value)
    databases:tuple[DatabaseCapture,...]=Field(default=(),max_length=4,exclude_if=lambda value:not value)

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
            elif '{task_id}' in value:safe_source_path(value.replace('{task_id}','{resource_id}'))
            else:safe_identity_path(value)
        if len(set(values))!=len(values):raise ValueError('duplicate paths')
        return values

    document_type: Literal["jiejian.source-read-scope"] = "jiejian.source-read-scope"


class ProofPreflightInput(RuntimeModel):
    schema_version: Literal["1"] = "1"
    preflight_id:PreflightId
    project_id:ProjectId
    source_id:SourceId
    source_revision:int=Field(ge=1)
    source_fingerprint:Digest
    config:CurrentProofSourceConfig
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
    purpose:Literal['READ','INSTALL_DATABASE','REMOVE_DATABASE']=Field(default='READ',exclude_if=lambda value:value=='READ')
    maintenance_plan_fingerprint:Digest|None=Field(default=None,exclude_if=lambda value:value is None)

    @model_validator(mode='after')
    def association(self):
        if (self.purpose!='READ')!=(self.maintenance_plan_fingerprint is not None):
            raise ValueError('database maintenance requires an exact approved plan')
        if self.purpose!='READ' and (not isinstance(self.config,DatabaseProofSourceConfig) or self.authority_id!='LOCAL_GUI'):
            raise ValueError('database maintenance requires local authorization')
        if isinstance(self.config,DatabaseProofSourceConfig) and self.config.database_capture not in self.scope.databases:
            raise ValueError('database connection is outside granted scope')
        if (self.project_id!=self.scope.project_id or self.project_id!=self.runtime_reference.project_id
            or self.target.base_url!=self.scope.origin or self.target.base_url!=f'http://127.0.0.1:{self.runtime_reference.port}'
            or self.source_fingerprint!=proof_fingerprint(self.config) or self.config.read_scope_id not in (None,self.scope.scope_id)
            or self.config.relative_path_template not in self.scope.path_templates
            or not set(source_read_paths(self.config,self.identities))<=set(self.scope.path_templates)
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

    @model_validator(mode='after')
    def reference_ready(self):
        if isinstance(self.config,FileProofSourceConfig) and self.config.reference_artifact is None:
            raise ValueError('reference file must be prepared before preflight')
        return self

    document_type: Literal["jiejian.proof-preflight-input"] = "jiejian.proof-preflight-input"


class ProofPreflightReport(RuntimeModel):
    schema_version: Literal["1"] = "1"
    preflight_id:PreflightId
    job_id:str=Field(pattern=r'^job_[0-9a-f]{32}$')
    request_fingerprint:Digest
    source_fingerprint:Digest
    attempt:int=Field(ge=1)
    fencing_token:int=Field(ge=1)
    lease_owner:str=Field(min_length=1,max_length=128)
    assessment:Literal['USABLE','NEEDS_CHANGES','UNSUPPORTED','COMPLETED']
    checks:tuple[ProofCheckItem,...]=Field(min_length=1,max_length=48)
    started_at_us:int=Field(ge=0)
    completed_at_us:int=Field(ge=0)
    purpose:Literal['READ','INSTALL_DATABASE','REMOVE_DATABASE']=Field(default='READ',exclude_if=lambda value:value=='READ')

    @model_validator(mode='after')
    def usable_requires_all_checks(self):
        if self.assessment=='COMPLETED' and self.purpose=='READ' or self.assessment=='USABLE' and self.purpose!='READ':
            raise ValueError('maintenance is distinct from source usability')
        if self.completed_at_us<self.started_at_us:raise ValueError('time order invalid')
        if self.assessment in {'USABLE','COMPLETED'} and any(item.status!='CONFIRMED' for item in self.checks):
            raise ValueError('usable requires confirmed checks')
        return self

    document_type: Literal["jiejian.proof-preflight-report"] = "jiejian.proof-preflight-report"


class FrozenProofSource(RuntimeModel):
    source_id:SourceId
    revision:int=Field(ge=1)
    source_fingerprint:Digest
    config:CurrentProofSourceConfig
    contract:ProofContractAttestation
    owner_subject_id:str=Field(pattern=SAFE_SUBJECT)
    identity_roles:dict[IdentityId,Annotated[str,Field(pattern=SAFE_SUBJECT)]]
    adoption_preflight_id:PreflightId|None=None

    @model_validator(mode='after')
    def file_adoption_reference(self):
        if isinstance(self.config,CreationProofSourceConfig) and self.adoption_preflight_id is None:
            raise ValueError('creation proof requires adopted preflight')
        if isinstance(self.config,FileProofSourceConfig) and (self.adoption_preflight_id is None or self.config.reference_artifact is None):
            raise ValueError('file proof requires exact adopted preflight')
        return self


class ProofRunnerInput(RuntimeModel):
    schema_version: Literal["1"] = "1"
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

    document_type: Literal["jiejian.proof-runner-input"] = "jiejian.proof-runner-input"


def read_source_revision(raw):
    return _read_proof_document(raw,ProofSourceRevision)


def read_source_scope(raw):
    return _read_proof_document(raw,SourceReadScope)


def read_preflight_input(raw):
    return _read_proof_document(raw,ProofPreflightInput)


def read_preflight_report(raw):
    return _read_proof_document(raw,ProofPreflightReport)


def read_proof_runner(raw):
    return _read_proof_document(raw,ProofRunnerInput)


def _read_proof_document(raw, model):
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    decode_document(data, document_type=model.model_fields["document_type"].default,
        version=model.model_fields["schema_version"].default, limit=262144)
    return model.model_validate_json(data, strict=True)


def proof_bytes(value:RuntimeModel)->bytes:
    validated=type(value).model_validate_json(value.model_dump_json(), strict=True)
    raw=encode_json(validated.model_dump(mode='json'))
    if len(raw)>262144:raise ValueError('proof document exceeds limit')
    return raw


def proof_fingerprint(value:RuntimeModel)->str:
    return hashlib.sha256(proof_bytes(value)).hexdigest()
