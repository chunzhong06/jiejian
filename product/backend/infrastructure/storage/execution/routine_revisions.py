"""完整方案与环境绑定的追加存储；目录查询只读取当前修订摘要。"""
from sqlalchemy import BigInteger, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.storage.base import Base, _flush, ensure_storage_payload_safe
from product.protocols.checks.routines import read_routine, read_routine_binding, routine_bytes


class RoutineRevisionRow(Base):
    __tablename__ = 'check_routine_revisions'
    __table_args__ = (UniqueConstraint('project_id', 'operation_id'),)
    routine_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('projects.project_id', ondelete='RESTRICT'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    scope_kind: Mapped[str] = mapped_column(String(16))
    permission_count: Mapped[int] = mapped_column(Integer)
    operation_id: Mapped[str] = mapped_column(String(32))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at_us: Mapped[int] = mapped_column(BigInteger)


class RoutineBindingRow(Base):
    __tablename__ = 'check_routine_bindings'
    __table_args__ = (ForeignKeyConstraint(['routine_id', 'routine_revision'],
        ['check_routine_revisions.routine_id', 'check_routine_revisions.revision'], ondelete='RESTRICT'),)
    binding_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('projects.project_id', ondelete='RESTRICT'), index=True)
    routine_id: Mapped[str] = mapped_column(String(36))
    routine_revision: Mapped[int] = mapped_column(Integer)
    environment_id: Mapped[str] = mapped_column(String(36))
    environment_revision: Mapped[int] = mapped_column(Integer)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at_us: Mapped[int] = mapped_column(BigInteger)


class RoutineRevisionRepository:
    def __init__(self, session, known_secrets=()):
        self.session, self.secrets = session, known_secrets

    def _document(self, row):
        if row is None:
            return None
        try:
            document = read_routine(row.payload_json.encode('utf-8'))
        except ValueError as exc:
            raise JiejianError(ErrorCode.STORAGE_STATE, '检查方案修订格式无效') from exc
        if (document.routine_id, document.revision, document.project_id, document.name, document.created_at_us) != (
            row.routine_id, row.revision, row.project_id, row.name, row.created_at_us):
            raise JiejianError(ErrorCode.STORAGE_STATE, '检查方案修订与目录不一致')
        return document

    def get(self, project, routine, revision):
        row = self.session.get(RoutineRevisionRow, (routine, revision))
        return self._document(row) if row is not None and row.project_id == project else None

    def latest(self, project, routine):
        row = self.session.scalar(select(RoutineRevisionRow).where(
            RoutineRevisionRow.project_id == project, RoutineRevisionRow.routine_id == routine)
            .order_by(RoutineRevisionRow.revision.desc()).limit(1))
        return self._document(row)

    def operation(self, project, operation):
        row = self.session.scalar(select(RoutineRevisionRow).where(
            RoutineRevisionRow.project_id == project, RoutineRevisionRow.operation_id == operation))
        return None if row is None else (self._document(row), row.request_fingerprint)

    def summaries(self, project, after=None, limit=50):
        latest = select(RoutineRevisionRow.routine_id, func.max(RoutineRevisionRow.revision).label('revision')).where(
            RoutineRevisionRow.project_id == project).group_by(RoutineRevisionRow.routine_id).subquery()
        query = select(RoutineRevisionRow.routine_id, RoutineRevisionRow.revision,
            RoutineRevisionRow.name, RoutineRevisionRow.scope_kind, RoutineRevisionRow.permission_count,
            RoutineRevisionRow.created_at_us).join(latest, (RoutineRevisionRow.routine_id == latest.c.routine_id) &
            (RoutineRevisionRow.revision == latest.c.revision))
        if after is not None:
            query = query.where(RoutineRevisionRow.routine_id > after)
        rows = self.session.execute(query.order_by(RoutineRevisionRow.routine_id).limit(limit))
        return [dict(row._mapping) for row in rows]

    def exists(self, project, routine):
        return self.session.scalar(select(RoutineRevisionRow.routine_id).where(
            RoutineRevisionRow.project_id == project, RoutineRevisionRow.routine_id == routine).limit(1)) is not None

    def history(self, project, routine, before=None):
        query = select(RoutineRevisionRow.revision, RoutineRevisionRow.name, RoutineRevisionRow.created_at_us).where(
            RoutineRevisionRow.project_id == project, RoutineRevisionRow.routine_id == routine)
        if before is not None:
            query = query.where(RoutineRevisionRow.revision < before)
        return [dict(row._mapping) for row in self.session.execute(query.order_by(RoutineRevisionRow.revision.desc()).limit(50))]

    def save(self, document, operation, fingerprint):
        ensure_storage_payload_safe(document.model_dump(mode='json'), self.secrets)
        self.session.add(RoutineRevisionRow(routine_id=document.routine_id, revision=document.revision,
            project_id=document.project_id, name=document.name, scope_kind='SCENARIO' if document.scope.scenario else 'PERMISSIONS',
            permission_count=len(document.scope.permissions), operation_id=operation, request_fingerprint=fingerprint,
            payload_json=routine_bytes(document).decode('utf-8'), created_at_us=document.created_at_us))
        _flush(self.session)

    def binding(self, project, binding):
        row = self.session.get(RoutineBindingRow, binding)
        if row is None or row.project_id != project:
            return None
        try:
            document = read_routine_binding(row.payload_json.encode('utf-8'))
        except ValueError as exc:
            raise JiejianError(ErrorCode.STORAGE_STATE, '检查方案环境绑定格式无效') from exc
        if (document.project_id, document.binding_id, document.routine_id, document.routine_revision,
            document.environment_id, document.environment_revision, document.created_at_us) != (
            row.project_id, row.binding_id, row.routine_id, row.routine_revision, row.environment_id,
            row.environment_revision, row.created_at_us):
            raise JiejianError(ErrorCode.STORAGE_STATE, '检查方案环境绑定与索引不一致')
        return document, row.request_fingerprint

    def bindings(self, project, routine, revision):
        ids = self.session.scalars(select(RoutineBindingRow.binding_id).where(RoutineBindingRow.project_id == project,
            RoutineBindingRow.routine_id == routine, RoutineBindingRow.routine_revision == revision)
            .order_by(RoutineBindingRow.created_at_us.desc()).limit(100))
        return [self.binding(project, binding)[0] for binding in ids]

    def save_binding(self, document, fingerprint):
        ensure_storage_payload_safe(document.model_dump(mode='json'), self.secrets)
        self.session.add(RoutineBindingRow(binding_id=document.binding_id, project_id=document.project_id,
            routine_id=document.routine_id, routine_revision=document.routine_revision,
            environment_id=document.environment_id, environment_revision=document.environment_revision,
            request_fingerprint=fingerprint, payload_json=routine_bytes(document).decode('utf-8'), created_at_us=document.created_at_us))
        _flush(self.session)
