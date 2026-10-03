# 不可变代码观察及精确变化/Run 关联；只保存授权源码范围的非秘密身份元数据。
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import Base, _flush, ensure_storage_payload_safe


class CodeObservationRow(Base):
    __tablename__ = "code_observations"
    __table_args__ = (
        CheckConstraint("length(source_fingerprint) = 64 AND observed_at_us >= 0", name="identity_bound"),
        CheckConstraint("git_status IN ('AVAILABLE','UNBORN','NOT_A_REPOSITORY','UNAVAILABLE')", name="git_status"),
        CheckConstraint("consistency IN ('CONSISTENT','UNAVAILABLE') AND scope = 'AUTHORIZED_SOURCE_SCAN'", name="scope"),
        CheckConstraint("head IS NULL OR length(head) IN (40,64)", name="head_length"),
        CheckConstraint("consistency != 'UNAVAILABLE' OR (git_status = 'UNAVAILABLE' AND head IS NULL AND has_local_changes IS NULL)", name="unknown_identity"),
    )
    observation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    observed_at_us: Mapped[int] = mapped_column(BigInteger)
    git_status: Mapped[str] = mapped_column(String(32))
    head: Mapped[str | None] = mapped_column(String(64))
    has_local_changes: Mapped[bool | None] = mapped_column(Boolean)
    consistency: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(32))


class ChangeCodeObservationRow(Base):
    __tablename__ = "change_code_observations"
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True)
    change_id: Mapped[str] = mapped_column(String(36), ForeignKey("change_manifests.change_id", ondelete="RESTRICT"), primary_key=True)
    observation_id: Mapped[str] = mapped_column(String(36), ForeignKey("code_observations.observation_id", ondelete="RESTRICT"), unique=True)


class RunCodeObservationRow(Base):
    __tablename__ = "run_code_observations"
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.run_id", ondelete="RESTRICT"), primary_key=True)
    observation_id: Mapped[str] = mapped_column(String(36), ForeignKey("code_observations.observation_id", ondelete="RESTRICT"), unique=True)


class CodeObservationRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def add_link(self, value, *, kind, target_id, project_id, source_fingerprint):
        # 调用者在同一 UoW 重核正式目标；仓储再次核验观察不能跨项目或指纹。
        if value["project_id"] != project_id or value["source_fingerprint"] != source_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "代码观察关联不一致")
        # 字符串 SQL 只含固定表名；不通过 peer Row import 登记其他聚合。
        if kind == "run":
            actual = self._session.execute(text("SELECT project_id,source_fingerprint FROM runs WHERE run_id=:id"), {"id": target_id}).first()
        elif kind == "change":
            actual = self._session.execute(text("SELECT c.project_id,s.source_fingerprint FROM source_change_sets c JOIN source_revision_snapshots s ON s.snapshot_id=c.current_snapshot_id WHERE c.change_id=:id"), {"id": target_id}).first()
        else:
            raise ValueError("unknown observation relation")
        if actual is None or tuple(actual) != (project_id, source_fingerprint):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "代码观察目标不一致")
        ensure_storage_payload_safe(value, self._secrets)
        self._session.add(CodeObservationRow(**value))
        _flush(self._session)
        row, key = self._relation(kind)
        self._session.add(row(project_id=project_id, observation_id=value["observation_id"], **{key: target_id}))
        _flush(self._session)

    def for_target(self, project_id, kind, target_id):
        row, key = self._relation(kind)
        link = self._session.get(row, (project_id, target_id))
        if link is None:
            return None
        observation = self._session.get(CodeObservationRow, link.observation_id)
        return {column.name: getattr(observation, column.name) for column in CodeObservationRow.__table__.columns}

    @staticmethod
    def _relation(kind):
        if kind == "change":
            return ChangeCodeObservationRow, "change_id"
        if kind == "run":
            return RunCodeObservationRow, "run_id"
        raise ValueError("unknown observation relation")
