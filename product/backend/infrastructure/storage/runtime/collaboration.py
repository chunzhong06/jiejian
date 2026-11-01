import json

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infrastructure.storage.base import Base, _flush, ensure_storage_payload_safe
from product.backend.domain.errors import ErrorCode, JiejianError
from product.protocols.codec import decode_json


class CollaborationRow(Base):
    __tablename__ = 'collaboration_tasks'
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('projects.project_id', ondelete='RESTRICT'), index=True)
    state: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer)
    updated_at_us: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[str] = mapped_column(Text)


class CollaborationRepository:
    """在调用方 UoW 中保存任务；不自行提交，也不以任务状态替代业务仓储。"""
    def __init__(self, session, known_secrets=()):
        self.session, self.secrets = session, known_secrets

    def get(self, project, task):
        row = self.session.get(CollaborationRow, task)
        return self._read(row) if row and row.project_id == project else None

    def list(self, project, *, limit=40):
        rows = self.session.scalars(select(CollaborationRow).where(CollaborationRow.project_id == project)
            .order_by(CollaborationRow.updated_at_us.desc()).limit(limit))
        return [self._read(row) for row in rows]

    def active(self):
        rows = self.session.scalars(select(CollaborationRow).where(
            CollaborationRow.state.not_in(('COMPLETED', 'CANCELLED'))))
        return [self._read(row) for row in rows]

    def current(self, project):
        row = self.session.scalars(select(CollaborationRow).where(CollaborationRow.project_id == project,
            CollaborationRow.state.not_in(('COMPLETED', 'CANCELLED')))
            .order_by(CollaborationRow.updated_at_us.desc()).limit(1)).first()
        return None if row is None else self._read(row)

    @staticmethod
    def _read(row):
        # 持久根只有这一处 reader；未知格式不能由当前环境补成一个可继续执行的任务。
        try:
            value = decode_json(row.payload)
            if value['schema_version'] != '1' or any(value[key] != getattr(row, key)
                for key in ('task_id', 'project_id', 'state', 'revision', 'updated_at_us')):
                raise ValueError('task root identity mismatch')
            return value
        except (ValueError, KeyError, TypeError):
            raise JiejianError(ErrorCode.STORAGE_STATE, '协作任务的持久格式或关联不一致') from None

    def save(self, value):
        ensure_storage_payload_safe(value, self.secrets)
        row = self.session.get(CollaborationRow, value['task_id'])
        if row is None:
            row = CollaborationRow(task_id=value['task_id'], project_id=value['project_id'])
            self.session.add(row)
        row.state, row.revision, row.updated_at_us = value['state'], value['revision'], value['updated_at_us']
        row.payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        _flush(self.session)
