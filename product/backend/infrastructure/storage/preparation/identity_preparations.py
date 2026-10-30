# 持久登录操作与账号认证代次；不保存登录秘密或第二份 Job 生命周期。
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Index, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.infrastructure.storage.base import Base, _flush, ensure_storage_payload_safe


class IdentityPreparationRow(Base):
    __tablename__ = 'identity_preparations'
    __table_args__ = (
        Index('ix_identity_preparations_identity', 'identity_id', 'created_at_us'),
        Index('ix_identity_preparations_project', 'project_id', 'created_at_us'),
        CheckConstraint('authentication_generation >= 0', name='generation_nonnegative'),
    )
    preparation_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('projects.project_id'), nullable=False)
    identity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    operation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    authentication_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    official_account: Mapped[str | None] = mapped_column(String(16))
    save_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # phase 记录浏览器控制及清理阶段；任务是否成功、取消或仍占有租约以关联 Job 为准。
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class IdentityPreparationRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def get(self, preparation_id):
        row = self._session.get(IdentityPreparationRow, preparation_id)
        return None if row is None else self._value(row)

    def list(self, *, project_id=None, identity_id=None, limit=64):
        query = select(IdentityPreparationRow)
        if project_id is not None:
            query = query.where(IdentityPreparationRow.project_id == project_id)
        if identity_id is not None:
            query = query.where(IdentityPreparationRow.identity_id == identity_id)
        return tuple(self._value(row) for row in self._session.scalars(query.order_by(
            IdentityPreparationRow.created_at_us.desc(), IdentityPreparationRow.preparation_id.desc()).limit(limit)))

    def add(self, value):
        ensure_storage_payload_safe(value, self._secrets)
        self._session.add(IdentityPreparationRow(**value))
        _flush(self._session)

    def update(self, preparation_id, *, phase=None, error_code=None, save_requested=None, now_us):
        row = self._session.get(IdentityPreparationRow, preparation_id)
        if row is None:
            return None
        if phase is not None:
            row.phase = phase
        if error_code is not None:
            row.error_code = error_code
        if save_requested is not None:
            # 保存意图一经确认便保持成立，迟到的控制面更新不能把它撤回为 False。
            row.save_requested = row.save_requested or save_requested
        row.updated_at_us = max(row.updated_at_us, now_us)
        _flush(self._session)
        return self._value(row)

    @staticmethod
    def _value(row):
        return {column.name: getattr(row, column.name) for column in IdentityPreparationRow.__table__.columns}
