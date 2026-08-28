# =============================================================================
# 官方 Sample 产品体验
#
# 定位
#   官方 Sample 运行时与正式 ApplicationUnderstanding、TestIdentity、ProductStatus 之间的应用编排层
#
# 职责
#   建立活跃体验｜创建并确认正式应用连接｜按明确模式授权分析｜准备正式测试账号｜约束行为切换与停止
#
# 边界
#   不确认候选、不生成 Recording/Flow/PermissionIntent/Run，不返回秘密、源码绝对路径或预期结论。
#
# 调用链
#   Experience API → OfficialSampleExperience → official runtime + existing workflows
# =============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.test_identity import (
    TestIdentityAuthMethod,
    TestIdentityCookie,
)
from product.backend.infra.samples import OfficialSampleManager, OfficialSampleRuntime
from product.backend.infra.secrets import SecretStore, credential_ref
from product.backend.workflows.application_understanding.service import (
    ApplicationUnderstandingService,
)
from product.backend.workflows.control import ProductStatusService
from product.backend.workflows.security_setup.local_observer_registry import (
    LocalObserverEnvironmentRegistry,
)
from product.backend.workflows.test_identities import (
    PreparedLoginState,
    TestIdentityService,
    TestIdentityStatus,
)


class OfficialExperienceMode(StrEnum):
    GUIDED = "GUIDED"
    FULL = "FULL"


class OfficialExperienceView(BaseModel):
    """官方体验的非秘密公共状态。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    available: bool
    display_name: str
    unavailable_reason: str | None = None
    active: bool
    experience_id: str | None = Field(default=None, pattern=r"^exp_[0-9a-f]{32}$")
    experience_mode: OfficialExperienceMode | None = None
    project_id: str | None = None
    origin: str | None = None
    identities_ready: bool
    authorization_order: str | None = None
    blob_observation: str | None = None


@dataclass(slots=True)
class _Experience:
    runtime: OfficialSampleRuntime
    mode: OfficialExperienceMode
    project_id: str
    identities_ready: bool = False
    authorization_order: str = "ENQUEUE_BEFORE_AUTHORIZE"
    blob_observation: str = "AVAILABLE"
    active: bool = True


_IDENTITY_MAPPING = {
    "project_owner": (
        "alice",
        "Alice · 项目负责人",
        "JIEJIAN_SAMPLE_ALICE_SESSION",
    ),
    "member": ("bob", "Bob · 普通成员", "JIEJIAN_SAMPLE_BOB_SESSION"),
    "external_visitor": (
        "eve",
        "Eve · 外部访客",
        "JIEJIAN_SAMPLE_EVE_SESSION",
    ),
}


class OfficialSampleExperience:
    """维护当前 Core 中唯一活跃体验，不持久化第二套导览进度。"""

    def __init__(
        self,
        manager: OfficialSampleManager,
        application_understanding: ApplicationUnderstandingService,
        test_identities: TestIdentityService,
        secret_store: SecretStore,
        local_observer_environments: LocalObserverEnvironmentRegistry,
        product_status: ProductStatusService,
        *,
        clock_us=None,
    ) -> None:
        self._manager = manager
        self._application_understanding = application_understanding
        self._test_identities = test_identities
        self._secret_store = secret_store
        self._local_observer_environments = local_observer_environments
        self._product_status = product_status
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
        self._lock = RLock()
        self._current: _Experience | None = None

    def status(self) -> OfficialExperienceView:
        with self._lock:
            current = self._current
            runtime = self._manager.active
            if current is not None and runtime is None:
                self._local_observer_environments.unregister(
                    current.runtime.experience_id
                )
                current.active = False
            installation = self._manager.installation
            return OfficialExperienceView(
                available=installation.available,
                display_name=installation.display_name,
                unavailable_reason=installation.reason,
                active=bool(current and current.active and runtime is not None),
                experience_id=current.runtime.experience_id if current else None,
                experience_mode=current.mode if current else None,
                project_id=current.project_id if current else None,
                origin=current.runtime.origin if current else None,
                identities_ready=current.identities_ready if current else False,
                authorization_order=current.authorization_order if current else None,
                blob_observation=current.blob_observation if current else None,
            )

    def start(
        self,
        mode: OfficialExperienceMode,
        *,
        consent: bool,
    ) -> OfficialExperienceView:
        """在一次明确同意内建立机械运行事实；导览只额外授权并执行只读分析。"""

        if consent is not True:
            raise JiejianError(
                ErrorCode.STATE_OPERATOR_REQUIRED,
                "启动官方示例前需要明确同意本机运行与源码复制",
            )
        with self._lock:
            previous = self._current
            if previous is not None and previous.active:
                self._require_idle(previous.project_id)
                self._stop_current(previous)
            runtime = self._manager.start()
            try:
                connection = self._application_understanding.connect(
                    runtime.source_root,
                    project_name="协作空间",
                )
                understanding = self._application_understanding.confirm_endpoint(
                    connection.project.project_id,
                    endpoint=runtime.origin,
                    revision=connection.understanding.revision,
                )
                self._local_observer_environments.register(
                    experience_id=runtime.experience_id,
                    source_root=runtime.source_root,
                    confirmed_endpoint=runtime.origin,
                    descriptor_path=runtime.descriptor_path,
                )
                if mode is OfficialExperienceMode.GUIDED:
                    understanding = (
                        self._application_understanding.authorize_source_analysis(
                            connection.project.project_id,
                            revision=understanding.revision,
                        )
                    )
                    self._application_understanding.analyze_source(
                        connection.project.project_id,
                        revision=understanding.revision,
                    )
                self._current = _Experience(
                    runtime=runtime,
                    mode=mode,
                    project_id=connection.project.project_id,
                )
                return self.status()
            except Exception:
                self._local_observer_environments.unregister(runtime.experience_id)
                self._manager.stop(runtime.experience_id)
                raise

    def prepare_identities(self) -> OfficialExperienceView:
        """只为三个已由用户确认的角色创建正常 TestIdentity 与 Cookie 引用。"""

        with self._lock:
            current = self._require_active()
            understanding = self._application_understanding.get(current.project_id)
            roles = {
                item.canonical_key.casefold(): item
                for item in understanding.role_candidates
                if item.decision is CandidateDecision.CONFIRMED and not item.stale
            }
            if set(_IDENTITY_MAPPING) - set(roles):
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "请先确认协作空间的三个权限组候选",
                )
            existing = {
                item.role_canonical_key.casefold(): item
                for item in self._test_identities.list(current.project_id)
            }
            for role_key, (_account, label, session_name) in _IDENTITY_MAPPING.items():
                identity = existing.get(role_key)
                created = False
                if identity is None:
                    identity = self._test_identities.create(
                        current.project_id,
                        role_candidate_id=roles[role_key].candidate_id,
                        label=label,
                    )
                    created = True
                if identity.status is TestIdentityStatus.PREPARED:
                    continue
                session = current.runtime.secrets.get(session_name)
                if not session:
                    raise JiejianError(
                        ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
                        "官方示例会话材料当前不可用",
                    )
                secret_ref = credential_ref(
                    "test-identity",
                    current.project_id,
                    identity.identity_id,
                    "cookie-00",
                )
                wrote_secret = False
                try:
                    self._secret_store.write(secret_ref, session)
                    wrote_secret = True
                    self._test_identities.save_prepared_state(
                        identity.identity_id,
                        PreparedLoginState(
                            auth_method=TestIdentityAuthMethod.COOKIE_SESSION,
                            cookies=(
                                TestIdentityCookie(
                                    name="jiejian_sample_session",
                                    domain="127.0.0.1",
                                    path="/",
                                    secure=False,
                                    http_only=True,
                                    same_site="LAX",
                                    value_secret_ref=secret_ref,
                                ),
                            ),
                            prepared_at_us=self._clock_us(),
                        ),
                    )
                except Exception:
                    if wrote_secret:
                        try:
                            self._secret_store.delete(secret_ref)
                        except Exception:
                            pass
                    if created:
                        try:
                            self._test_identities.delete(identity.identity_id)
                        except Exception:
                            pass
                    raise
            current.identities_ready = all(
                item.status is TestIdentityStatus.PREPARED
                for item in self._test_identities.list(current.project_id)
                if item.role_canonical_key.casefold() in _IDENTITY_MAPPING
            )
            return self.status()

    def switch_behavior(
        self,
        *,
        authorization_order: str,
        blob_observation: str,
        verification_run_id: str | None = None,
    ) -> OfficialExperienceView:
        """切换被测应用自己的机械行为；不创建新 Run 或推断修复结果。"""

        with self._lock:
            current = self._require_active()
            self._require_idle(current.project_id)
            if verification_run_id is not None:
                status = self._product_status.get(current.project_id)
                latest = status.latest_result
                if (
                    current.mode is not OfficialExperienceMode.GUIDED
                    or latest is None
                    or latest.run_id != verification_run_id
                    or authorization_order != "AUTHORIZE_BEFORE_ENQUEUE"
                    or blob_observation != "AVAILABLE"
                ):
                    raise JiejianError(
                        ErrorCode.STATE_PRECONDITION,
                        "当前结果不允许进入修复行为验证",
                    )
            self._manager.switch_behavior(
                current.runtime.experience_id,
                authorization_order=authorization_order,
                blob_observation=blob_observation,
            )
            current.authorization_order = authorization_order
            current.blob_observation = blob_observation
            return self.status()

    def stop(self) -> OfficialExperienceView:
        with self._lock:
            current = self._current
            if current is not None and current.active:
                self._require_idle(current.project_id)
                self._stop_current(current)
            return self.status()

    def close(self) -> None:
        """应用关闭已先停止 Worker/Recording；此处强制回收其拥有的 Sample。"""

        with self._lock:
            current = self._current
            if current is not None and current.active:
                self._stop_current(current)

    def _require_active(self) -> _Experience:
        current = self._current
        if current is None or not current.active or self._manager.active is None:
            raise JiejianError(
                ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                "当前没有正在运行的官方示例体验",
            )
        return current

    def _require_idle(self, project_id: str) -> None:
        status = self._product_status.get(project_id)
        if status.readiness is not None and status.readiness.active_tasks:
            raise JiejianError(
                ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                "当前检查或业务流程尚未结束，不能切换官方示例",
            )

    def _stop_current(self, current: _Experience) -> None:
        self._local_observer_environments.unregister(current.runtime.experience_id)
        self._manager.stop(current.runtime.experience_id)
        current.active = False


__all__ = [
    "OfficialExperienceMode",
    "OfficialExperienceView",
    "OfficialSampleExperience",
]
