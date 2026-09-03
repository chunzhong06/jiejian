# =============================================================================
# 测试账号应用服务
#
# 职责
#   以稳定 BusinessActor revision 创建和读取账号，并安全保存、重置或删除受控登录状态。
#
# 边界
#   不读取 Candidate/endpoint/source binding；API 视图不返回 secret_ref 或秘密正文。
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.business_boundary import BusinessActorRevision, BusinessRevisionState
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.identifiers import PROJECT_ID_PATTERN, TEST_IDENTITY_ID_PATTERN
from product.backend.core.test_identity import TestIdentity, TestIdentityAuthMethod, TestIdentityCookie
from product.backend.infra.secrets.store import SecretStore
from product.backend.infra.storage import StorageUnitOfWork


class TestIdentityStatus(StrEnum):
    NOT_PREPARED = "NOT_PREPARED"
    PREPARED = "PREPARED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class _IdentityModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class PreparedLoginState(_IdentityModel):
    auth_method: TestIdentityAuthMethod
    cookies: tuple[TestIdentityCookie, ...] = Field(default=(), max_length=32)
    bearer_secret_ref: str | None = Field(default=None, max_length=512)
    prepared_at_us: int = Field(ge=0)


class TestIdentityView(_IdentityModel):
    identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    actor_id: str
    actor_revision: int = Field(ge=1)
    actor_display_name: str
    label: str
    auth_method: TestIdentityAuthMethod | None
    status: TestIdentityStatus
    review_reasons: tuple[str, ...] = ()
    cookie_count: int = Field(ge=0, le=32)
    prepared_at_us: int | None = Field(default=None, ge=0)
    refreshed_at_us: int | None = Field(default=None, ge=0)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)


class TestIdentityService:
    """TestIdentity 始终冻结创建时选择的 Actor revision，不随 binding 漂移。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        secret_store: SecretStore,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._secret_store = secret_store
        self._clock_us = clock_us or (lambda: time.time_ns() // 1000)

    def create(
        self,
        project_id: str,
        *,
        actor_id: str,
        actor_revision: int,
        label: str,
    ) -> TestIdentityView:
        clean_label = self._label(label)
        with self._uow_factory() as work:
            actor = self._active_actor(work, project_id, actor_id, actor_revision)
            now_us = self._clock_us()
            record = TestIdentity(
                identity_id=f"tid_{uuid4().hex}",
                project_id=project_id,
                actor_id=actor_id,
                actor_revision=actor_revision,
                label=clean_label,
                created_at_us=now_us,
                updated_at_us=now_us,
            )
            work.test_identities.add(record)
            work.commit()
        return self._view(record, actor)

    def list(self, project_id: str) -> tuple[TestIdentityView, ...]:
        with self._uow_factory() as work:
            records = work.test_identities.list_for_project(project_id)
            actors = tuple(self._actor_for_record(work, record) for record in records)
        return tuple(self._view(record, actor) for record, actor in zip(records, actors, strict=True))

    def get(self, identity_id: str) -> TestIdentityView:
        record, actor = self._load(identity_id)
        return self._view(record, actor)

    def get_record(self, identity_id: str) -> TestIdentity:
        record, _ = self._load(identity_id)
        return record

    def save_prepared_state(self, identity_id: str, state: PreparedLoginState) -> TestIdentityView:
        with self._uow_factory() as work:
            current = work.test_identities.get(identity_id)
            if current is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
            actor = self._actor_for_record(work, current)
            if current.auth_method is not None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "测试账号已有登录状态，请先重置")
            refs = tuple(cookie.value_secret_ref for cookie in state.cookies)
            if state.bearer_secret_ref:
                refs += (state.bearer_secret_ref,)
            expected_prefix = f"cred:jiejian/test-identity/{current.project_id}/{identity_id}/"
            if not refs or any(not ref.startswith(expected_prefix) for ref in refs):
                raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "登录状态秘密引用与测试账号不匹配")
            try:
                missing = tuple(ref for ref in refs if not self._secret_store.configured(ref))
            except (JiejianError, OSError, RuntimeError, ValueError):
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "无法确认测试账号登录状态") from None
            if missing:
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_READY,
                    "测试账号登录状态尚未完整写入安全存储",
                    details={"missing_count": len(missing)},
                )
            prepared = TestIdentity(
                **(
                    current.model_dump()
                    | {
                        "auth_method": state.auth_method,
                        "cookies": state.cookies,
                        "bearer_secret_ref": state.bearer_secret_ref,
                        "prepared_at_us": state.prepared_at_us,
                        "refreshed_at_us": state.prepared_at_us,
                        "updated_at_us": max(self._clock_us(), state.prepared_at_us),
                    }
                )
            )
            work.test_identities.replace(prepared)
            work.commit()
        return self._view(prepared, actor)

    def reset(self, identity_id: str) -> TestIdentityView:
        with self._uow_factory() as work:
            current = work.test_identities.get(identity_id)
            if current is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
            actor = self._actor_for_record(work, current)
            self._delete_secrets(current)
            reset = TestIdentity(
                **(
                    current.model_dump()
                    | {
                        "auth_method": None,
                        "cookies": (),
                        "bearer_secret_ref": None,
                        "prepared_at_us": None,
                        "refreshed_at_us": None,
                        "updated_at_us": max(self._clock_us(), current.updated_at_us),
                    }
                )
            )
            work.test_identities.replace(reset)
            work.commit()
        return self._view(reset, actor)

    def delete(self, identity_id: str) -> None:
        with self._uow_factory() as work:
            current = work.test_identities.get(identity_id)
            if current is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
            self._delete_secrets(current)
            work.test_identities.delete(identity_id)
            work.commit()

    def remove_project_credentials(self, project_id: str) -> int:
        with self._uow_factory() as work:
            records = work.test_identities.list_for_project(project_id)
        for record in records:
            self._delete_secrets(record)
        return len(records)

    def _load(self, identity_id: str) -> tuple[TestIdentity, BusinessActorRevision]:
        with self._uow_factory() as work:
            record = work.test_identities.get(identity_id)
            if record is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
            actor = self._actor_for_record(work, record)
        return record, actor

    def _view(self, record: TestIdentity, actor: BusinessActorRevision) -> TestIdentityView:
        reasons: tuple[str, ...] = ()
        if record.auth_method is not None:
            try:
                if any(not self._secret_store.configured(ref) for ref in record.secret_refs):
                    reasons = ("SECRET_STATE_UNAVAILABLE",)
            except (JiejianError, OSError, RuntimeError, ValueError):
                reasons = ("SECRET_STATE_UNAVAILABLE",)
        status = (
            TestIdentityStatus.NEEDS_REVIEW
            if reasons
            else TestIdentityStatus.PREPARED
            if record.auth_method is not None
            else TestIdentityStatus.NOT_PREPARED
        )
        return TestIdentityView(
            identity_id=record.identity_id,
            project_id=record.project_id,
            actor_id=record.actor_id,
            actor_revision=record.actor_revision,
            actor_display_name=actor.display_name,
            label=record.label,
            auth_method=record.auth_method,
            status=status,
            review_reasons=reasons,
            cookie_count=len(record.cookies),
            prepared_at_us=record.prepared_at_us,
            refreshed_at_us=record.refreshed_at_us,
            created_at_us=record.created_at_us,
            updated_at_us=record.updated_at_us,
        )

    @staticmethod
    def _active_actor(
        work: StorageUnitOfWork,
        project_id: str,
        actor_id: str,
        revision: int,
    ) -> BusinessActorRevision:
        actor = work.business_boundaries.actor_revision(actor_id, revision)
        if actor is None or actor.project_id != project_id:
            raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "测试账号业务主体不存在或不属于当前项目")
        if actor.effective_state is not BusinessRevisionState.ACTIVE:
            raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "只能为 ACTIVE 业务主体创建测试账号")
        return actor

    @staticmethod
    def _actor_for_record(work: StorageUnitOfWork, record: TestIdentity) -> BusinessActorRevision:
        actor = work.business_boundaries.actor_revision(record.actor_id, record.actor_revision)
        if actor is None or actor.project_id != record.project_id:
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "测试账号引用的业务主体数据损坏")
        return actor

    def _delete_secrets(self, record: TestIdentity) -> None:
        try:
            for secret_ref in record.secret_refs:
                self._secret_store.delete(secret_ref)
        except (JiejianError, OSError, RuntimeError, ValueError):
            raise JiejianError(
                ErrorCode.TEST_IDENTITY_SECRET_CLEANUP,
                "测试账号登录状态清理失败，账号信息已保留，可稍后重试",
                details={"identity_id": record.identity_id},
            ) from None

    @staticmethod
    def _label(value: str) -> str:
        if not isinstance(value, str):
            raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "测试账号名称无效")
        clean = value.strip()
        if not clean or len(clean) > 128 or any(ord(char) < 32 for char in clean):
            raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "测试账号名称无效")
        return clean


__all__ = ["PreparedLoginState", "TestIdentityService", "TestIdentityStatus", "TestIdentityView"]
