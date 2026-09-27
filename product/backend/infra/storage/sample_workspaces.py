# 保留官方示例的非秘密工作空间与实例所有权；核对记录追加保存，不改写操作历史。
import json
from sqlalchemy import BigInteger, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.infra.storage.base import Base, _flush, ensure_storage_payload_safe


class SampleWorkspaceRow(Base):
    __tablename__ = "sample_workspaces"
    workspace_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"))
    source_root: Mapped[str] = mapped_column(Text)
    scenario_version: Mapped[str] = mapped_column(String(24))
    created_at_us: Mapped[int] = mapped_column(BigInteger)


class SampleInstanceRow(Base):
    __tablename__ = "sample_instances"
    instance_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("sample_workspaces.workspace_id", ondelete="RESTRICT"))
    kernel_identity: Mapped[str] = mapped_column(Text)
    created_at_us: Mapped[int] = mapped_column(BigInteger)


class SampleReconciliationRow(Base):
    __tablename__ = "sample_reconciliations"
    reconciliation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(36), ForeignKey("sample_instances.instance_id", ondelete="RESTRICT"))
    observed_at_us: Mapped[int] = mapped_column(BigInteger)
    outcome: Mapped[str] = mapped_column(String(24))


class SampleWorkspaceRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def latest(self):
        row = self._session.scalars(select(SampleWorkspaceRow).order_by(SampleWorkspaceRow.created_at_us.desc(), SampleWorkspaceRow.workspace_id.desc()).limit(1)).first()
        return None if row is None else self._value(row)

    def for_project(self, project_id):
        row = self._session.scalars(select(SampleWorkspaceRow).where(SampleWorkspaceRow.project_id == project_id)
            .order_by(SampleWorkspaceRow.created_at_us.desc(), SampleWorkspaceRow.workspace_id.desc()).limit(1)).first()
        return None if row is None else self._value(row)

    def save(self, value):
        ensure_storage_payload_safe(value, self._secrets)
        row = self._session.get(SampleWorkspaceRow, value["workspace_id"])
        if row is None:
            self._session.add(SampleWorkspaceRow(**value))
        else:
            for key, item in value.items():
                setattr(row, key, item)
        _flush(self._session)

    def add_instance(self, instance_id, workspace_id, identity, created_at_us):
        ensure_storage_payload_safe(identity, self._secrets)
        self._session.add(SampleInstanceRow(instance_id=instance_id, workspace_id=workspace_id,
            kernel_identity=json.dumps(identity), created_at_us=created_at_us))
        _flush(self._session)

    def instance(self, workspace_id):
        row = self._session.scalars(select(SampleInstanceRow).where(SampleInstanceRow.workspace_id == workspace_id)
            .order_by(SampleInstanceRow.created_at_us.desc(), SampleInstanceRow.instance_id.desc()).limit(1)).first()
        if row is None:
            return None
        value = self._value(row)
        value["kernel_identity"] = json.loads(value["kernel_identity"])
        return value

    def observe(self, value):
        ensure_storage_payload_safe(value, self._secrets)
        self._session.add(SampleReconciliationRow(**value))
        _flush(self._session)

    def observation(self, instance_id):
        row = self._session.scalars(select(SampleReconciliationRow).where(SampleReconciliationRow.instance_id == instance_id)
            .order_by(SampleReconciliationRow.observed_at_us.desc()).limit(1)).first()
        return None if row is None else self._value(row)

    @staticmethod
    def _value(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}
