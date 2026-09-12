# =============================================================================
# Recording 完成提交与同动作补录关系校验
#
# 定位
#   Web 与普通 CLI 共用的当前项目录制请求准备边界。
#
# 职责
#   校验已确认动作与端点｜准备单一测试身份会话｜构造并提交 Recording Job
#
# 边界
#   不执行浏览器、不控制采集阶段，也不从登录行为推导业务流程。
# =============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import uuid4

from product.backend.core.business_boundary import BusinessActionRevision, ImplementationBindingStatus
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.recording import RecordingPurpose, RecordingState, RecordingStateEvent
from product.backend.workflows.recording.submission import (
    RecordingSubmission,
    RecordingSubmissionResult,
    SubmitRecording,
    recording_target_scope,
)
from product.backend.workflows.test_identities import TestIdentityView
from product.backend.workflows.test_identities.service import TestIdentityStatus
from product.backend.workflows.recording.source import recording_source_fingerprint
from product.protocols import RecordingBudget, RecordingRunnerRequest, RecordingRunnerResult, RecordingRunnerResultType, RecordingCleanupStatus


@dataclass(frozen=True, slots=True)
class ProjectRecordingSubmission:
    """保留控制面展示所需的非秘密事实与正式提交结果。"""

    request: RecordingRunnerRequest
    result: RecordingSubmissionResult
    action: BusinessActionRevision
    test_identity: TestIdentityView


class ProjectRecordingService:
    """从当前项目权威事实构造唯一的普通 Recording 提交。"""

    def __init__(
        self,
        application_understanding,
        test_identities,
        recording_credentials,
        recording_submission: RecordingSubmission,
        *,
        business_boundaries,
        uow_factory=None,
        request_store=None,
        projects=None,
        clock_us=None,
        preparation=None,
    ) -> None:
        self._application_understanding = application_understanding
        self._business_boundaries = business_boundaries
        self._test_identities = test_identities
        self._recording_credentials = recording_credentials
        self._recording_submission = recording_submission
        self._uow_factory = uow_factory
        self._request_store = request_store
        self._projects = projects
        self._preparation = preparation
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)

    def submit(
        self,
        project_id: str,
        *,
        business_action_id: str,
        action_revision: int,
        subject_test_identity_id: str,
        resource_owner_test_identity_id: str,
        subject_slot_id: str,
        resource_owner_slot_id: str,
        resource_owner_confirmed: bool = False,
        duration_seconds: int,
        idempotency_key: str,
        purpose: RecordingPurpose = RecordingPurpose.TARGET,
        parent_recording_id: str | None = None,
        effect_id: str | None = None,
        headless: bool = False,
    ) -> ProjectRecordingSubmission:
        """按普通控制面合同提交浏览器录制。"""
        return self._submit(**{key: value for key, value in locals().items() if key != "self"})

    def submit_captured(self, project_id: str, *, events, **parameters) -> ProjectRecordingSubmission:
        """内部固定配方入口；公开 API 不接收事件、租约或此模式。"""
        return self._submit(project_id, captured_events=events, **parameters)

    def _submit(
        self,
        project_id: str,
        *,
        business_action_id: str,
        action_revision: int,
        subject_test_identity_id: str,
        resource_owner_test_identity_id: str,
        subject_slot_id: str,
        resource_owner_slot_id: str,
        resource_owner_confirmed: bool = False,
        duration_seconds: int,
        idempotency_key: str,
        purpose: RecordingPurpose = RecordingPurpose.TARGET,
        parent_recording_id: str | None = None,
        effect_id: str | None = None,
        headless: bool = False,
        captured_events=None,
    ) -> ProjectRecordingSubmission:
        """校验项目式输入并提交；异常时精确清理本次短期会话。"""

        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 3_600:
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制时长必须在 1 到 3600 秒之间")
        if (purpose is RecordingPurpose.TARGET) != (parent_recording_id is None):
            raise JiejianError(ErrorCode.INPUT_INVALID, "补录必须关联原业务录制")
        if (purpose is RecordingPurpose.OBSERVATION) != (effect_id is not None):
            raise JiejianError(ErrorCode.INPUT_INVALID, "结果证明必须指定已确认的业务效果")
        if parent_recording_id is not None:
            if self._uow_factory is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "补录服务尚未装配")
            with self._uow_factory() as work:
                parent = work.recordings.get(parent_recording_id)
                parent_job = work.jobs.get_by_recording(parent_recording_id)
            if (
                parent is None
                or parent.project_id != project_id
                or parent.purpose is not RecordingPurpose.TARGET
                or parent.state is not RecordingState.COMPLETED
                or parent_job is None
            ):
                raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "原业务录制不存在或尚未完成")
            if self._request_store is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "补录请求存储尚未装配")
            parent_request = self._request_store.load_history(
                parent_job.job_id,
                expected_hash=parent_job.request_hash,
            )
            if (
                parent_request.business_action_id != business_action_id
                or parent_request.action_revision != action_revision
                or parent_request.subject_test_identity_id != subject_test_identity_id
                or parent_request.resource_owner_test_identity_id != resource_owner_test_identity_id
            ):
                raise JiejianError(
                    ErrorCode.INPUT_INVALID,
                    "补录必须沿用原业务动作和测试账号",
                )
        if (
            self._projects is not None
            and self._projects.get(project_id).status is ProjectStatus.ARCHIVED
        ):
            raise JiejianError(
                ErrorCode.PROJECT_ARCHIVE_CONFLICT,
                "已移除应用不能创建新的录制任务，请先重新接入应用",
            )
        understanding = self._application_understanding.get(project_id)
        boundary = self._business_boundaries.view(project_id)
        action = next(
            (
                item
                for item in boundary.actions
                if item.action_id == business_action_id and item.revision == action_revision
            ),
            None,
        )
        if action is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制动作尚未确认或已经失效")
        if not any(
            item.action_id == business_action_id and item.action_revision == action_revision
            and item.status is ImplementationBindingStatus.CURRENT
            for item in boundary.action_bindings
        ):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先确认业务动作的当前实现")
        if effect_id is not None and effect_id not in {item.effect_id for item in action.effect_catalog}:
            raise JiejianError(ErrorCode.INPUT_INVALID, "结果证明引用的业务效果不属于当前动作")
        if purpose is RecordingPurpose.RECOVERY and not action.state_changing:
            raise JiejianError(ErrorCode.INPUT_INVALID, "只读业务动作不需要录制恢复方式")
        if understanding.confirmed_endpoint is None:
            raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "请先确认应用运行地址")
        if self._preparation is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备服务未装配")
        prepared_action = next((item for item in self._preparation.get(project_id).actions
                                if (item.action_id, item.action_revision) == (business_action_id, action_revision)), None)
        if prepared_action is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
        from product.backend.workflows.preparation.demonstrations import legal_demonstrations
        combinations = legal_demonstrations(prepared_action.assurance_contract, boundary.permission_intents,
                                            prepared_action.identity_requirements)
        requested = (subject_test_identity_id, resource_owner_test_identity_id, subject_slot_id, resource_owner_slot_id)
        if not any(item.can_execute and (item.subject_test_identity_id, item.resource_owner_test_identity_id,
                   item.subject_slot_id, item.resource_owner_slot_id) == requested for item in combinations):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化", details={"reason": "ALLOW_RESOURCE_SETUP_REQUIRED"})
        if subject_test_identity_id != resource_owner_test_identity_id and resource_owner_confirmed is not True:
            raise JiejianError(ErrorCode.INPUT_INVALID, "准备选择无效", details={"reason": "RESOURCE_OWNER_CONFIRMATION_REQUIRED"})
        identity = self._test_identities.get(subject_test_identity_id)
        owner = self._test_identities.get(resource_owner_test_identity_id)
        if (
            identity.project_id != project_id or identity.status is not TestIdentityStatus.PREPARED
            or not any(
                item.actor_id == identity.actor_id and item.revision == identity.actor_revision
                for item in boundary.actors
            )
            or not any(
                item.actor_id == identity.actor_id and item.actor_revision == identity.actor_revision
                and item.status is ImplementationBindingStatus.CURRENT
                for item in boundary.actor_bindings
            )
        ):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "录制需要本应用当前角色下已登录的测试账号")
        source_fingerprint = recording_source_fingerprint(
            action, identity, understanding,
            next(item for item in boundary.action_bindings if item.action_id == action.action_id),
            next(item for item in boundary.actor_bindings if item.actor_id == identity.actor_id),
            owner=owner, owner_actor_binding=next(item for item in boundary.actor_bindings if item.actor_id == owner.actor_id),
        )
        if captured_events is not None:
            prior = self._recording_submission.captured_existing(project_id, idempotency_key)
            if prior is not None:
                request, result = prior
                expected = dict(business_action_id=action.action_id, action_revision=action.revision,
                    subject_test_identity_id=subject_test_identity_id, resource_owner_test_identity_id=resource_owner_test_identity_id,
                    subject_slot_id=subject_slot_id, resource_owner_slot_id=resource_owner_slot_id,
                    resource_owner_confirmed=resource_owner_confirmed, preparation_source_fingerprint=source_fingerprint,
                    purpose=purpose, parent_recording_id=parent_recording_id, effect_id=effect_id,
                    target_scope=recording_target_scope(understanding.confirmed_endpoint), headless=headless,
                    budget=RecordingBudget(max_duration_us=duration_seconds * 1_000_000, max_contexts=1))
                if any(getattr(request, key) != value for key, value in expected.items()):
                    raise JiejianError(ErrorCode.JOB_IDEMPOTENCY_CONFLICT, "固定流程输入已变化")
                return ProjectRecordingSubmission(request=request, result=result, action=action, test_identity=identity)
        now_us = self._clock_us()
        recording_id = f"rec_{uuid4().hex}"
        duration_us = duration_seconds * 1_000_000
        session = self._recording_credentials.prepare(
            project_id=project_id,
            test_identity_id=subject_test_identity_id,
            recording_id=recording_id,
            session_ref=f"session_{uuid4().hex}",
            now_us=now_us,
            expires_at_us=now_us + duration_us,
        )
        try:
            request = RecordingRunnerRequest(
                schema_version="3",
                recording_id=recording_id,
                project_id=project_id,
                business_action_id=action.action_id,
                action_revision=action.revision,
                subject_test_identity_id=subject_test_identity_id,
                resource_owner_test_identity_id=resource_owner_test_identity_id,
                subject_slot_id=subject_slot_id, resource_owner_slot_id=resource_owner_slot_id,
                resource_owner_confirmed=resource_owner_confirmed,
                preparation_source_fingerprint=source_fingerprint,
                purpose=purpose,
                parent_recording_id=parent_recording_id,
                effect_id=effect_id,
                created_at_us=now_us,
                target_scope=recording_target_scope(understanding.confirmed_endpoint),
                sessions=(session,),
                budget=RecordingBudget(max_duration_us=duration_us, max_contexts=1),
                headless=headless,
                trace_enabled=False,
            )
            command = SubmitRecording(
                    request=request,
                    flow_id=f"flow-{action.action_id.removeprefix('bac_')}-r{action.revision}",
                    idempotency_key=idempotency_key,
                    now_us=now_us,
                    available_at_us=now_us,
                    max_attempts=1 if captured_events is not None else 3,
                )
            if captured_events is None:
                result = self._recording_submission.submit(command)
            else:
                states = (RecordingState.CREATED, RecordingState.STARTING, RecordingState.RECORDING,
                    RecordingState.CLEANING, RecordingState.PROCESSING)
                result = self._recording_submission.submit_captured(command, RecordingRunnerResult(
                    recording_id=recording_id, project_id=project_id, finished_at_us=now_us,
                    result_type=RecordingRunnerResultType.CAPTURED, recording_state=RecordingState.PROCESSING,
                    cleanup_status=RecordingCleanupStatus.SUCCEEDED,
                    state_events=tuple(RecordingStateEvent(sequence=index, source=source, target=target,
                        operator="FIXED_RECORDING_RECIPE", occurred_at_us=now_us)
                        for index, (source, target) in enumerate(zip(states, states[1:]), 1)),
                    events=tuple(event.model_copy(update={"occurred_at_us": now_us}) for event in captured_events)))
                if not result.created:
                    request, result = self._recording_submission.captured_existing(project_id, idempotency_key)
        except Exception:
            self._recording_credentials.clear(recording_id)
            raise
        finally:
            if captured_events is not None:
                self._recording_credentials.clear(recording_id)
        return ProjectRecordingSubmission(
            request=request,
            result=result,
            action=action,
            test_identity=identity,
        )


__all__ = ["ProjectRecordingService", "ProjectRecordingSubmission"]
