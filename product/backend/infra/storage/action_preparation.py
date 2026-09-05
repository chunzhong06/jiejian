# 动作技术准备聚合：关系字段保存来源，嵌套模板只保存受限 JSON；仓储不计算实时状态。

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, PrimaryKeyConstraint, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.action_preparation import (
    ActionEvidenceBinding, ActionExecutionBinding, ActionRecoveryBinding, ActionResourceBinding,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import Base, _canonical_json, _flush, _scalar, _scalars, ensure_storage_payload_safe


def _binding_constraints(*, recorded: bool = True):
    constraints = (
        ForeignKeyConstraint(
            ["business_action_id", "action_revision"],
            ["business_action_revisions.action_id", "business_action_revisions.revision"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("action_revision >= 1 AND confirmed_at_us >= 0", name="revision_time_bounds"),
        CheckConstraint(
            "length(binding_fingerprint) = 64 AND binding_fingerprint NOT GLOB '*[^0-9a-f]*'",
            name="binding_fingerprint_format",
        ),
    )
    if recorded:
        constraints += (
            ForeignKeyConstraint(
                ["source_recording_id", "source_draft_revision"],
                ["flow_draft_revisions.recording_id", "flow_draft_revisions.revision"],
                ondelete="RESTRICT",
            ),
        )
    return constraints


class _BindingColumns:
    business_action_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    action_revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False)
    action_semantic_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    implementation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    endpoint_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # 身份 ID 是历史来源，写入时验证真实账号，删除账号后由现场检查判定失效。
    test_identity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    identity_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    binding_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class _RecordedColumns:
    source_recording_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_draft_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class ActionExecutionBindingRow(_BindingColumns, _RecordedColumns, Base):
    __tablename__ = "action_execution_bindings"
    __table_args__ = _binding_constraints()
    flow_id: Mapped[str] = mapped_column(String(64), nullable=False)
    flow_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_injection_json: Mapped[str] = mapped_column(Text, nullable=False)


class ActionResourceBindingRow(_BindingColumns, _RecordedColumns, Base):
    __tablename__ = "action_resource_bindings"
    __table_args__ = _binding_constraints() + (
        PrimaryKeyConstraint("business_action_id", "action_revision", "owner_test_identity_id"),
        CheckConstraint("owner_test_identity_id = test_identity_id", name="owner_identity_match"),
        CheckConstraint("length(actual_resource_id) BETWEEN 1 AND 256", name="resource_value_bound"),
    )
    owner_test_identity_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actual_resource_id: Mapped[str] = mapped_column(String(256), nullable=False)
    flow_id: Mapped[str] = mapped_column(String(64), nullable=False)
    flow_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_injection_json: Mapped[str] = mapped_column(Text, nullable=False)


class ActionEvidenceBindingRow(_BindingColumns, Base):
    __tablename__ = "action_evidence_bindings"
    __table_args__ = _binding_constraints() + (
        PrimaryKeyConstraint("business_action_id", "action_revision", "effect_id"),
        CheckConstraint(
            "(kind = 'RECORDED_OBSERVATION' AND source_recording_id IS NOT NULL "
            "AND source_draft_revision IS NOT NULL AND source_draft_sha256 IS NOT NULL "
            "AND step_id IS NOT NULL AND request_template_json IS NOT NULL AND observer_reference_json IS NULL) OR "
            "(kind = 'REGISTERED_OBSERVER' AND source_recording_id IS NULL "
            "AND source_draft_revision IS NULL AND source_draft_sha256 IS NULL "
            "AND step_id IS NULL AND request_template_json IS NULL AND observer_reference_json IS NOT NULL)",
            name="evidence_source_matrix",
        ),
    )
    effect_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_recording_id: Mapped[str | None] = mapped_column(String(36))
    source_draft_revision: Mapped[int | None] = mapped_column(Integer)
    source_draft_sha256: Mapped[str | None] = mapped_column(String(64))
    step_id: Mapped[str | None] = mapped_column(String(64))
    request_template_json: Mapped[str | None] = mapped_column(Text)
    observer_reference_json: Mapped[str | None] = mapped_column(Text)


class ActionRecoveryBindingRow(_BindingColumns, _RecordedColumns, Base):
    __tablename__ = "action_recovery_bindings"
    __table_args__ = _binding_constraints()
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_template_json: Mapped[str] = mapped_column(Text, nullable=False)


_ROWS = {
    ActionExecutionBinding: ActionExecutionBindingRow,
    ActionResourceBinding: ActionResourceBindingRow,
    ActionEvidenceBinding: ActionEvidenceBindingRow,
    ActionRecoveryBinding: ActionRecoveryBindingRow,
}
_JSON_FIELDS = frozenset({"resource_injection", "request_template", "observer_reference"})


class ActionPreparationRepository:
    """仅替换同一动作版本的指定技术资产；其他账号、效果和业务历史保持不变。"""

    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def replace(self, binding) -> None:
        row_type = _ROWS.get(type(binding))
        if row_type is None:
            raise TypeError("unsupported action preparation binding")
        payload = binding.model_dump(mode="json")
        ensure_storage_payload_safe(payload, self._known_secrets)
        # 拒绝未经严格构造的 model_copy/model_construct 旁路对象。
        type(binding).model_validate_json(_canonical_json(payload), strict=True)
        values = {
            key + "_json" if key in _JSON_FIELDS else key:
            _canonical_json(value) if key in _JSON_FIELDS and value is not None else value
            for key, value in payload.items()
        }
        conditions = [getattr(row_type, key.name) == values[key.name] for key in row_type.__table__.primary_key]
        row = _scalar(self._session, select(row_type).where(*conditions))
        if row is None:
            self._session.add(row_type(**values))
        else:
            if row.project_id != binding.project_id:
                raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "技术绑定所属应用不可更换")
            for key, value in values.items():
                setattr(row, key, value)
        _flush(self._session)

    def execution(self, action_id: str, revision: int) -> ActionExecutionBinding | None:
        return self._one(ActionExecutionBinding, action_id, revision)

    def resource(self, action_id: str, revision: int, owner_id: str) -> ActionResourceBinding | None:
        return self._one(ActionResourceBinding, action_id, revision, owner_test_identity_id=owner_id)

    def resources(self, action_id: str, revision: int) -> tuple[ActionResourceBinding, ...]:
        return self._many(ActionResourceBinding, action_id, revision, "owner_test_identity_id")

    def evidence(self, action_id: str, revision: int, effect_id: str) -> ActionEvidenceBinding | None:
        return self._one(ActionEvidenceBinding, action_id, revision, effect_id=effect_id)

    def recovery(self, action_id: str, revision: int) -> ActionRecoveryBinding | None:
        return self._one(ActionRecoveryBinding, action_id, revision)

    def _one(self, model_type, action_id: str, revision: int, **keys):
        row_type = _ROWS[model_type]
        row = _scalar(self._session, select(row_type).where(
            row_type.business_action_id == action_id, row_type.action_revision == revision,
            *(getattr(row_type, key) == value for key, value in keys.items()),
        ))
        return None if row is None else self._record(model_type, row)

    def _many(self, model_type, action_id: str, revision: int, order: str):
        row_type = _ROWS[model_type]
        rows = _scalars(self._session, select(row_type).where(
            row_type.business_action_id == action_id, row_type.action_revision == revision,
        ).order_by(getattr(row_type, order)))
        return tuple(self._record(model_type, row) for row in rows)

    @staticmethod
    def _record(model_type, row):
        payload = {}
        try:
            for key in model_type.model_fields:
                value = getattr(row, key + "_json" if key in _JSON_FIELDS else key)
                payload[key] = json.loads(value) if key in _JSON_FIELDS and value is not None else value
            return model_type.model_validate_json(_canonical_json(payload), strict=True)
        except ValueError:
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "技术绑定的持久来源无效") from None


__all__ = ["ActionPreparationRepository"]
