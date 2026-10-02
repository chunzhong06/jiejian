# 持久化开发任务、追加上下文、接收和交付回执；所有写入加入调用者同一事务。
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select, text, update, or_, and_
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.core.development import DevelopmentAcceptance, DevelopmentContext, DevelopmentDelivery, DevelopmentReceipt, DevelopmentTask, RuntimeActivationReceipt
from product.backend.core.development import NodeRuntimeActivationReceipt
import json
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import Base, _flush, ensure_storage_payload_safe


class DevelopmentTaskRow(Base):
    __tablename__ = "development_tasks"
    __table_args__ = (
        CheckConstraint("version >= 1 AND revision >= 1", name="revisions"),
        CheckConstraint("status IN ('ACTIVE','CLOSED','CANCELLED')", name="status"),
        Index("uq_development_active_project", "project_id", unique=True, sqlite_where=text("status = 'ACTIVE'")),
    )
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    created_at_us: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[str] = mapped_column(Text)


class DevelopmentContextRow(Base):
    __tablename__ = "development_contexts"
    __table_args__ = (UniqueConstraint("task_id", "revision"), CheckConstraint("revision >= 1", name="revision"))
    context_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("development_tasks.task_id", ondelete="RESTRICT"))
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)


class DevelopmentAcceptanceRow(Base):
    __tablename__ = "development_acceptances"
    context_id: Mapped[str] = mapped_column(String(36), ForeignKey("development_contexts.context_id", ondelete="RESTRICT"), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class DevelopmentDeliveryRow(Base):
    __tablename__ = "development_deliveries"
    __table_args__ = (UniqueConstraint("task_id", "ordinal"), CheckConstraint("ordinal >= 1", name="ordinal"))
    delivery_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("development_tasks.task_id", ondelete="RESTRICT"))
    context_id: Mapped[str] = mapped_column(String(36), ForeignKey("development_contexts.context_id", ondelete="RESTRICT"))
    change_id: Mapped[str] = mapped_column(String(36), ForeignKey("change_manifests.change_id", ondelete="RESTRICT"), unique=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)


class DevelopmentReceiptRow(Base):
    __tablename__ = "development_receipts"
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class DevelopmentCheckRunRow(Base):
    __tablename__ = "development_check_runs"
    __table_args__ = (Index("ix_development_check_runs_delivery", "delivery_id", "created_at_us"),)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.run_id", ondelete="RESTRICT"), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(36), ForeignKey("development_deliveries.delivery_id", ondelete="RESTRICT"))
    created_at_us: Mapped[int] = mapped_column(BigInteger)


class DevelopmentRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def _payload(self, value):
        ensure_storage_payload_safe(value.model_dump(mode="json"), self._secrets)
        encoded = value.model_dump_json()
        if len(encoded.encode("utf-8")) > 1_048_576:
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "开发任务记录超出大小限制")
        return encoded

    @staticmethod
    def _read(row, model):
        if row is None:
            return None
        try:
            value = model.model_validate_json(row.payload)
            for key in ("project_id", "task_id", "context_id", "delivery_id", "change_id", "version", "revision", "ordinal", "status", "kind", "operation_id"):
                if hasattr(row, key) and getattr(row, key) != getattr(value, key):
                    raise ValueError("development identity mismatch")
            return value
        except ValueError:
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "开发任务记录不完整") from None

    def task(self, project_id, task_id):
        row = self._session.scalar(select(DevelopmentTaskRow).where(
            DevelopmentTaskRow.project_id == project_id, DevelopmentTaskRow.task_id == task_id))
        return self._read(row, DevelopmentTask)

    def active(self, project_id):
        row = self._session.scalar(select(DevelopmentTaskRow).where(
            DevelopmentTaskRow.project_id == project_id, DevelopmentTaskRow.status == "ACTIVE"))
        return self._read(row, DevelopmentTask)

    def tasks(self, project_id, limit=50, *, before=None):
        query = select(DevelopmentTaskRow).where(DevelopmentTaskRow.project_id == project_id)
        if before is not None:
            query = query.where(or_(DevelopmentTaskRow.created_at_us < before.created_at_us,
                and_(DevelopmentTaskRow.created_at_us == before.created_at_us, DevelopmentTaskRow.task_id < before.task_id)))
        rows = self._session.scalars(query.order_by(DevelopmentTaskRow.created_at_us.desc(), DevelopmentTaskRow.task_id.desc()).limit(limit)).all()
        return tuple(self._read(row, DevelopmentTask) for row in rows)

    def add_task(self, value):
        self._session.add(DevelopmentTaskRow(task_id=value.task_id, project_id=value.project_id, status=value.status,
            version=value.version, revision=value.revision, created_at_us=value.created_at_us, payload=self._payload(value)))
        _flush(self._session)

    def replace_task(self, value, *, expected_version):
        if value.version != expected_version + 1:
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "任务版本必须连续递增")
        result = self._session.execute(update(DevelopmentTaskRow).where(DevelopmentTaskRow.task_id == value.task_id,
            DevelopmentTaskRow.project_id == value.project_id, DevelopmentTaskRow.version == expected_version)
            .values(status=value.status, version=value.version, revision=value.revision, payload=self._payload(value)))
        if result.rowcount != 1:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "任务已经变化，请读取当前版本")

    def context(self, project_id, context_id):
        row = self._session.scalar(select(DevelopmentContextRow).join(DevelopmentTaskRow)
            .where(DevelopmentTaskRow.project_id == project_id, DevelopmentContextRow.context_id == context_id))
        return self._read(row, DevelopmentContext)

    def add_context(self, value):
        self._session.add(DevelopmentContextRow(context_id=value.context_id, task_id=value.task_id,
            revision=value.revision, payload=self._payload(value)))
        _flush(self._session)

    def first_context(self, project_id, task_id):
        row = self._session.scalar(select(DevelopmentContextRow).join(DevelopmentTaskRow).where(
            DevelopmentTaskRow.project_id == project_id, DevelopmentContextRow.task_id == task_id,
            DevelopmentContextRow.revision == 1))
        return self._read(row, DevelopmentContext)

    def acceptance(self, project_id, context_id):
        if self.context(project_id, context_id) is None:
            return None
        return self._read(self._session.get(DevelopmentAcceptanceRow, context_id), DevelopmentAcceptance)

    def add_acceptance(self, value):
        self._session.add(DevelopmentAcceptanceRow(context_id=value.context_id, payload=self._payload(value)))
        _flush(self._session)

    def deliveries(self, project_id, task_id, limit=50, *, before_ordinal=None):
        if self.task(project_id, task_id) is None:
            return ()
        query = select(DevelopmentDeliveryRow).where(DevelopmentDeliveryRow.task_id == task_id)
        if before_ordinal is not None:
            query = query.where(DevelopmentDeliveryRow.ordinal < before_ordinal)
        rows = self._session.scalars(query.order_by(DevelopmentDeliveryRow.ordinal.desc()).limit(limit)).all()
        return tuple(self._read(row, DevelopmentDelivery) for row in rows)

    def add_delivery(self, value):
        self._session.add(DevelopmentDeliveryRow(delivery_id=value.delivery_id, task_id=value.task_id,
            context_id=value.context_id, change_id=value.change_id, ordinal=value.ordinal, payload=self._payload(value)))
        _flush(self._session)

    def delivery(self, project_id, delivery_id):
        row = self._session.scalar(select(DevelopmentDeliveryRow).join(DevelopmentTaskRow).where(
            DevelopmentTaskRow.project_id == project_id, DevelopmentDeliveryRow.delivery_id == delivery_id))
        return self._read(row, DevelopmentDelivery)

    def delivery_for_change(self, project_id, change_id):
        row = self._session.scalar(select(DevelopmentDeliveryRow).join(DevelopmentTaskRow).where(
            DevelopmentTaskRow.project_id == project_id, DevelopmentDeliveryRow.change_id == change_id))
        return self._read(row, DevelopmentDelivery)

    def add_check_run(self, delivery_id, run_id, created_at_us):
        self._session.add(DevelopmentCheckRunRow(delivery_id=delivery_id, run_id=run_id, created_at_us=created_at_us))
        _flush(self._session)

    def latest_check_run(self, project_id, delivery_id):
        if self.delivery(project_id, delivery_id) is None:
            return None
        return self._session.scalar(select(DevelopmentCheckRunRow.run_id)
            .where(DevelopmentCheckRunRow.delivery_id == delivery_id)
            .order_by(DevelopmentCheckRunRow.created_at_us.desc(), DevelopmentCheckRunRow.run_id.desc()).limit(1))

    def runtime_receipt(self, project_id, operation_id):
        row=self._session.get(DevelopmentReceiptRow,(project_id,'LOAD_RUNTIME',operation_id))
        model=NodeRuntimeActivationReceipt if row is not None and json.loads(row.payload).get('schema_version')=='2' else RuntimeActivationReceipt
        return self._read(row,model)

    def finish_runtime_receipt(self, before, value):
        if before.status != "PENDING" or (before.project_id, before.operation_id) != (value.project_id, value.operation_id):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "运行加载回执不能覆盖既有终态")
        result = self._session.execute(update(DevelopmentReceiptRow).where(
            DevelopmentReceiptRow.project_id == before.project_id, DevelopmentReceiptRow.kind == "LOAD_RUNTIME",
            DevelopmentReceiptRow.operation_id == before.operation_id, DevelopmentReceiptRow.payload == self._payload(before))
            .values(payload=self._payload(value)))
        if result.rowcount != 1:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "运行加载回执已经变化，请重新读取")

    def receipt(self, project_id, kind, operation_id):
        return self._read(self._session.get(DevelopmentReceiptRow, (project_id, kind, operation_id)), DevelopmentReceipt)

    def add_receipt(self, value):
        self._session.add(DevelopmentReceiptRow(project_id=value.project_id, kind=value.kind,
            operation_id=value.operation_id, payload=self._payload(value)))
        _flush(self._session)
