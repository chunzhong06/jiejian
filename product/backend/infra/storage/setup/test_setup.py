# =============================================================================
# 测试准备：动作安全事实持久化
#
# 定位
#   TestResource、ObservationBinding、RecoveryBinding 与 SQLite 关系记录之间的 Repository
#
# 职责
#   保存当前动作资源事实｜独立持久观察/恢复/效果确认｜按动作原子替换完整聚合
#
# 边界
#   只保存受限模板和非秘密事实；候选、浏览器状态和真实凭据不进入这些表。
#
# 调用链
#   ActionSafetySetupService → ActionSafetySetupRepository → SQLite
# =============================================================================

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.test_setup import (
    ActionSafetySetup,
    ObservationBinding,
    ObservationBindingKind,
    RecoveryBinding,
    RecoveryBindingKind,
    ResourceValueConsumer,
    SecurityEffectConfirmation,
    TestResource,
    TestResourceRelation,
)
from product.backend.core.verification.permissions import SecurityEffectKind
from product.backend.infra.storage.base import (
    Base,
    _canonical_json,
    _flush,
    _scalar,
    ensure_storage_payload_safe,
)


class TestResourceRow(Base):
    __tablename__ = "test_resources"
    __table_args__ = (
        CheckConstraint(
            "length(resource_id) = 36 AND resource_id GLOB 'trs_[0-9a-f]*'",
            name="test_resource_id_format",
        ),
        CheckConstraint("relation = 'OWNS'", name="test_resource_relation_value"),
        CheckConstraint(
            "consumer IN ('PATH', 'QUERY', 'JSON_BODY')",
            name="test_resource_consumer_value",
        ),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="test_resource_time_order",
        ),
        UniqueConstraint(
            "project_id",
            "action_candidate_id",
            name="uq_test_resource_project_action",
        ),
        Index("ix_test_resources_recording", "recording_id"),
    )

    resource_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    action_candidate_id: Mapped[str] = mapped_column(String(39), nullable=False)
    recording_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recordings.recording_id", ondelete="CASCADE"), nullable=False
    )
    flow_id: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actual_resource_id: Mapped[str] = mapped_column(String(256), nullable=False)
    owner_test_identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_identities.identity_id", ondelete="CASCADE"), nullable=False
    )
    owner_role_candidate_id: Mapped[str] = mapped_column(String(37), nullable=False)
    relation: Mapped[str] = mapped_column(String(16), nullable=False)
    consumer: Mapped[str] = mapped_column(String(16), nullable=False)
    location: Mapped[str] = mapped_column(String(512), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    understanding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    flow_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ObservationBindingRow(Base):
    __tablename__ = "observation_bindings"
    __table_args__ = (
        CheckConstraint(
            "length(observation_binding_id) = 36 "
            "AND observation_binding_id GLOB 'obs_[0-9a-f]*'",
            name="observation_binding_id_format",
        ),
        CheckConstraint(
            "kind = 'OWNER_READ' AND method = 'GET' AND required = 1",
            name="observation_binding_value",
        ),
        UniqueConstraint("resource_id", name="uq_observation_binding_resource"),
    )

    observation_binding_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_resources.resource_id", ondelete="CASCADE"), nullable=False
    )
    trusted_test_identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_identities.identity_id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    recording_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path_template: Mapped[str] = mapped_column(String(8192), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class RecoveryBindingRow(Base):
    __tablename__ = "recovery_bindings"
    __table_args__ = (
        CheckConstraint(
            "length(recovery_binding_id) = 36 "
            "AND recovery_binding_id GLOB 'rcv_[0-9a-f]*'",
            name="recovery_binding_id_format",
        ),
        CheckConstraint(
            "kind IN ('RECORDED_REQUEST', 'NOT_REQUIRED')",
            name="recovery_binding_kind_value",
        ),
        CheckConstraint(
            "(kind = 'NOT_REQUIRED' AND source_step_id IS NULL AND method IS NULL "
            "AND path_template IS NULL AND json_body_template = '{}') OR "
            "(kind = 'RECORDED_REQUEST' AND source_step_id IS NOT NULL "
            "AND method IN ('PATCH', 'POST', 'PUT', 'DELETE') "
            "AND path_template IS NOT NULL)",
            name="recovery_binding_request_shape",
        ),
        UniqueConstraint("resource_id", name="uq_recovery_binding_resource"),
    )

    recovery_binding_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_resources.resource_id", ondelete="CASCADE"), nullable=False
    )
    test_identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_identities.identity_id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    recording_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_step_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    path_template: Mapped[str | None] = mapped_column(String(8192), nullable=True)
    json_body_template: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SecurityEffectConfirmationRow(Base):
    __tablename__ = "security_effect_confirmations"
    __table_args__ = (
        CheckConstraint(
            "length(effect_confirmation_id) = 36 "
            "AND effect_confirmation_id GLOB 'efc_[0-9a-f]*'",
            name="effect_confirmation_id_format",
        ),
        UniqueConstraint("resource_id", name="uq_effect_confirmation_resource"),
    )

    effect_confirmation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_resources.resource_id", ondelete="CASCADE"), nullable=False
    )
    action_candidate_id: Mapped[str] = mapped_column(String(39), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    protected_fields: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ActionSafetySetupRepository:
    """把同一动作的四类已确认事实作为一个事务聚合读写。"""

    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def get_for_recording(self, recording_id: str) -> ActionSafetySetup | None:
        row = _scalar(
            self._session,
            select(TestResourceRow).where(TestResourceRow.recording_id == recording_id),
        )
        return None if row is None else self._record(row)

    def get_for_action(
        self,
        project_id: str,
        action_candidate_id: str,
    ) -> ActionSafetySetup | None:
        row = _scalar(
            self._session,
            select(TestResourceRow).where(
                TestResourceRow.project_id == project_id,
                TestResourceRow.action_candidate_id == action_candidate_id,
            ),
        )
        return None if row is None else self._record(row)

    def replace(self, setup: ActionSafetySetup) -> None:
        payload = setup.model_dump(mode="json")
        ensure_storage_payload_safe(payload, self._known_secrets)
        existing = _scalar(
            self._session,
            select(TestResourceRow).where(
                TestResourceRow.project_id == setup.resource.project_id,
                TestResourceRow.action_candidate_id
                == setup.resource.action_candidate_id,
            ),
        )
        # 子事实由数据库 CASCADE 精确删除；随后在同一事务中写入完整新聚合。
        if existing is not None:
            self._session.delete(existing)
            _flush(self._session)
        self._session.add(TestResourceRow(**setup.resource.model_dump(mode="json")))
        # 未声明 ORM relationship 时不能依赖一次 flush 自动推导父子插入顺序。
        _flush(self._session)
        if setup.observation is not None:
            self._session.add(
                ObservationBindingRow(**setup.observation.model_dump(mode="json"))
            )
        if setup.recovery is not None:
            values = setup.recovery.model_dump(mode="json")
            values["json_body_template"] = _canonical_json(
                setup.recovery.json_body_template
            )
            self._session.add(RecoveryBindingRow(**values))
        if setup.effect is not None:
            values = setup.effect.model_dump(mode="json")
            values["protected_fields"] = _canonical_json(
                list(setup.effect.protected_fields)
            )
            self._session.add(SecurityEffectConfirmationRow(**values))
        _flush(self._session)

    def _record(self, row: TestResourceRow) -> ActionSafetySetup:
        observation = _scalar(
            self._session,
            select(ObservationBindingRow).where(
                ObservationBindingRow.resource_id == row.resource_id
            ),
        )
        recovery = _scalar(
            self._session,
            select(RecoveryBindingRow).where(
                RecoveryBindingRow.resource_id == row.resource_id
            ),
        )
        effect = _scalar(
            self._session,
            select(SecurityEffectConfirmationRow).where(
                SecurityEffectConfirmationRow.resource_id == row.resource_id
            ),
        )
        return ActionSafetySetup(
            resource=TestResource(
                resource_id=row.resource_id,
                project_id=row.project_id,
                action_candidate_id=row.action_candidate_id,
                recording_id=row.recording_id,
                flow_id=row.flow_id,
                logical_name=row.logical_name,
                resource_type=row.resource_type,
                actual_resource_id=row.actual_resource_id,
                owner_test_identity_id=row.owner_test_identity_id,
                owner_role_candidate_id=row.owner_role_candidate_id,
                relation=TestResourceRelation(row.relation),
                consumer=ResourceValueConsumer(row.consumer),
                location=row.location,
                source_fingerprint=row.source_fingerprint,
                endpoint_source_fingerprint=row.endpoint_source_fingerprint,
                understanding_revision=row.understanding_revision,
                flow_sha256=row.flow_sha256,
                fingerprint=row.fingerprint,
                created_at_us=row.created_at_us,
                updated_at_us=row.updated_at_us,
            ),
            observation=(
                None
                if observation is None
                else ObservationBinding(
                    observation_binding_id=observation.observation_binding_id,
                    resource_id=observation.resource_id,
                    trusted_test_identity_id=observation.trusted_test_identity_id,
                    kind=ObservationBindingKind(observation.kind),
                    recording_id=observation.recording_id,
                    source_step_id=observation.source_step_id,
                    method="GET",
                    path_template=observation.path_template,
                    required=True,
                    fingerprint=observation.fingerprint,
                    confirmed_at_us=observation.confirmed_at_us,
                )
            ),
            recovery=(
                None
                if recovery is None
                else RecoveryBinding(
                    recovery_binding_id=recovery.recovery_binding_id,
                    resource_id=recovery.resource_id,
                    test_identity_id=recovery.test_identity_id,
                    kind=RecoveryBindingKind(recovery.kind),
                    recording_id=recovery.recording_id,
                    source_step_id=recovery.source_step_id,
                    method=recovery.method,
                    path_template=recovery.path_template,
                    json_body_template=json.loads(recovery.json_body_template),
                    fingerprint=recovery.fingerprint,
                    confirmed_at_us=recovery.confirmed_at_us,
                )
            ),
            effect=(
                None
                if effect is None
                else SecurityEffectConfirmation(
                    effect_confirmation_id=effect.effect_confirmation_id,
                    resource_id=effect.resource_id,
                    action_candidate_id=effect.action_candidate_id,
                    kind=SecurityEffectKind(effect.kind),
                    protected_fields=tuple(json.loads(effect.protected_fields)),
                    fingerprint=effect.fingerprint,
                    confirmed_at_us=effect.confirmed_at_us,
                )
            ),
        )


__all__ = [
    "ActionSafetySetupRepository",
    "ObservationBindingRow",
    "RecoveryBindingRow",
    "SecurityEffectConfirmationRow",
    "TestResourceRow",
]
