"""不可变环境修订；活动环境快照由应用理解记录持有。"""
from sqlalchemy import ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.infrastructure.storage.base import Base, _flush, ensure_storage_payload_safe
from product.protocols.web.environment import parse_environment_document
from product.backend.domain.errors import ErrorCode,JiejianError


class EnvironmentRow(Base):
    __tablename__ = 'application_environments'
    environment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.project_id', ondelete='RESTRICT'), index=True)
    payload: Mapped[str] = mapped_column(Text)


class EnvironmentRepository:
    def __init__(self, session, known_secrets):
        self._session, self._secrets = session, known_secrets

    def revisions(self, project_id):
        rows = self._session.scalars(select(EnvironmentRow).where(EnvironmentRow.project_id == project_id)
            .order_by(EnvironmentRow.environment_id, EnvironmentRow.revision.desc())).all()
        return tuple(self._document(row) for row in rows)

    @staticmethod
    def _document(row):
        try:
            document=parse_environment_document(row.payload)
            if (document.project_id,document.configuration.environment_id,document.configuration.revision)!=(row.project_id,row.environment_id,row.revision):
                raise ValueError('environment index mismatch')
            return document
        except ValueError:
            raise JiejianError(ErrorCode.STORAGE_STATE,'环境修订无法读取或与索引不符') from None

    def latest(self, project_id, environment_id=None):
        revisions = select(EnvironmentRow.environment_id, func.max(EnvironmentRow.revision).label('revision')).where(
            EnvironmentRow.project_id == project_id)
        if environment_id is not None:
            revisions = revisions.where(EnvironmentRow.environment_id == environment_id)
        latest = revisions.group_by(EnvironmentRow.environment_id).subquery()
        query = select(EnvironmentRow).join(latest, (EnvironmentRow.environment_id == latest.c.environment_id) &
            (EnvironmentRow.revision == latest.c.revision)).where(EnvironmentRow.project_id == project_id)
        return tuple(self._document(row) for row in self._session.scalars(query.order_by(EnvironmentRow.environment_id)))

    def revision(self, project_id, environment_id, revision):
        row = self._session.get(EnvironmentRow, (environment_id, revision))
        return None if row is None or row.project_id != project_id else self._document(row)

    def add(self, document):
        ensure_storage_payload_safe(document.model_dump(mode='json'), self._secrets)
        self._session.add(EnvironmentRow(environment_id=document.configuration.environment_id,
            revision=document.configuration.revision, project_id=document.project_id, payload=document.model_dump_json()))
        _flush(self._session)
