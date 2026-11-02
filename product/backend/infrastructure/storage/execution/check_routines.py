import json

from sqlalchemy import ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infrastructure.storage.base import Base, _flush, ensure_storage_payload_safe
from product.backend.domain.errors import ErrorCode, JiejianError
from product.protocols.codec import decode_json


class CheckRoutineRow(Base):
    __tablename__ = 'check_routines'
    routine_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('projects.project_id', ondelete='CASCADE'), index=True)
    payload: Mapped[str] = mapped_column(Text)


class CheckRoutineRepository:
    def __init__(self, session, known_secrets=()):
        self.session, self.secrets = session, known_secrets

    def list(self, project):
        result = []
        for row in self.session.scalars(select(CheckRoutineRow).where(CheckRoutineRow.project_id == project)):
            value = decode_json(row.payload)
            if value.get('schema_version') != '1' or value.get('routine_id') != row.routine_id or value.get('project_id') != project:
                raise JiejianError(ErrorCode.STORAGE_STATE, '保存的检查方案格式或归属不一致')
            result.append(value)
        return sorted(result, key=lambda item:item['created_at_us'], reverse=True)

    def save(self, value):
        ensure_storage_payload_safe(value, self.secrets)
        self.session.add(CheckRoutineRow(routine_id=value['routine_id'], project_id=value['project_id'],
            payload=json.dumps(value, ensure_ascii=False, separators=(',', ':'))))
        _flush(self.session)

    def delete(self, project, routine):
        row = self.session.get(CheckRoutineRow, routine)
        if row and row.project_id == project:
            self.session.delete(row)
