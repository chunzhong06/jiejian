# =============================================================================
# 录制动作安全准备服务
#
# 定位
#   已确认 Flow 与确定性编译之间的人工确认应用服务
#
# 职责
#   从受限 Recording 生成候选｜分别确认资源/观察/恢复/效果｜计算自动执行安全缺口
#
# 边界
#   不执行目标请求，不接受任意 URL/脚本/JSONPath；候选没有用户确认前不形成事实。
#
# 调用链
#   Recording API / GUI → ActionSafetySetupService → Core facts / Storage
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import (
    ActionCandidate,
    ApplicationUnderstanding,
    CandidateDecision,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.core.test_setup import (
    ActionSafetySetup,
    ObservationBinding,
    RecoveryBinding,
    RecoveryBindingKind,
    ResourceValueConsumer,
    SecurityEffectConfirmation,
    TestResource,
    test_setup_sha256,
)
from product.backend.core.verification.permissions import SecurityEffectKind
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.storage import RecordingRecord, StorageUnitOfWork
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.test_identities import (
    TestIdentityService,
    TestIdentityStatus,
    TestIdentityView,
)
from product.protocols import FlowDraft, FlowDraftResourceCandidate, FlowDraftStep
from product.protocols.recording import RecordingEvent
from product.protocols.recording_flow import Flow

_MUTATING_METHODS = frozenset({"PATCH", "POST", "PUT", "DELETE"})
_SUCCESS_MIN = 200
_SUCCESS_MAX = 299


class SafetySetupModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class TestResourceCandidateView(SafetySetupModel):
    candidate_id: str = Field(pattern=r"^trc_[0-9a-f]{32}$")
    label: str = Field(min_length=1, max_length=128)
    suggested_resource_type: str = Field(min_length=1, max_length=128)
    actual_resource_id: str = Field(min_length=1, max_length=256)
    consumer: ResourceValueConsumer
    location: str = Field(min_length=1, max_length=512)


class ObservationCandidateView(SafetySetupModel):
    candidate_id: str = Field(pattern=r"^obc_[0-9a-f]{32}$")
    label: str = Field(min_length=1, max_length=256)
    source_recording_id: str
    source_step_id: str
    method: str
    path_template: str
    trusted_test_identity_id: str


class RecoveryCandidateView(SafetySetupModel):
    candidate_id: str = Field(pattern=r"^rcc_[0-9a-f]{32}$")
    label: str = Field(min_length=1, max_length=256)
    source_recording_id: str
    source_step_id: str
    method: str
    path_template: str
    json_body_template: dict[str, Any] = Field(default_factory=dict)
    test_identity_id: str


class SecurityEffectCandidateView(SafetySetupModel):
    candidate_id: str = Field(pattern=r"^sfc_[0-9a-f]{32}$")
    kind: SecurityEffectKind
    label: str = Field(min_length=1, max_length=128)
    protected_fields: tuple[str, ...] = ()


class ConfirmActionSafetySetup(SafetySetupModel):
    resource_candidate_id: str | None = Field(default=None, pattern=r"^trc_[0-9a-f]{32}$")
    logical_name: str | None = Field(default=None, min_length=1, max_length=128)
    resource_type: str | None = Field(default=None, min_length=1, max_length=128)
    observation_candidate_id: str | None = Field(
        default=None,
        pattern=r"^obc_[0-9a-f]{32}$",
    )
    recovery_candidate_id: str | None = Field(
        default=None,
        pattern=r"^rcc_[0-9a-f]{32}$",
    )


class ActionSafetySetupView(SafetySetupModel):
    recording_id: str
    action_candidate_id: str
    action_display_name: str
    target_method: str
    recording_identity: TestIdentityView
    state_changing: bool
    resource_candidates: tuple[TestResourceCandidateView, ...]
    observation_candidates: tuple[ObservationCandidateView, ...]
    recovery_candidates: tuple[RecoveryCandidateView, ...]
    security_effect_candidates: tuple[SecurityEffectCandidateView, ...]
    business_result: str | None = None
    observation_status: str
    recovery_status: str
    ready: bool
    confirmed_setup: ActionSafetySetup | None = None
    gaps: tuple[str, ...] = ()
    automatic_execution_allowed: bool = False


@dataclass(frozen=True, slots=True)
class _SetupContext:
    recording: RecordingRecord
    draft: FlowDraft
    flow: Flow
    flow_sha256: str
    understanding: ApplicationUnderstanding
    action: ActionCandidate
    recording_identity: TestIdentityView
    target_step: FlowDraftStep
    target_event: RecordingEvent
    resource_candidate: FlowDraftResourceCandidate
    resource_value: str
    existing: ActionSafetySetup | None
    supplements: tuple[tuple[RecordingRecord, FlowDraft], ...] = ()


@dataclass(frozen=True, slots=True)
class _RequestTemplate:
    path: str
    json_body: dict[str, Any]


from .safety_candidates import (
    _binding_candidates,
    _effect_candidates,
    _json_sha256,
    _json_value,
    _pick,
    _pick_optional,
    _request_event,
    _resource_candidate_view,
    _resource_value,
    _required_endpoint_fingerprint,
    _setup_is_current,
    _state_changing,
    _suggest_resource_type,
)


class ActionSafetySetupService:
    """只把当前录制中的有限候选转成可追溯、可失效的已确认事实。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        var_dir: Path,
        request_store: RecordingRequestStore,
        test_identities: TestIdentityService,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._var_dir = var_dir.resolve()
        self._request_store = request_store
        self._test_identities = test_identities
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
        self._permission_binding_refresher: Callable[[str], None] | None = None

    def set_permission_binding_refresher(
        self,
        refresher: Callable[[str], None],
    ) -> None:
        """安装安全准备变化后的权限实现绑定失效器。"""

        self._permission_binding_refresher = refresher

    def preview(self, recording_id: str) -> ActionSafetySetupView:
        context = self._load_context(recording_id)
        return self._view(context)

    def confirm(
        self,
        recording_id: str,
        command: ConfirmActionSafetySetup,
    ) -> ActionSafetySetupView:
        """按候选 ID 确认事实；缺少观察或恢复时允许保存，但安全门保持关闭。"""

        context = self._load_context(recording_id)
        view = self._view(context)
        resource_candidate_id = command.resource_candidate_id or (
            view.resource_candidates[0].candidate_id if len(view.resource_candidates) == 1 else None
        )
        if resource_candidate_id is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, "需要确认这次操作影响的业务对象")
        resource_candidate = _pick(view.resource_candidates, resource_candidate_id, "测试资源候选已经失效")
        observation_candidate_id = command.observation_candidate_id or (
            view.observation_candidates[0].candidate_id if len(view.observation_candidates) == 1 else None
        )
        recovery_candidate_id = command.recovery_candidate_id or (
            view.recovery_candidates[0].candidate_id if len(view.recovery_candidates) == 1 else None
        )
        observation_candidate = _pick_optional(
            view.observation_candidates,
            observation_candidate_id,
            "观察候选已经失效",
        )
        recovery_candidate = _pick_optional(
            view.recovery_candidates,
            recovery_candidate_id,
            "恢复候选已经失效",
        )
        effect_candidate = view.security_effect_candidates[0] if len(view.security_effect_candidates) == 1 else None
        now_us = self._clock_us()
        resource = self._resource_fact(
            context,
            resource_candidate,
            logical_name=command.logical_name or f"{context.action.display_name}测试对象",
            resource_type=command.resource_type or resource_candidate.suggested_resource_type,
            now_us=now_us,
        )
        setup = ActionSafetySetup(
            resource=resource,
            observation=(
                None
                if observation_candidate is None
                else self._observation_fact(
                    resource,
                    observation_candidate,
                    now_us=now_us,
                )
            ),
            recovery=self._recovery_fact(
                resource,
                recovery_candidate,
                confirm_not_required=not view.state_changing,
                now_us=now_us,
            ),
            effect=(
                None
                if effect_candidate is None
                else self._effect_fact(resource, effect_candidate, now_us=now_us)
            ),
        )
        with self._uow_factory() as work:
            work.action_safety_setups.replace(setup)
            work.commit()
        if self._permission_binding_refresher is not None:
            self._permission_binding_refresher(context.recording.project_id)
        return self._view(self._load_context(recording_id))

    def _load_context(self, recording_id: str) -> _SetupContext:
        with self._uow_factory() as work:
            recording = work.recordings.get(recording_id)
            draft_record = work.flow_drafts.latest(recording_id)
            job = work.jobs.get_by_recording(recording_id)
            if recording is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "录制对象不存在")
            if (
                recording.state is not RecordingState.COMPLETED
                or draft_record is None
                or job is None
            ):
                raise JiejianError(
                    ErrorCode.RECORD_STATE_PRECONDITION,
                    "请先完成并保存业务流程",
                )
            understanding = work.application_understanding.get(recording.project_id)
            if understanding is None:
                raise JiejianError(
                    ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                    "应用理解事实不存在",
                )
            existing = work.action_safety_setups.get_for_action(
                recording.project_id,
                draft_record.draft.action_candidate_id,
            )
            supplements = tuple(
                (item, supplement_draft.draft)
                for item in work.recordings.list_for_project(recording.project_id)
                if item.parent_recording_id == recording.recording_id
                and item.purpose in {RecordingPurpose.OBSERVATION, RecordingPurpose.RECOVERY}
                and item.state is RecordingState.COMPLETED
                and (supplement_draft := work.flow_drafts.latest(item.recording_id)) is not None
            )
        request = self._request_store.load(
            job.job_id,
            expected_hash=job.request_hash,
        )
        identity_id = request.sessions[0].test_identity_id
        identity = self._test_identities.get(identity_id)
        if identity.status is not TestIdentityStatus.PREPARED:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "录制账号需要重新准备")
        if not understanding.source_fingerprint:
            raise JiejianError(
                ErrorCode.APPLICATION_ANALYSIS_NOT_AUTHORIZED,
                "请先完成当前源码分析并确认业务动作",
            )
        action = next(
            (
                item
                for item in understanding.action_candidates
                if item.candidate_id == draft_record.draft.action_candidate_id
                and item.decision is CandidateDecision.CONFIRMED
                and not item.stale
            ),
            None,
        )
        if action is None:
            raise JiejianError(
                ErrorCode.APPLICATION_CANDIDATE_CONFLICT,
                "业务动作已经变化，请重新录制",
            )
        draft = draft_record.draft
        target_step = next(
            (item for item in draft.steps if item.id == draft.target_step_id),
            None,
        )
        resource_candidate = next(
            (
                candidate
                for candidate in target_step.resource_candidates
                if candidate.candidate_id == draft.resource_candidate_id
            ),
            None,
        ) if target_step is not None else None
        if target_step is None or target_step.method is None or resource_candidate is None:
            raise JiejianError(ErrorCode.RECORD_DRAFT_UNCONFIRMED, "流程缺少已确认目标或资源")
        target_event = _request_event(recording, target_step)
        resource_value = _resource_value(target_event, resource_candidate)
        # 通过领域模型的同一校验器拒绝 URL、脚本、超长值或疑似秘密。
        probe_payload = {
            "project_id": recording.project_id,
            "action_candidate_id": action.candidate_id,
            "recording_id": recording.recording_id,
            "flow_id": recording.flow_id,
            "logical_name": "待确认测试资源",
            "resource_type": _suggest_resource_type(target_event, resource_candidate),
            "actual_resource_id": resource_value,
            "owner_test_identity_id": identity.identity_id,
            "owner_role_candidate_id": identity.role_candidate_id,
            "consumer": ResourceValueConsumer(resource_candidate.consumer.value),
            "location": resource_candidate.location,
            "source_fingerprint": understanding.source_fingerprint,
            "endpoint_source_fingerprint": _required_endpoint_fingerprint(understanding),
            "understanding_revision": understanding.revision,
            "flow_sha256": "0" * 64,
        }
        probe_fingerprint = test_setup_sha256("test_resource", probe_payload)
        TestResource(
            resource_id=f"trs_{probe_fingerprint[:32]}",
            fingerprint=probe_fingerprint,
            created_at_us=0,
            updated_at_us=0,
            **probe_payload,
        )
        flow_path = RecordingLifecycle.flow_path(self._var_dir, recording)
        flow = RecordingLifecycle.load_final_flow(flow_path)
        flow_sha256 = _json_sha256(flow.model_dump(mode="json"))
        return _SetupContext(
            recording=recording,
            draft=draft,
            flow=flow,
            flow_sha256=flow_sha256,
            understanding=understanding,
            action=action,
            recording_identity=identity,
            target_step=target_step,
            target_event=target_event,
            resource_candidate=resource_candidate,
            resource_value=resource_value,
            existing=existing,
            supplements=supplements,
        )

    def _view(self, context: _SetupContext) -> ActionSafetySetupView:
        resource = _resource_candidate_view(context)
        observations, recoveries = _binding_candidates(context)
        effects = _effect_candidates(context)
        current = context.existing if _setup_is_current(context) else None
        gaps: list[str] = []
        if current is None:
            gaps.append("TEST_RESOURCE_UNCONFIRMED")
        if current is None or current.observation is None:
            gaps.append("OBSERVATION_UNCONFIRMED")
        if current is None or current.recovery is None:
            gaps.append("RECOVERY_UNCONFIRMED")
        if current is None or current.effect is None:
            gaps.append("SECURITY_EFFECT_UNCONFIRMED")
        return ActionSafetySetupView(
            recording_id=context.recording.recording_id,
            action_candidate_id=context.action.candidate_id,
            action_display_name=context.action.display_name,
            target_method=str(context.target_step.method),
            recording_identity=context.recording_identity,
            state_changing=_state_changing(context),
            resource_candidates=(resource,),
            observation_candidates=observations,
            recovery_candidates=recoveries,
            security_effect_candidates=effects,
            business_result=(effects[0].label if len(effects) == 1 else None),
            observation_status=("READY" if current is not None and current.observation is not None else "MISSING"),
            recovery_status=(
                "NOT_REQUIRED"
                if not _state_changing(context)
                else "READY"
                if current is not None and current.recovery is not None
                else "MISSING"
            ),
            ready=not gaps,
            confirmed_setup=context.existing,
            gaps=tuple(gaps),
            automatic_execution_allowed=not gaps,
        )

    @staticmethod
    def _resource_fact(
        context: _SetupContext,
        candidate: TestResourceCandidateView,
        *,
        logical_name: str,
        resource_type: str,
        now_us: int,
    ) -> TestResource:
        created_at_us = (
            context.existing.resource.created_at_us
            if context.existing is not None
            and context.existing.resource.recording_id == context.recording.recording_id
            else now_us
        )
        payload = {
            "project_id": context.recording.project_id,
            "action_candidate_id": context.action.candidate_id,
            "recording_id": context.recording.recording_id,
            "flow_id": context.flow.id,
            "logical_name": logical_name,
            "resource_type": resource_type,
            "actual_resource_id": candidate.actual_resource_id,
            "owner_test_identity_id": context.recording_identity.identity_id,
            "owner_role_candidate_id": context.recording_identity.role_candidate_id,
            "consumer": candidate.consumer,
            "location": candidate.location,
            "source_fingerprint": str(context.understanding.source_fingerprint),
            "endpoint_source_fingerprint": _required_endpoint_fingerprint(
                context.understanding
            ),
            "understanding_revision": context.understanding.revision,
            "flow_sha256": context.flow_sha256,
        }
        fingerprint = test_setup_sha256("test_resource", _json_value(payload))
        return TestResource(
            resource_id=f"trs_{fingerprint[:32]}",
            fingerprint=fingerprint,
            created_at_us=created_at_us,
            updated_at_us=now_us,
            **payload,
        )

    @staticmethod
    def _observation_fact(
        resource: TestResource,
        candidate: ObservationCandidateView,
        *,
        now_us: int,
    ) -> ObservationBinding:
        payload = {
            "resource_id": resource.resource_id,
            "trusted_test_identity_id": candidate.trusted_test_identity_id,
            "kind": "OWNER_READ",
            "recording_id": candidate.source_recording_id,
            "source_step_id": candidate.source_step_id,
            "method": "GET",
            "path_template": candidate.path_template,
            "required": True,
        }
        fingerprint = test_setup_sha256("observation_binding", payload)
        return ObservationBinding(
            observation_binding_id=f"obs_{fingerprint[:32]}",
            fingerprint=fingerprint,
            confirmed_at_us=now_us,
            **payload,
        )

    @staticmethod
    def _recovery_fact(
        resource: TestResource,
        candidate: RecoveryCandidateView | None,
        *,
        confirm_not_required: bool,
        now_us: int,
    ) -> RecoveryBinding | None:
        if candidate is None and not confirm_not_required:
            return None
        payload: dict[str, Any] = {
            "resource_id": resource.resource_id,
            "test_identity_id": resource.owner_test_identity_id,
            "kind": (
                RecoveryBindingKind.NOT_REQUIRED
                if confirm_not_required
                else RecoveryBindingKind.RECORDED_REQUEST
            ),
            "recording_id": resource.recording_id if candidate is None else candidate.source_recording_id,
            "source_step_id": None if candidate is None else candidate.source_step_id,
            "method": None if candidate is None else candidate.method,
            "path_template": None if candidate is None else candidate.path_template,
            "json_body_template": (
                {} if candidate is None else candidate.json_body_template
            ),
        }
        fingerprint = test_setup_sha256("recovery_binding", _json_value(payload))
        return RecoveryBinding(
            recovery_binding_id=f"rcv_{fingerprint[:32]}",
            fingerprint=fingerprint,
            confirmed_at_us=now_us,
            **payload,
        )

    @staticmethod
    def _effect_fact(
        resource: TestResource,
        candidate: SecurityEffectCandidateView,
        *,
        now_us: int,
    ) -> SecurityEffectConfirmation:
        payload = {
            "resource_id": resource.resource_id,
            "action_candidate_id": resource.action_candidate_id,
            "kind": candidate.kind,
            "protected_fields": candidate.protected_fields,
        }
        fingerprint = test_setup_sha256("security_effect_confirmation", _json_value(payload))
        return SecurityEffectConfirmation(
            effect_confirmation_id=f"efc_{fingerprint[:32]}",
            fingerprint=fingerprint,
            confirmed_at_us=now_us,
            **payload,
        )

__all__ = [
    "ActionSafetySetupService",
    "ActionSafetySetupView",
    "ConfirmActionSafetySetup",
    "ObservationCandidateView",
    "RecoveryCandidateView",
    "SecurityEffectCandidateView",
    "TestResourceCandidateView",
]
