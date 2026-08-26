# =============================================================================
# 测试账号应用服务
#
# 定位
#   已确认应用角色、测试账号元数据与共享 SecretStore 之间的业务编排边界。
#
# 职责
#   创建和查询账号｜判定登录状态是否仍可用｜保存准备结果｜安全重置和删除。
#
# 边界
#   API 视图不暴露 secret_ref；删除秘密失败时不删除或清空数据库元数据。
#
# 调用链
#   API / GUI → TestIdentityService → UoW + SecretStore
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import (
    ApplicationUnderstanding,
    CandidateDecision,
    RoleCandidate,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.identifiers import PROJECT_ID_PATTERN, TEST_IDENTITY_ID_PATTERN
from product.backend.core.test_identity import (
    TestIdentity,
    TestIdentityAuthMethod,
    TestIdentityCookie,
)
from product.backend.infra.secrets.store import SecretStore
from product.backend.infra.storage import StorageUnitOfWork


class TestIdentityStatus(StrEnum):
    NOT_PREPARED = "NOT_PREPARED"
    PREPARED = "PREPARED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class _IdentityModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class PreparedLoginState(_IdentityModel):
    auth_method: TestIdentityAuthMethod
    cookies: tuple[TestIdentityCookie, ...] = Field(default=(), max_length=32)
    bearer_secret_ref: str | None = Field(default=None, max_length=512)
    prepared_at_us: int = Field(ge=0)


class TestIdentityView(_IdentityModel):
    identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    role_candidate_id: str
    role_canonical_key: str
    role_display_name: str
    label: str
    confirmed_endpoint: str
    auth_method: TestIdentityAuthMethod | None
    status: TestIdentityStatus
    review_reasons: tuple[str, ...] = ()
    cookie_count: int = Field(ge=0, le=32)
    prepared_at_us: int | None = Field(default=None, ge=0)
    refreshed_at_us: int | None = Field(default=None, ge=0)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)


class TestIdentityService:
    """以当前 ApplicationUnderstanding 作为测试账号可用性的唯一事实来源。"""

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
        role_candidate_id: str,
        label: str,
    ) -> TestIdentityView:
        clean_label = self._label(label)
        with self._uow_factory() as work:
            understanding = self._understanding(work, project_id)
            role = self._confirmed_role(understanding, role_candidate_id)
            now_us = self._clock_us()
            record = TestIdentity(
                identity_id=f"tid_{uuid4().hex}",
                project_id=project_id,
                role_candidate_id=role.candidate_id,
                role_canonical_key=role.canonical_key,
                role_display_name=role.display_name,
                label=clean_label,
                confirmed_endpoint=self._confirmed_endpoint(understanding),
                endpoint_source_fingerprint=self._endpoint_fingerprint(understanding),
                understanding_revision=understanding.revision,
                created_at_us=now_us,
                updated_at_us=now_us,
            )
            work.test_identities.add(record)
            work.commit()
        return self._view(record, understanding)

    def list(self, project_id: str) -> tuple[TestIdentityView, ...]:
        with self._uow_factory() as work:
            understanding = self._understanding(work, project_id)
            records = work.test_identities.list_for_project(project_id)
        return tuple(self._view(record, understanding) for record in records)

    def get(self, identity_id: str) -> TestIdentityView:
        record, understanding = self._load(identity_id)
        return self._view(record, understanding)

    def get_record(self, identity_id: str) -> TestIdentity:
        record, _ = self._load(identity_id)
        return record

    def save_prepared_state(
        self,
        identity_id: str,
        state: PreparedLoginState,
    ) -> TestIdentityView:
        with self._uow_factory() as work:
            current = work.test_identities.get(identity_id)
            if current is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
            understanding = self._understanding(work, current.project_id)
            reasons = self._review_reasons(current, understanding)
            if reasons:
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_READY,
                    "测试账号绑定的角色或运行地址已经变化，请重新确认后再准备",
                    details={"reasons": reasons},
                )
            if current.auth_method is not None:
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_CONFLICT,
                    "测试账号已有登录状态，请先重置后再重新准备",
                )
            expected_prefix = (
                f"cred:jiejian/test-identity/{current.project_id}/{identity_id}/"
            )
            refs = tuple(cookie.value_secret_ref for cookie in state.cookies)
            if state.bearer_secret_ref:
                refs += (state.bearer_secret_ref,)
            if not refs or any(not ref.startswith(expected_prefix) for ref in refs):
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_CONFLICT,
                    "登录状态秘密引用与测试账号不匹配",
                )
            try:
                missing = tuple(ref for ref in refs if not self._secret_store.configured(ref))
            except (JiejianError, OSError, RuntimeError, ValueError):
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_READY,
                    "无法确认测试账号登录状态，请检查 Windows 凭据管理器",
                ) from None
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
        return self._view(prepared, understanding)

    def reset(self, identity_id: str) -> TestIdentityView:
        with self._uow_factory() as work:
            current = work.test_identities.get(identity_id)
            if current is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
            understanding = self._understanding(work, current.project_id)
            self._delete_secrets(current)
            now_us = max(self._clock_us(), current.updated_at_us)
            role = next(
                (
                    item
                    for item in understanding.role_candidates
                    if item.candidate_id == current.role_candidate_id
                    and item.decision is CandidateDecision.CONFIRMED
                    and not item.stale
                ),
                None,
            )
            binding: dict[str, object] = {}
            if (
                role is not None
                and understanding.confirmed_endpoint
                and understanding.endpoint_source_fingerprint
            ):
                # 账号清空后才能把绑定推进到用户重新确认过的角色和 endpoint。
                binding = {
                    "role_canonical_key": role.canonical_key,
                    "role_display_name": role.display_name,
                    "confirmed_endpoint": understanding.confirmed_endpoint,
                    "endpoint_source_fingerprint": (
                        understanding.endpoint_source_fingerprint
                    ),
                    "understanding_revision": understanding.revision,
                }
            reset = TestIdentity(
                **(
                    current.model_dump()
                    | {
                        "auth_method": None,
                        "cookies": (),
                        "bearer_secret_ref": None,
                        "prepared_at_us": None,
                        "refreshed_at_us": None,
                        "updated_at_us": now_us,
                    }
                    | binding
                )
            )
            work.test_identities.replace(reset)
            work.commit()
        return self._view(reset, understanding)

    def delete(self, identity_id: str) -> None:
        with self._uow_factory() as work:
            current = work.test_identities.get(identity_id)
            if current is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
            self._delete_secrets(current)
            work.test_identities.delete(identity_id)
            work.commit()

    def _load(self, identity_id: str) -> tuple[TestIdentity, ApplicationUnderstanding]:
        with self._uow_factory() as work:
            record = work.test_identities.get(identity_id)
            if record is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
            understanding = self._understanding(work, record.project_id)
        return record, understanding

    def _view(
        self,
        record: TestIdentity,
        understanding: ApplicationUnderstanding,
    ) -> TestIdentityView:
        reasons = self._review_reasons(record, understanding)
        secret_missing = False
        if record.auth_method is not None and not reasons:
            try:
                secret_missing = any(
                    not self._secret_store.configured(ref) for ref in record.secret_refs
                )
            except (JiejianError, OSError, RuntimeError, ValueError):
                secret_missing = True
            if secret_missing:
                reasons += ("SECRET_STATE_UNAVAILABLE",)
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
            role_candidate_id=record.role_candidate_id,
            role_canonical_key=record.role_canonical_key,
            role_display_name=record.role_display_name,
            label=record.label,
            confirmed_endpoint=record.confirmed_endpoint,
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
    def _review_reasons(
        record: TestIdentity,
        understanding: ApplicationUnderstanding,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if (
            understanding.confirmed_endpoint != record.confirmed_endpoint
            or understanding.endpoint_source_fingerprint
            != record.endpoint_source_fingerprint
        ):
            reasons.append("ENDPOINT_CHANGED")
        role = next(
            (
                item
                for item in understanding.role_candidates
                if item.candidate_id == record.role_candidate_id
            ),
            None,
        )
        if role is None:
            reasons.append("ROLE_MISSING")
        elif (
            role.decision is not CandidateDecision.CONFIRMED
            or role.stale
            or role.canonical_key != record.role_canonical_key
        ):
            reasons.append("ROLE_NEEDS_REVIEW")
        return tuple(reasons)

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
    def _understanding(
        work: StorageUnitOfWork,
        project_id: str,
    ) -> ApplicationUnderstanding:
        understanding = work.application_understanding.get(project_id)
        if understanding is None:
            raise JiejianError(
                ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                "应用理解记录不存在",
            )
        return understanding

    @staticmethod
    def _confirmed_role(
        understanding: ApplicationUnderstanding,
        role_candidate_id: str,
    ) -> RoleCandidate:
        role = next(
            (
                item
                for item in understanding.role_candidates
                if item.candidate_id == role_candidate_id
            ),
            None,
        )
        if role is None:
            raise JiejianError(
                ErrorCode.APPLICATION_CANDIDATE_NOT_FOUND,
                "角色候选不存在",
            )
        if role.decision is not CandidateDecision.CONFIRMED or role.stale:
            raise JiejianError(
                ErrorCode.APPLICATION_CANDIDATE_CONFLICT,
                "只能为当前已确认角色添加测试账号",
            )
        return role

    @staticmethod
    def _confirmed_endpoint(understanding: ApplicationUnderstanding) -> str:
        if not understanding.confirmed_endpoint:
            raise JiejianError(
                ErrorCode.APPLICATION_ENDPOINT_INVALID,
                "请先确认应用运行地址",
            )
        return understanding.confirmed_endpoint

    @staticmethod
    def _endpoint_fingerprint(understanding: ApplicationUnderstanding) -> str:
        if not understanding.endpoint_source_fingerprint:
            raise JiejianError(
                ErrorCode.APPLICATION_ENDPOINT_INVALID,
                "应用运行地址缺少来源指纹",
            )
        return understanding.endpoint_source_fingerprint

    @staticmethod
    def _label(value: str) -> str:
        if not isinstance(value, str):
            raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "测试账号名称无效")
        clean = value.strip()
        if not clean or len(clean) > 128 or any(ord(char) < 32 for char in clean):
            raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "测试账号名称无效")
        return clean
