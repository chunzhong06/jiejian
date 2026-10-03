# 官方环境操作的持久回执；历史索引不恢复进程、临时秘密或执行能力。
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.infra.storage.base import Base, _flush, ensure_storage_payload_safe


class EnvironmentOperationRow(Base):
    __tablename__ = "environment_operations"
    __table_args__ = (
        CheckConstraint("operation IN ('start','reset','stop')", name="operation"),
        CheckConstraint("state IN ('PENDING','SUCCEEDED','FAILED','UNKNOWN')", name="state"),
        CheckConstraint("started_at_us >= 0 AND (finished_at_us IS NULL OR finished_at_us >= started_at_us)", name="time_order"),
    )
    operation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operation: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(16))
    started_at_us: Mapped[int] = mapped_column(BigInteger)
    finished_at_us: Mapped[int | None] = mapped_column(BigInteger)
    experience_id: Mapped[str | None] = mapped_column(String(36))
    project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"))
    error_code: Mapped[str | None] = mapped_column(String(64))
    cleanup_confirmed: Mapped[bool] = mapped_column(Boolean)


class EnvironmentOperationRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def get(self, operation_id):
        row = self._session.get(EnvironmentOperationRow, operation_id)
        return None if row is None else self._value(row)

    def save(self, value):
        ensure_storage_payload_safe(value, self._secrets)
        row = self._session.get(EnvironmentOperationRow, value["operation_id"])
        if row is None:
            self._session.add(EnvironmentOperationRow(**value))
        else:
            for key, item in value.items():
                setattr(row, key, item)
        _flush(self._session)

    def list(self, limit=25):
        values = [self._value(row) for row in self._session.scalars(select(EnvironmentOperationRow).order_by(
            EnvironmentOperationRow.started_at_us.desc(), EnvironmentOperationRow.operation_id.desc()).limit(limit + 1))]
        return values[:limit], len(values) > limit

    @staticmethod
    def _value(row):
        return {column.name: getattr(row, column.name) for column in EnvironmentOperationRow.__table__.columns}
