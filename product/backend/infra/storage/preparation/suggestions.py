# 追加保存材料建议及同键回执；不与真实材料绑定或Preparation派生状态共用字段。
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, String, Text, select, update
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.core.preparation.suggestions import PreparationSuggestionRevision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import Base, _flush, ensure_storage_payload_safe


class PreparationSuggestionRow(Base):
    __tablename__ = 'preparation_suggestions'
    __table_args__ = (CheckConstraint('revision >= 1', name='revision_positive'),)
    suggestion_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('projects.project_id', ondelete='RESTRICT'))
    revision: Mapped[int] = mapped_column(Integer)
    created_at_us: Mapped[int] = mapped_column(BigInteger)
    updated_at_us: Mapped[int] = mapped_column(BigInteger)


class PreparationSuggestionRevisionRow(Base):
    __tablename__ = 'preparation_suggestion_revisions'
    __table_args__ = (CheckConstraint('revision >= 1', name='revision_positive'),)
    suggestion_id: Mapped[str] = mapped_column(String(36), ForeignKey('preparation_suggestions.suggestion_id', ondelete='RESTRICT'), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class PreparationSuggestionReceiptRow(Base):
    __tablename__ = 'preparation_suggestion_receipts'
    __table_args__ = (ForeignKeyConstraint(['suggestion_id','revision'],
        ['preparation_suggestion_revisions.suggestion_id','preparation_suggestion_revisions.revision'], ondelete='RESTRICT'),)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('projects.project_id', ondelete='RESTRICT'), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    suggestion_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)


class PreparationSuggestionRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def get(self, project_id, suggestion_id, revision=None):
        head = self._session.get(PreparationSuggestionRow, suggestion_id)
        if head is None or head.project_id != project_id:
            return None
        expected_revision = head.revision if revision is None else revision
        row = self._session.get(PreparationSuggestionRevisionRow, (suggestion_id, expected_revision))
        if row is None:
            return None
        if len(row.payload.encode('utf-8')) > 256*1024:
            raise JiejianError(ErrorCode.STORAGE_STATE, '保存的材料建议超过读取范围')
        value = PreparationSuggestionRevision.model_validate_json(row.payload)
        if (value.project_id,value.suggestion_id,value.revision) != (project_id,suggestion_id,expected_revision):
            raise JiejianError(ErrorCode.STORAGE_STATE, '材料建议修订归属不一致')
        return value

    def list(self, project_id, *, limit=50):
        rows = self._session.scalars(select(PreparationSuggestionRow).where(PreparationSuggestionRow.project_id == project_id)
            .order_by(PreparationSuggestionRow.updated_at_us.desc(), PreparationSuggestionRow.suggestion_id).limit(limit)).all()
        return [{'suggestion_id': row.suggestion_id, 'revision': row.revision, 'updated_at_us': row.updated_at_us} for row in rows]

    def append(self, value, *, expected_revision):
        ensure_storage_payload_safe(value.model_dump(mode='json'), self._secrets)
        if expected_revision is None:
            self._session.add(PreparationSuggestionRow(suggestion_id=value.suggestion_id, project_id=value.project_id,
                revision=1, created_at_us=value.created_at_us, updated_at_us=value.created_at_us))
            _flush(self._session)
        else:
            changed = self._session.execute(update(PreparationSuggestionRow).where(
                PreparationSuggestionRow.suggestion_id == value.suggestion_id, PreparationSuggestionRow.project_id == value.project_id,
                PreparationSuggestionRow.revision == expected_revision).values(revision=value.revision, updated_at_us=value.created_at_us))
            if changed.rowcount != 1:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '材料建议已有新修订，请重新读取')
        self._session.add(PreparationSuggestionRevisionRow(suggestion_id=value.suggestion_id, revision=value.revision, payload=value.model_dump_json()))
        _flush(self._session)

    def receipt(self, project_id, operation_id):
        row = self._session.get(PreparationSuggestionReceiptRow, (project_id,operation_id))
        return None if row is None else (row.request_fingerprint,row.suggestion_id,row.revision)

    def add_receipt(self, project_id, operation_id, fingerprint, value):
        self._session.add(PreparationSuggestionReceiptRow(project_id=project_id, operation_id=operation_id,
            request_fingerprint=fingerprint, suggestion_id=value.suggestion_id, revision=value.revision))
        _flush(self._session)
