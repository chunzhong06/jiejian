# =============================================================================
# 官方 Sample 产品体验
#
# 定位
#   官方 Sample 运行时、场景合同与正式 ApplicationUnderstanding、PermissionIntent、检查链之间的编排层
#
# 职责
#   建立问题版体验｜一键应用样例合同｜切换证据受限与修复行为｜把所有代码改动接入权威变化链｜约束停止
#
# 边界
#   场景配方只生成正式检查输入，不生成 Run 或 Verdict；切换按钮只改变真实行为，不能直接写入安全结论。
#
# 调用链
#   Experience API → OfficialSampleExperience → official runtime + existing workflows
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import PermissionIntentRelation
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
from product.backend.workflows.official_scenario import (
    EXPORT_ACTION_KEY,
    SAMPLE_RESOURCE_ID,
    VIEW_ACTION_KEY,
    OfficialScenarioInstaller,
)
from product.backend.workflows.permission_intents import PermissionIntentService
from product.backend.workflows.projects.preparation import ProjectPreparationService
from product.backend.workflows.recording.safety_setup import (
    ActionSafetySetupService,
    ConfirmActionSafetySetup,
)
from product.backend.workflows.results.repair import RepairContractService
from product.backend.workflows.source_changes import SourceChangeService
from product.backend.workflows.security_setup.local_observer_registry import (
    LocalObserverEnvironmentRegistry,
)
from product.backend.workflows.test_identities import (
    PreparedLoginState,
    TestIdentityService,
    TestIdentityStatus,
)
from product.backend.core.verification.permissions import PermissionExpectation


class OfficialScenarioVersion(StrEnum):
    VULNERABLE = "VULNERABLE"
    EVIDENCE_LIMITED = "EVIDENCE_LIMITED"
    FIXED = "FIXED"


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
    project_id: str | None = None
    origin: str | None = None
    scenario_prepared: bool
    scenario_version: OfficialScenarioVersion | None = None
    scenario_changed_at_us: int | None = Field(default=None, ge=0)
    vulnerable_change_id: str | None = Field(default=None, pattern=r"^chg_[0-9a-f]{32}$")
    repair_change_id: str | None = Field(default=None, pattern=r"^chg_[0-9a-f]{32}$")


@dataclass(slots=True)
class _Experience:
    runtime: OfficialSampleRuntime
    project_id: str
    scenario_prepared: bool = False
    scenario_version: OfficialScenarioVersion = OfficialScenarioVersion.VULNERABLE
    scenario_changed_at_us: int = 0
    active: bool = True
    vulnerable_change_id: str | None = None
    repair_change_id: str | None = None


_IDENTITY_MAPPING = {
    "project_owner": (
        "alice",
        "Alice · 项目负责人",
        "JIEJIAN_SAMPLE_ALICE_SESSION",
    ),
    "member": ("bob", "Bob · 普通成员", "JIEJIAN_SAMPLE_BOB_SESSION"),
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
        scenario_installer: OfficialScenarioInstaller,
        action_safety_setup: ActionSafetySetupService,
        permission_intents: PermissionIntentService,
        project_preparation: ProjectPreparationService,
        repair_contracts: RepairContractService,
        source_changes: SourceChangeService,
        archive_project: Callable[[str], object] | None = None,
        clock_us=None,
    ) -> None:
        self._manager = manager
        self._application_understanding = application_understanding
        self._test_identities = test_identities
        self._secret_store = secret_store
        self._local_observer_environments = local_observer_environments
        self._product_status = product_status
        self._scenario_installer = scenario_installer
        self._action_safety_setup = action_safety_setup
        self._permission_intents = permission_intents
        self._project_preparation = project_preparation
        self._repair_contracts = repair_contracts
        self._source_changes = source_changes
        self._archive_project = archive_project or (lambda _project_id: None)
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
                project_id=current.project_id if current else None,
                origin=current.runtime.origin if current else None,
                scenario_prepared=current.scenario_prepared if current else False,
                scenario_version=current.scenario_version if current else None,
                scenario_changed_at_us=current.scenario_changed_at_us if current else None,
                vulnerable_change_id=current.vulnerable_change_id if current else None,
                repair_change_id=current.repair_change_id if current else None,
            )

    def start(
        self,
        *,
        consent: bool,
    ) -> OfficialExperienceView:
        """先建立安全源码基线，再让运行中的样例进入 Agent 写错的问题版。"""

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
                self._archive_project(previous.project_id)
            runtime = self._manager.start(
                authorization_order="AUTHORIZE_BEFORE_ENQUEUE",
                owner_observation="AVAILABLE",
                blob_observation="AVAILABLE",
            )
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
                understanding = self._application_understanding.authorize_source_analysis(
                    connection.project.project_id,
                    revision=understanding.revision,
                )
                self._application_understanding.analyze_source(
                    connection.project.project_id,
                    revision=understanding.revision,
                )
                self._current = _Experience(
                    runtime=runtime,
                    project_id=connection.project.project_id,
                )
                self._manager.switch_behavior(
                    runtime.experience_id,
                    authorization_order="ENQUEUE_BEFORE_AUTHORIZE",
                    owner_observation="AVAILABLE",
                    blob_observation="AVAILABLE",
                )
                self._current.scenario_changed_at_us = self._clock_us()
                return self.status()
            except Exception:
                self._local_observer_environments.unregister(runtime.experience_id)
                self._manager.stop(runtime.experience_id)
                raise

    def prepare(self) -> OfficialExperienceView:
        """一键应用固定样例合同；每项仍经正式理解、身份、Flow、安全准备与 Human Approval 服务。"""

        with self._lock:
            current = self._require_active()
            if current.scenario_prepared:
                return self.status()
            understanding = self._confirm_scenario_candidates(current.project_id)
            roles = {
                item.canonical_key.casefold(): item
                for item in understanding.role_candidates
                if item.decision is CandidateDecision.CONFIRMED and not item.stale
            }
            actions = {
                item.canonical_key: item
                for item in understanding.action_candidates
                if item.decision is CandidateDecision.CONFIRMED and not item.stale
            }
            if set(_IDENTITY_MAPPING) - set(roles) or {EXPORT_ACTION_KEY, VIEW_ACTION_KEY} - set(actions):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "官方样例角色或业务动作不完整")
            identities = self._prepare_scenario_identities(current, roles)
            export_recording, view_recording = self._scenario_installer.install(
                project_id=current.project_id,
                endpoint=current.runtime.origin,
                export_action_id=actions[EXPORT_ACTION_KEY].candidate_id,
                view_action_id=actions[VIEW_ACTION_KEY].candidate_id,
                owner_identity_id=identities["project_owner"].identity_id,
            )
            self._confirm_scenario_safety(export_recording, view_recording)
            self._confirm_scenario_permissions(
                current.project_id,
                roles=roles,
                actions=actions,
            )
            manifest, _, _ = self._source_changes.submit(
                current.project_id,
                reason="Vibe Coding Agent 为缩短导出等待，把后台任务创建提前到权限判断之前",
                submitted_by="MCP · Codex",
            )
            current.vulnerable_change_id = manifest.change_id
            self._complete_safe_preparation(current.project_id)
            current.scenario_prepared = True
            return self.status()

    def _prepare_scenario_identities(self, current: _Experience, roles: dict[str, object]) -> dict[str, object]:
        """准备样例的 Alice/Bob 会话引用；秘密仍只进入 SecretStore。"""

        existing = {
            item.role_canonical_key.casefold(): item
            for item in self._test_identities.list(current.project_id)
        }
        prepared: dict[str, object] = {}
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
                prepared[role_key] = identity
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
            prepared[role_key] = self._test_identities.get(identity.identity_id)
        return prepared

    def _confirm_scenario_candidates(self, project_id: str):
        """把官方设计稿中的角色与动作逐项提交给既有候选决定服务。"""

        understanding = self._application_understanding.get(project_id)
        role_labels = {"project_owner": "项目负责人", "member": "普通成员"}
        action_labels = {
            EXPORT_ACTION_KEY: "导出完整项目交付包",
            VIEW_ACTION_KEY: "查看日常协作资料",
        }
        for candidate in understanding.role_candidates:
            decision = CandidateDecision.CONFIRMED if candidate.canonical_key.casefold() in role_labels else CandidateDecision.REJECTED
            understanding = self._application_understanding.decide_role(
                project_id,
                candidate.candidate_id,
                revision=understanding.revision,
                decision=decision,
                display_name=role_labels.get(candidate.canonical_key.casefold(), candidate.display_name),
            )
        for candidate in understanding.action_candidates:
            decision = CandidateDecision.CONFIRMED if candidate.canonical_key in action_labels else CandidateDecision.REJECTED
            understanding = self._application_understanding.decide_action(
                project_id,
                candidate.candidate_id,
                revision=understanding.revision,
                decision=decision,
                display_name=action_labels.get(candidate.canonical_key, candidate.display_name),
            )
        return understanding

    def _confirm_scenario_safety(self, export_recording: str, view_recording: str) -> None:
        """用官方合同明确选择资源、独立观察和恢复候选，不能从名称推断安全结论。"""

        export = self._action_safety_setup.preview(export_recording)
        export_resource = next(item for item in export.resource_candidates if item.actual_resource_id == SAMPLE_RESOURCE_ID)
        export_observation = next(item for item in export.observation_candidates if item.method == "GET")
        export_recovery = next(item for item in export.recovery_candidates if item.method == "DELETE")
        self._action_safety_setup.confirm(
            export_recording,
            ConfirmActionSafetySetup(
                resource_candidate_id=export_resource.candidate_id,
                logical_name="校园数字展馆完整项目交付包",
                resource_type="项目资料包",
                observation_candidate_id=export_observation.candidate_id,
                recovery_candidate_id=export_recovery.candidate_id,
            ),
        )
        view = self._action_safety_setup.preview(view_recording)
        view_resource = next(item for item in view.resource_candidates if item.actual_resource_id == "collaboration")
        view_observation = next(item for item in view.observation_candidates if item.method == "GET")
        self._action_safety_setup.confirm(
            view_recording,
            ConfirmActionSafetySetup(
                resource_candidate_id=view_resource.candidate_id,
                logical_name="校园数字展馆日常协作资料",
                resource_type="项目",
                observation_candidate_id=view_observation.candidate_id,
            ),
        )

    def _confirm_scenario_permissions(self, project_id: str, *, roles: dict[str, object], actions: dict[str, object]) -> None:
        """应用三条公开样例规则；批准理由明确说明它们来自固定样例设计。"""

        owner_id = roles["project_owner"].candidate_id
        for action_key, subject_id, relation, expectation in (
            (EXPORT_ACTION_KEY, owner_id, PermissionIntentRelation.OWNS, PermissionExpectation.ALLOW),
            (EXPORT_ACTION_KEY, roles["member"].candidate_id, PermissionIntentRelation.OTHER_ROLE, PermissionExpectation.DENY),
            (VIEW_ACTION_KEY, roles["member"].candidate_id, PermissionIntentRelation.OTHER_ROLE, PermissionExpectation.ALLOW),
        ):
            self._permission_intents.confirm(
                project_id,
                actions[action_key].candidate_id,
                subject_id,
                owner_id,
                relation,
                expectation=expectation,
                reason="应用官方样例公开设计合同",
            )

    def switch_version(
        self,
        *,
        version: OfficialScenarioVersion,
        source_run_id: str | None = None,
    ) -> OfficialExperienceView:
        """切换真实代码或观察能力；结论必须由用户随后发起的新 Run 形成。"""

        with self._lock:
            current = self._require_active()
            self._require_idle(current.project_id)
            if not current.scenario_prepared:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先应用官方样例配置")
            authorization_order = "AUTHORIZE_BEFORE_ENQUEUE" if version is OfficialScenarioVersion.FIXED else "ENQUEUE_BEFORE_AUTHORIZE"
            owner_observation = "UNAVAILABLE" if version is OfficialScenarioVersion.EVIDENCE_LIMITED else "AVAILABLE"
            blob_observation = "UNAVAILABLE" if version is OfficialScenarioVersion.EVIDENCE_LIMITED else "AVAILABLE"
            if version is OfficialScenarioVersion.FIXED:
                if source_run_id is None:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "修复版需要引用先前的 BLOCK 检查")
                repair_contract = self._repair_contracts.for_run(source_run_id)
                if repair_contract.project_id != current.project_id:
                    raise JiejianError(
                        ErrorCode.STATE_PRECONDITION,
                        "当前修复要求不属于官方示例应用",
                    )
            else:
                repair_contract = None
            previous_version = current.scenario_version
            self._manager.switch_behavior(
                current.runtime.experience_id,
                authorization_order=authorization_order,
                owner_observation=owner_observation,
                blob_observation=blob_observation,
            )
            try:
                code_changed = (previous_version is OfficialScenarioVersion.FIXED) != (version is OfficialScenarioVersion.FIXED)
                if repair_contract is not None:
                    manifest, _, _ = self._source_changes.submit(
                        current.project_id,
                        reason="Codex 按界鉴修复合同把权限判断移动到后台任务创建之前",
                        submitted_by="MCP · Codex",
                        repair_reference=repair_contract.reference,
                    )
                    current.repair_change_id = manifest.change_id
                elif code_changed:
                    manifest, _, _ = self._source_changes.submit(
                        current.project_id,
                        reason="Vibe Coding Agent 再次把后台任务创建提前到权限判断之前",
                        submitted_by="MCP · Codex",
                    )
                    current.vulnerable_change_id = manifest.change_id
                    current.repair_change_id = None
            except Exception:
                self._manager.switch_behavior(
                    current.runtime.experience_id,
                    authorization_order=("AUTHORIZE_BEFORE_ENQUEUE" if previous_version is OfficialScenarioVersion.FIXED else "ENQUEUE_BEFORE_AUTHORIZE"),
                    owner_observation=("UNAVAILABLE" if previous_version is OfficialScenarioVersion.EVIDENCE_LIMITED else "AVAILABLE"),
                    blob_observation=("UNAVAILABLE" if previous_version is OfficialScenarioVersion.EVIDENCE_LIMITED else "AVAILABLE"),
                )
                raise
            current.scenario_version = version
            # 版本切换本身不形成结论；时间边界让前端只把随后完成的正式 Run 归到当前版本。
            current.scenario_changed_at_us = self._clock_us()
            self._complete_safe_preparation(current.project_id)
            return self.status()

    def _complete_safe_preparation(self, project_id: str) -> None:
        """只连续执行后端标记为 AUTO 的机械动作；任何用户判断缺口都立即停止。"""

        for _ in range(6):
            preparation = self._project_preparation.status(project_id)
            if preparation.ready:
                return
            next_item = next(
                (item for item in preparation.items if item.key == preparation.next_item_key),
                None,
            )
            if next_item is None or next_item.status.value != "AUTO":
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "官方样例配置存在需要用户判断的缺口",
                )
            self._project_preparation.prepare_safe(project_id)
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "官方样例检查条件尚未准备完成")

    def stop(self) -> OfficialExperienceView:
        with self._lock:
            current = self._current
            if current is not None and current.active:
                self._require_idle(current.project_id)
                self._stop_current(current)
                # 官方示例是一次性体验。运行目录回收后同步归档其正式 Project，
                # 避免下次启动留下一个已失效、仍可见的“协作空间”。
                self._archive_project(current.project_id)
            return self.status()

    def stop_project(self, project_id: str) -> bool:
        """结束属于指定 Project 的空闲体验；不匹配时保持幂等。"""

        with self._lock:
            current = self._current
            if current is None or not current.active or current.project_id != project_id:
                return False
            self._require_idle(project_id)
            self._stop_current(current)
            return True

    def close(self) -> None:
        """应用关闭已先停止 Worker/Recording；回收 Sample 并归档一次性 Project。"""

        with self._lock:
            current = self._current
            if current is not None and current.active:
                self._stop_current(current)
                self._archive_project(current.project_id)

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
    "OfficialExperienceView",
    "OfficialScenarioVersion",
    "OfficialSampleExperience",
]
