# 测试账号应用服务
# 以稳定 BusinessActor revision 创建和读取账号，并安全保存、重置或删除受控登录状态。
# 不读取 Candidate/endpoint/source binding；API 视图不返回 secret_ref 或秘密正文。

from __future__ import annotations
from contextlib import nullcontext

import time
import hashlib
import re
from collections.abc import Callable
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from product.backend.domain.boundaries.entities import BusinessActorRevision, BusinessRevisionState
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.identifiers import PROJECT_ID_PATTERN, TEST_IDENTITY_ID_PATTERN
from product.backend.domain.identities.models import TestIdentity, TestIdentityAuthMethod, TestIdentityCookie
from product.backend.infrastructure.secrets.store import SecretStore
from product.backend.infrastructure.storage import StorageUnitOfWork


class TestIdentityStatus(StrEnum):
    NOT_PREPARED = "NOT_PREPARED"
    PREPARED = "PREPARED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class _IdentityModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class PreparedLoginState(_IdentityModel):
    # 内部采用输入只携带 SecretStore 引用；页面使用不含引用的 TestIdentityView。
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
        operation_id: str | None = None,
    ) -> TestIdentityView:
        # 同一项目内，同一操作标识只允许同一角色修订和标签；同角色仍可有多个真实账号。
        clean_label = self._label(label)
        identity_id = self._operation_identity(project_id, operation_id) if operation_id else f"tid_{uuid4().hex}"
        with self._uow_factory() as work:
            work.acquire_write_lock()
            actor = self._active_actor(work, project_id, actor_id, actor_revision)
            prior = work.test_identities.get(identity_id)
            if prior is not None:
                if (prior.project_id, prior.actor_id, prior.actor_revision, prior.label) != (project_id, actor_id, actor_revision, clean_label):
                    raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "这个账号请求已用于其他内容")
                return self._view(prior, actor)
            now_us = self._clock_us()
            record = TestIdentity(
                identity_id=identity_id,
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

    @staticmethod
    def _operation_identity(project_id: str, operation_id: str) -> str:
        if re.fullmatch(r'[0-9a-f]{32}', operation_id) is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, '账号操作标识无效')
        return 'tid_' + hashlib.sha256(f'{project_id}:{operation_id}'.encode()).hexdigest()[:32]

    def created(self, project_id: str, operation_id: str) -> TestIdentityView | None:
        with self._uow_factory() as work:
            record = work.test_identities.get(self._operation_identity(project_id, operation_id))
            return None if record is None else self._view(record, self._actor_for_record(work, record))

    def list(self, project_id: str, *, work=None) -> tuple[TestIdentityView, ...]:
        with (self._uow_factory() if work is None else nullcontext(work)) as work:
            records = work.test_identities.list_for_project(project_id)
            actors = tuple(self._actor_for_record(work, record) for record in records)
        return tuple(self._view(record, actor) for record, actor in zip(records, actors, strict=True))

    def get(self, identity_id: str, *, work=None) -> TestIdentityView:
        if work is not None:
            record = work.test_identities.get(identity_id)
            if record is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, '测试账号不存在')
            return self._view(record, self._actor_for_record(work, record))
        record, actor = self._load(identity_id)
        return self._view(record, actor)

    def get_record(self, identity_id: str) -> TestIdentity:
        # 供运行时凭据解析和清理使用；返回记录含受控引用，不应直接成为 HTTP 响应。
        record, _ = self._load(identity_id)
        return record

    def save_prepared_state(self, identity_id: str, state: PreparedLoginState, *, work=None) -> TestIdentityView:
        # 注入 work 时由外层提交，用于将账号状态与登录 Job 的完成纳入同一事务。
        # SecretStore 写入发生在此之前，此处核对引用归属与存在性，不复制秘密值。
        if work is not None:
            return self._save_prepared_state(work, identity_id, state)
        with self._uow_factory() as owned:
            value = self._save_prepared_state(owned, identity_id, state)
            owned.commit()
            return value

    def _save_prepared_state(self, work, identity_id, state):
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
        return self._view(prepared, actor)

    def reset(self, identity_id: str) -> TestIdentityView:
        # 先拒绝活动或未清理的准备任务，再删除已知引用；不得让迟到结果复活刚重置的会话。
        with self._uow_factory() as work:
            work.acquire_write_lock()
            self._require_preparation_closed(work, identity_id)
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
            work.acquire_write_lock()
            self._require_preparation_closed(work, identity_id)
            current = work.test_identities.get(identity_id)
            if current is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
            # 先在未提交事务中验证数据库删除；约束拒绝时不能提前破坏仍在使用的登录状态。
            work.test_identities.delete(identity_id)
            self._delete_secrets(current)
            work.commit()

    @staticmethod
    def _require_preparation_closed(work, identity_id):
        # Job 终态不等于凭据清理完成，CLEANUP_REQUIRED 同样阻止账号重置或删除。
        from product.backend.domain.lifecycle import JobState
        for row in work.identity_preparations.list(identity_id=identity_id, limit=1):
            job = work.jobs.get(row['job_id'])
            if job is not None and job.state in {JobState.PENDING, JobState.RUNNING, JobState.RETRY_WAIT}:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '请先取消当前登录并等待清理完成')
            if row['phase'] == 'CLEANUP_REQUIRED':
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '上次登录仍需完成清理，账号暂时保留')

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
