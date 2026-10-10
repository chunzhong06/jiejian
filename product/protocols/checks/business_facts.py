# 封存可核对的有限业务事实；只表达采集值与关联，安全Verdict仍由原判定器产生。
from __future__ import annotations
import hashlib
import json
from typing import Annotated,Literal
from pydantic import Field,model_validator
from product.protocols.checks.execution_request import WireModel,Hash,EffectId,IdentityId

FactId=Annotated[str,Field(pattern=r'^bf_[0-9a-f]{64}$')]
ProofId=Annotated[str,Field(pattern=r'^[0-9a-f]{64}$')]
RecordId=Annotated[str,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')]
FactScalar=Annotated[str,Field(max_length=256)]|Annotated[int,Field(ge=-9_007_199_254_740_991,le=9_007_199_254_740_991)]|Annotated[float,Field(allow_inf_nan=False)]|bool|None
FieldPath=Annotated[tuple[Annotated[str,Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')],...],Field(min_length=1,max_length=8)]


class FactProofReference(WireModel):
    effect_id:EffectId
    proof_fingerprint:ProofId
    source_id:Annotated[str,Field(pattern=r'^(psr|exp)_[0-9a-f]{32}$')]
    source_revision:int=Field(ge=1)
    source_fingerprint:Hash


class CommittedFieldChange(WireModel):
    proof_fingerprint:ProofId
    path:FieldPath
    before:FactScalar
    after:FactScalar


class CommittedStateFact(WireModel):
    kind:Literal['COMMITTED_STATE']='COMMITTED_STATE'
    generation:RecordId
    operation_id:RecordId
    scope_ordinal:int=Field(ge=0,le=31)
    before_version:int=Field(ge=0)
    after_version:int=Field(ge=1)
    commit_semantics:Literal['ATOMIC_COMMIT']='ATOMIC_COMMIT'
    subject_identity_id:IdentityId
    owner_identity_id:IdentityId
    resource_id:str=Field(min_length=1,max_length=256)
    changes:tuple[CommittedFieldChange,...]=Field(min_length=1,max_length=8)

    @model_validator(mode='after')
    def commit_sequence(self):
        if self.after_version!=self.before_version+1:raise ValueError('commit versions are not consecutive')
        keys=[(item.proof_fingerprint,item.path) for item in self.changes]
        if len(keys)!=len(set(keys)) or keys!=sorted(keys):raise ValueError('duplicate or unsorted committed projection')
        return self


class IdentityCheckFact(WireModel):
    kind:Literal['IDENTITY_CHECK']='IDENTITY_CHECK'
    identity_id:IdentityId
    subject_match:Literal['MATCH','MISMATCH','UNKNOWN']
    role_match:Literal['MATCH','MISMATCH','UNKNOWN']


class FieldContentComparison(WireModel):
    path:str=Field(min_length=1,max_length=128)
    expected_digest:Hash|None=None
    received_digest:Hash|None=None
    matched:bool

    @model_validator(mode='after')
    def exact_comparison(self):
        if self.matched!=(self.expected_digest is not None and self.expected_digest==self.received_digest):
            raise ValueError('field comparison differs from collected digests')
        return self


class FieldDisclosureFact(WireModel):
    kind:Literal['FIELD_DISCLOSURE']='FIELD_DISCLOSURE'
    subject_identity_id:IdentityId
    owner_identity_id:IdentityId
    resource_id:str=Field(min_length=1,max_length=256)
    fields:tuple[FieldContentComparison,...]=Field(min_length=1,max_length=16)


class ArtifactManifestReference(WireModel):
    asset_id:Annotated[str,Field(pattern=r'^pai_[0-9a-f]{32}$')]
    sha256:Hash
    size:int=Field(gt=0,le=4*1024*1024)


class ReferenceArtifactFact(WireModel):
    kind:Literal['REFERENCE_ARTIFACT']='REFERENCE_ARTIFACT'
    manifest:ArtifactManifestReference
    origin:Literal['UPLOAD','REFERENCE_CAPTURE']
    adoption_ref:Annotated[str,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')]


class FileReceiptFact(WireModel):
    kind:Literal['FILE_RECEIPT']='FILE_RECEIPT'
    actual_size:int=Field(ge=0,le=4*1024*1024)
    actual_sha256:Hash|None=None
    complete:bool
    expected:ArtifactManifestReference
    comparison:Literal['MATCH','DIFFERENT','INCOMPLETE']
    subject_identity_id:IdentityId
    owner_identity_id:IdentityId
    resource_id:str=Field(min_length=1,max_length=256)

    @model_validator(mode='after')
    def complete_match(self):
        matched=self.complete and self.actual_size==self.expected.size and self.actual_sha256==self.expected.sha256
        if (self.comparison=='MATCH')!=matched or (self.comparison=='DIFFERENT')!=(self.complete and not matched):
            raise ValueError('file comparison differs from collected entity bytes')
        return self


FactData=Annotated[CommittedStateFact|IdentityCheckFact|FieldDisclosureFact|ReferenceArtifactFact|FileReceiptFact,Field(discriminator='kind')]


def fact_content_id(payload):
    raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return 'bf_'+hashlib.sha256(raw).hexdigest()


class BusinessFact(WireModel):
    fact_id:FactId
    case_id:Annotated[str,Field(pattern=r'^case_[0-9a-f]{32}$')]
    request_ref:Annotated[str,Field(pattern=r'^req_[0-9a-f]{48}$')]
    observed_at_us:int=Field(ge=0)
    collector_kind:Literal['CONTROLLED_RECORDS','IDENTITY_READER','HTTP_ENTITY','REFERENCE_STORE']
    collector_version:Literal['2']='2'
    proofs:tuple[FactProofReference,...]=Field(min_length=1,max_length=8)
    complete:bool
    reason_codes:tuple[Annotated[str,Field(pattern=r'^[A-Z][A-Z0-9_]{0,127}$')],...]=Field(default=(),max_length=8)
    data:FactData

    @model_validator(mode='after')
    def bounded_fact(self):
        keys=[item.proof_fingerprint for item in self.proofs]
        if keys!=sorted(set(keys)):raise ValueError('fact proof references must be unique and sorted')
        if self.fact_id!=fact_content_id(self.model_dump(mode='json',exclude={'fact_id'})):
            raise ValueError('business fact content address mismatch')
        if len(self.model_dump_json().encode('utf-8'))>2048:raise ValueError('business fact exceeds 2KiB')
        if isinstance(self.data,CommittedStateFact) and {item.proof_fingerprint for item in self.data.changes}!=set(keys):
            raise ValueError('committed projection must cover exact proof references')
        collector={'COMMITTED_STATE':'CONTROLLED_RECORDS','IDENTITY_CHECK':'IDENTITY_READER',
            'FIELD_DISCLOSURE':'HTTP_ENTITY','FILE_RECEIPT':'HTTP_ENTITY','REFERENCE_ARTIFACT':'REFERENCE_STORE'}
        if self.collector_kind!=collector[self.data.kind]:raise ValueError('business fact collector mismatch')
        return self


def seal_business_fact(**values):
    draft=BusinessFact.model_construct(fact_id='bf_'+'0'*64,**values)
    payload=draft.model_dump(mode='json',exclude={'fact_id'})
    payload['fact_id']=fact_content_id(payload)
    return BusinessFact.model_validate_json(json.dumps(payload),strict=True)


class RecordObservationWindow(WireModel):
    generation:RecordId
    before_version:int=Field(ge=0)
    after_version:int=Field(ge=0)
    before_value:FactScalar
    after_value:FactScalar
    before_operation:RecordId|None=None
    after_operation:RecordId|None=None
    scope_state:Literal['OPEN','COMPLETE','INCOMPLETE','MISSING']
    operation_count:int=Field(ge=0,le=32)
    request_matched:bool
    source_complete:bool
    field_path:FieldPath


class DisclosureObservationWindow(WireModel):
    protected_paths:tuple[Annotated[str,Field(min_length=1,max_length=256)],...]=Field(min_length=1,max_length=64)
    baseline_digest:Hash|None=None
    current_digest:Hash|None=None
    source_unchanged:bool
    resource_matched:bool
    rejected_empty_response:bool
    scope_state:Literal['OPEN','COMPLETE','INCOMPLETE','MISSING']
    request_matched:bool


class FileObservationWindow(WireModel):
    expected:ArtifactManifestReference
    resource_matched:bool
    request_matched:bool
    scope_state:Literal['OPEN','COMPLETE','INCOMPLETE','MISSING']
    refused:bool


class ObservationFactReference(WireModel):
    proof_fingerprint:ProofId
    observer_id:Annotated[str,Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')]
    phase:Literal['BASELINE','BEFORE','AFTER','EVENTUAL','RECOVERY']
    fact_ids:tuple[FactId,...]=Field(default=(),max_length=64)
    source:FactProofReference
    method:Literal['STATE_SNAPSHOT','ATOMIC_STATE','FIELD_SNAPSHOT','FIELD_DISCLOSURE','FILE_SNAPSHOT','FILE_DELIVERY']
    record_window:RecordObservationWindow|None=None
    disclosure_window:DisclosureObservationWindow|None=None
    file_window:FileObservationWindow|None=None
    complete:bool
    reason_codes:tuple[Annotated[str,Field(pattern=r'^[A-Z][A-Z0-9_]{0,127}$')],...]=Field(default=(),max_length=8)

    @model_validator(mode='after')
    def reference_shape(self):
        if self.source.proof_fingerprint!=self.proof_fingerprint or len(set(self.fact_ids))!=len(self.fact_ids):
            raise ValueError('observation fact reference mismatch')
        if (self.method in {'STATE_SNAPSHOT','ATOMIC_STATE'})!=(self.record_window is not None):
            raise ValueError('record window does not match observation method')
        if (self.method in {'FIELD_SNAPSHOT','FIELD_DISCLOSURE'})!=(self.disclosure_window is not None):
            raise ValueError('disclosure window does not match observation method')
        if (self.method in {'FILE_SNAPSHOT','FILE_DELIVERY'})!=(self.file_window is not None):
            raise ValueError('file window does not match observation method')
        return self
