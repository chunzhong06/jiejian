# 持久保存不可变来源修订、预检查输入和读取授权；报告可见性与Job发布同事务，准备状态不落盘。
from sqlalchemy import BigInteger,CheckConstraint,ForeignKey,ForeignKeyConstraint,Integer,String,Text,select,update
from sqlalchemy.orm import Mapped,mapped_column
from product.backend.infra.storage.base import Base,_flush,ensure_storage_payload_safe
from product.backend.core.errors import ErrorCode,JiejianError
from product.protocols.proof_sources import ProofSourceRevision,SourceReadScope,ProofPreflightInput,ProofSourceAdoption,proof_fingerprint


class ProofSourceRow(Base):
    __tablename__='proof_sources'
    __table_args__=(CheckConstraint('revision >= 1',name='revision_positive'),)
    source_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'))
    revision:Mapped[int]=mapped_column(Integer)
    adoption_json:Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at_us:Mapped[int]=mapped_column(BigInteger)


class ProofSourceRevisionRow(Base):
    __tablename__='proof_source_revisions'
    source_id:Mapped[str]=mapped_column(String(36),ForeignKey('proof_sources.source_id',ondelete='RESTRICT'),primary_key=True)
    revision:Mapped[int]=mapped_column(Integer,primary_key=True)
    fingerprint:Mapped[str]=mapped_column(String(64))
    payload:Mapped[str]=mapped_column(Text)


class ProofReadScopeRow(Base):
    __tablename__='proof_read_scopes'
    scope_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'))
    fingerprint:Mapped[str]=mapped_column(String(64))
    payload:Mapped[str]=mapped_column(Text)
    revoked_at_us:Mapped[int|None]=mapped_column(BigInteger,nullable=True)


class ProofPreflightRow(Base):
    __tablename__='proof_preflights'
    __table_args__=(ForeignKeyConstraint(['source_id','source_revision'],['proof_source_revisions.source_id','proof_source_revisions.revision'],ondelete='RESTRICT'),)
    preflight_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'))
    source_id:Mapped[str]=mapped_column(String(36))
    source_revision:Mapped[int]=mapped_column(Integer)
    input_fingerprint:Mapped[str]=mapped_column(String(64))
    input_json:Mapped[str]=mapped_column(Text)
    report_sha256:Mapped[str|None]=mapped_column(String(64),nullable=True)
    created_at_us:Mapped[int]=mapped_column(BigInteger)


class ProofSourceRepository:
    def __init__(self,session,known_secrets=()):self._session,self._secrets=session,known_secrets

    def source(self,project_id,source_id,revision=None):
        head=self._session.get(ProofSourceRow,source_id)
        if head is None or head.project_id!=project_id:return None
        row=self._session.get(ProofSourceRevisionRow,(source_id,head.revision if revision is None else revision))
        if row is None:return None
        value=ProofSourceRevision.model_validate_json(row.payload)
        if (value.project_id,value.source_id,value.revision,value.fingerprint)!=(project_id,row.source_id,row.revision,row.fingerprint):
            raise JiejianError(ErrorCode.STORAGE_STATE,'来源修订关联不一致')
        return value

    def list(self,project_id,*,offset=0,limit=50):
        heads=self._session.scalars(select(ProofSourceRow).where(ProofSourceRow.project_id==project_id)
            .order_by(ProofSourceRow.created_at_us,ProofSourceRow.source_id).offset(offset).limit(limit)).all()
        return tuple(self.source(project_id,row.source_id) for row in heads)

    def save(self,value,*,expected_revision=None):
        ensure_storage_payload_safe(value.model_dump(mode='json'),self._secrets)
        if expected_revision is None:
            self._session.add(ProofSourceRow(source_id=value.source_id,project_id=value.project_id,revision=value.revision,created_at_us=value.created_at_us))
            _flush(self._session)
        else:
            changed=self._session.execute(update(ProofSourceRow).where(ProofSourceRow.source_id==value.source_id,
                ProofSourceRow.project_id==value.project_id,ProofSourceRow.revision==expected_revision).values(revision=value.revision))
            if changed.rowcount!=1:raise JiejianError(ErrorCode.STATE_PRECONDITION,'证明来源已有新修订')
        self._session.add(ProofSourceRevisionRow(source_id=value.source_id,revision=value.revision,fingerprint=value.fingerprint,payload=value.model_dump_json()))
        _flush(self._session)

    def adoption(self,project_id,source_id):
        row=self._session.get(ProofSourceRow,source_id)
        if row is None or row.project_id!=project_id or row.adoption_json is None:return None
        value=ProofSourceAdoption.model_validate_json(row.adoption_json)
        if (value.project_id,value.source_id)!=(project_id,source_id):raise JiejianError(ErrorCode.STORAGE_STATE,'来源采用归属不一致')
        source=self.source(project_id,source_id,value.revision)
        if source is None or source.fingerprint!=value.source_fingerprint:raise JiejianError(ErrorCode.STORAGE_STATE,'来源采用修订不可核对')
        return value

    def adopt(self,value):
        row=self._session.get(ProofSourceRow,value.source_id)
        if row is None or row.project_id!=value.project_id or row.revision!=value.revision:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'采用来源已变化')
        row.adoption_json=value.model_dump_json();_flush(self._session)

    def scope(self,project_id,scope_id):
        row=self._session.get(ProofReadScopeRow,scope_id)
        if row is None or row.project_id!=project_id or row.revoked_at_us is not None:return None
        value=SourceReadScope.model_validate_json(row.payload)
        if (value.project_id,value.scope_id,proof_fingerprint(value))!=(project_id,scope_id,row.fingerprint):
            raise JiejianError(ErrorCode.STORAGE_STATE,'来源读取授权关联不一致')
        return value

    def scopes(self,project_id):
        rows=self._session.scalars(select(ProofReadScopeRow).where(ProofReadScopeRow.project_id==project_id,
            ProofReadScopeRow.revoked_at_us.is_(None)).order_by(ProofReadScopeRow.scope_id).limit(200)).all()
        return tuple(self.scope(project_id,row.scope_id) for row in rows)

    def add_scope(self,value):
        ensure_storage_payload_safe(value.model_dump(mode='json'),self._secrets)
        self._session.add(ProofReadScopeRow(scope_id=value.scope_id,project_id=value.project_id,
            fingerprint=proof_fingerprint(value),payload=value.model_dump_json()));_flush(self._session)

    def revoke(self,project_id,scope_id,now):
        self._session.execute(update(ProofReadScopeRow).where(ProofReadScopeRow.scope_id==scope_id,
            ProofReadScopeRow.project_id==project_id,ProofReadScopeRow.revoked_at_us.is_(None)).values(revoked_at_us=now))
        _flush(self._session)

    def add_preflight(self,value):
        ensure_storage_payload_safe(value.model_dump(mode='json'),self._secrets)
        self._session.add(ProofPreflightRow(preflight_id=value.preflight_id,project_id=value.project_id,
            source_id=value.source_id,source_revision=value.source_revision,input_fingerprint=proof_fingerprint(value),
            input_json=value.model_dump_json(),created_at_us=value.created_at_us));_flush(self._session)

    def preflight(self,project_id,preflight_id):
        row=self._session.get(ProofPreflightRow,preflight_id)
        if row is None or row.project_id!=project_id:return None
        value=ProofPreflightInput.model_validate_json(row.input_json)
        if (value.project_id,value.preflight_id,value.source_id,value.source_revision,proof_fingerprint(value))!=(project_id,preflight_id,row.source_id,row.source_revision,row.input_fingerprint):
            raise JiejianError(ErrorCode.STORAGE_STATE,'预检查输入关联不一致')
        return value

    def preflights(self,project_id,source_id,revision,limit=20):
        rows=self._session.scalars(select(ProofPreflightRow).where(ProofPreflightRow.project_id==project_id,
            ProofPreflightRow.source_id==source_id,ProofPreflightRow.source_revision==revision)
            .order_by(ProofPreflightRow.created_at_us.desc(),ProofPreflightRow.preflight_id.desc()).limit(limit)).all()
        return tuple(self.preflight(project_id,row.preflight_id) for row in rows)

    def report_hash(self,project_id,preflight_id):
        row=self._session.get(ProofPreflightRow,preflight_id)
        return None if row is None or row.project_id!=project_id else row.report_sha256

    def publish(self,project_id,preflight_id,report_hash):
        row=self._session.get(ProofPreflightRow,preflight_id)
        if row is None or row.project_id!=project_id or row.report_sha256 not in (None,report_hash):
            raise JiejianError(ErrorCode.STORAGE_STATE,'预检查报告不可覆盖')
        row.report_sha256=report_hash;_flush(self._session)
