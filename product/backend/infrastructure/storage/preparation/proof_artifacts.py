# 保存私有参照manifest和取样授权、冻结请求、报告引用；正文仅存在受控私有目录。
from sqlalchemy import BigInteger,CheckConstraint,ForeignKey,ForeignKeyConstraint,Integer,String,Text,select
from sqlalchemy.orm import Mapped,mapped_column
from product.backend.infrastructure.storage.base import Base,_flush,ensure_storage_payload_safe
from product.backend.domain.errors import ErrorCode,JiejianError
from product.protocols.preparation.proof_artifacts import ProofArtifactInput
from product.protocols.preparation.reference_capture import ReferenceCaptureRequest
from product.protocols.preparation.proof_sources import proof_fingerprint


class ProofArtifactInputRow(Base):
    __tablename__='proof_artifact_inputs'
    __table_args__=(CheckConstraint('byte_count >= 0 AND byte_count <= 4194304',name='size_bounds'),
        CheckConstraint("state IN ('PENDING','COMPLETE','INCOMPLETE','CANCELLED')",name='state_value'))
    asset_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'))
    state:Mapped[str]=mapped_column(String(16))
    byte_count:Mapped[int]=mapped_column(Integer)
    payload:Mapped[str]=mapped_column(Text)
    created_at_us:Mapped[int]=mapped_column(BigInteger)


class ReferenceCaptureAuthorizationRow(Base):
    __tablename__='reference_capture_authorizations'
    authorization_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'))
    plan_hash:Mapped[str]=mapped_column(String(64))
    control_session_id:Mapped[str]=mapped_column(String(36))
    created_at_us:Mapped[int]=mapped_column(BigInteger)
    revoked_at_us:Mapped[int|None]=mapped_column(BigInteger,nullable=True)


class ReferenceCaptureRow(Base):
    __tablename__='reference_captures'
    capture_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'))
    authorization_id:Mapped[str]=mapped_column(String(36),ForeignKey('reference_capture_authorizations.authorization_id',ondelete='RESTRICT'),unique=True)
    asset_id:Mapped[str|None]=mapped_column(String(36),ForeignKey('proof_artifact_inputs.asset_id',ondelete='RESTRICT'),unique=True,nullable=True)
    request_hash:Mapped[str]=mapped_column(String(64))
    request_json:Mapped[str]=mapped_column(Text)
    report_sha256:Mapped[str|None]=mapped_column(String(64),nullable=True)
    recovery_resolved_at_us:Mapped[int|None]=mapped_column(BigInteger,nullable=True)
    created_at_us:Mapped[int]=mapped_column(BigInteger)
    recovery_report_sha256:Mapped[str|None]=mapped_column(String(64),nullable=True)


class ProofArtifactReferenceRow(Base):
    __tablename__='proof_artifact_references'
    __table_args__=(ForeignKeyConstraint(['source_id','source_revision'],['proof_source_revisions.source_id','proof_source_revisions.revision'],ondelete='RESTRICT'),)
    asset_id:Mapped[str]=mapped_column(String(36),ForeignKey('proof_artifact_inputs.asset_id',ondelete='RESTRICT'),primary_key=True)
    source_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    source_revision:Mapped[int]=mapped_column(Integer,primary_key=True)


class ProofArtifactRepository:
    def __init__(self,session,known_secrets=()):self._session,self._secrets=session,known_secrets

    def input(self,project_id,asset_id):
        row=self._session.get(ProofArtifactInputRow,asset_id)
        if row is None or row.project_id!=project_id:return None
        value=ProofArtifactInput.model_validate_json(row.payload,strict=True)
        if (value.project_id,value.asset_id,value.state,0 if value.manifest is None else value.manifest.size)!=(
            row.project_id,row.asset_id,row.state,row.byte_count):raise JiejianError(ErrorCode.STORAGE_STATE,'参照输入关联不一致')
        return value

    def inputs(self,project_id):
        ids=self._session.scalars(select(ProofArtifactInputRow.asset_id).where(ProofArtifactInputRow.project_id==project_id,
            ProofArtifactInputRow.state!='CANCELLED').order_by(ProofArtifactInputRow.created_at_us,ProofArtifactInputRow.asset_id)).all()
        return tuple(self.input(project_id,item) for item in ids)

    def add_input(self,value):
        ensure_storage_payload_safe(value.model_dump(mode='json'),self._secrets)
        rows=self.inputs(value.project_id)
        # 待取样输入也预留完整4MiB，防止多个并发任务完成时越过项目容量。
        reserved=sum(item.manifest.size if item.manifest is not None else 4194304 for item in rows)
        required=value.manifest.size if value.manifest is not None else 4194304
        if len(rows)>=64 or reserved+required>268435456:raise JiejianError(ErrorCode.STATE_PRECONDITION,'参照输入达到容量上限')
        self._session.add(ProofArtifactInputRow(asset_id=value.asset_id,project_id=value.project_id,state=value.state,
            byte_count=0 if value.manifest is None else value.manifest.size,payload=value.model_dump_json(),created_at_us=value.created_at_us))
        _flush(self._session)

    def update_input(self,value,*,expected_state):
        row=self._session.get(ProofArtifactInputRow,value.asset_id)
        if row is None or row.project_id!=value.project_id or row.state!=expected_state:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'参照输入状态已经变化')
        previous=ProofArtifactInput.model_validate_json(row.payload)
        if previous.model_dump(exclude={'state','manifest'})!=value.model_dump(exclude={'state','manifest'}):
            raise JiejianError(ErrorCode.STORAGE_STATE,'参照输入归属不可改写')
        ensure_storage_payload_safe(value.model_dump(mode='json'),self._secrets)
        row.state=value.state;row.byte_count=0 if value.manifest is None else value.manifest.size;row.payload=value.model_dump_json()
        _flush(self._session)

    def add_capture(self,request):
        ensure_storage_payload_safe(request.model_dump(mode='json'),self._secrets)
        self._session.add(ReferenceCaptureAuthorizationRow(authorization_id=request.authorization_id,
            project_id=request.project_id,plan_hash=request.plan.plan_hash,control_session_id=request.control_session_id,
            created_at_us=request.created_at_us))
        _flush(self._session)
        self._session.add(ReferenceCaptureRow(capture_id=request.capture_id,project_id=request.project_id,
            authorization_id=request.authorization_id,asset_id=request.asset_id,request_hash=proof_fingerprint(request),
            request_json=request.model_dump_json(),created_at_us=request.created_at_us))
        _flush(self._session)

    def reference(self,project_id,asset_id,source_id,revision):
        if self.input(project_id,asset_id) is None:raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'参照输入不存在')
        self._session.add(ProofArtifactReferenceRow(asset_id=asset_id,source_id=source_id,source_revision=revision))
        _flush(self._session)

    def referenced(self,asset_id):
        return self._session.scalar(select(ProofArtifactReferenceRow.asset_id).where(ProofArtifactReferenceRow.asset_id==asset_id).limit(1)) is not None

    def capture(self,project_id,capture_id):
        row=self._session.get(ReferenceCaptureRow,capture_id)
        if row is None or row.project_id!=project_id:return None
        value=ReferenceCaptureRequest.model_validate_json(row.request_json,strict=True)
        if (value.project_id,value.capture_id,value.authorization_id,value.asset_id,proof_fingerprint(value))!=(
            project_id,capture_id,row.authorization_id,row.asset_id,row.request_hash):raise JiejianError(ErrorCode.STORAGE_STATE,'取样输入关联不一致')
        return value

    def captures(self,project_id):
        ids=self._session.scalars(select(ReferenceCaptureRow.capture_id).where(ReferenceCaptureRow.project_id==project_id)
            .order_by(ReferenceCaptureRow.created_at_us.desc()).limit(64)).all()
        return tuple(self.capture(project_id,item) for item in ids)

    def authorized(self,request):
        row=self._session.get(ReferenceCaptureAuthorizationRow,request.authorization_id)
        return row is not None and row.revoked_at_us is None and (row.project_id,row.plan_hash,row.control_session_id)==(
            request.project_id,request.plan.plan_hash,request.control_session_id)

    def unresolved_captures(self,project_id):
        ids=self._session.scalars(select(ReferenceCaptureRow.capture_id).where(ReferenceCaptureRow.project_id==project_id,
            ReferenceCaptureRow.recovery_resolved_at_us.is_(None)).order_by(ReferenceCaptureRow.created_at_us).limit(501)).all()
        if len(ids)>500:raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样恢复记录过多，请先核对待处理记录')
        return tuple(self.capture(project_id,item) for item in ids)

    def resolve_recovery(self,project_id,capture_id,digest,now):
        row=self._session.get(ReferenceCaptureRow,capture_id)
        if row is None or row.project_id!=project_id:raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'原取样不存在')
        if row.recovery_report_sha256 not in (None,digest):raise JiejianError(ErrorCode.STATE_PRECONDITION,'恢复已经由另一份报告核对')
        row.recovery_resolved_at_us=now;row.recovery_report_sha256=digest;_flush(self._session)

    def revoke(self,request,now):
        row=self._session.get(ReferenceCaptureAuthorizationRow,request.authorization_id)
        if row is not None and row.project_id==request.project_id and row.revoked_at_us is None:
            row.revoked_at_us=now;_flush(self._session)

    def report_hash(self,project_id,capture_id):
        row=self._session.get(ReferenceCaptureRow,capture_id)
        return None if row is None or row.project_id!=project_id else row.report_sha256

    def publish(self,project_id,capture_id,digest):
        row=self._session.get(ReferenceCaptureRow,capture_id)
        if row is None or row.project_id!=project_id or row.report_sha256 not in (None,digest):
            raise JiejianError(ErrorCode.STORAGE_STATE,'取样报告不可覆盖')
        row.report_sha256=digest;_flush(self._session)
