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

from product.backend.core.application_understanding import ActionCandidate, CandidateDecision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.workflows.recording.submission import (
    RecordingSubmission,
    RecordingSubmissionResult,
    SubmitRecording,
    recording_target_scope,
)
from product.backend.workflows.test_identities import TestIdentityView
from product.protocols import RecordingBudget, RecordingRunnerRequest


@dataclass(frozen=True, slots=True)
class ProjectRecordingSubmission:
    """保留控制面展示所需的非秘密事实与正式提交结果。"""

    request: RecordingRunnerRequest
    result: RecordingSubmissionResult
    action: ActionCandidate
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
        uow_factory=None,
        request_store=None,
        projects=None,
        clock_us=None,
    ) -> None:
        self._application_understanding = application_understanding
        self._test_identities = test_identities
        self._recording_credentials = recording_credentials
        self._recording_submission = recording_submission
        self._uow_factory = uow_factory
        self._request_store = request_store
        self._projects = projects
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)

    def submit(
        self,
        project_id: str,
        *,
        action_candidate_id: str,
        test_identity_id: str,
        duration_seconds: int,
        idempotency_key: str,
        purpose: RecordingPurpose = RecordingPurpose.TARGET,
        parent_recording_id: str | None = None,
        headless: bool = False,
    ) -> ProjectRecordingSubmission:
        """校验项目式输入并提交；异常时精确清理本次短期会话。"""

        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 3_600:
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制时长必须在 1 到 3600 秒之间")
        if (purpose is RecordingPurpose.TARGET) != (parent_recording_id is None):
            raise JiejianError(ErrorCode.INPUT_INVALID, "补录必须关联原业务录制")
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
            parent_request = self._request_store.load(
                parent_job.job_id,
                expected_hash=parent_job.request_hash,
            )
            if (
                parent_request.action_candidate_id != action_candidate_id
                or parent_request.sessions[0].test_identity_id != test_identity_id
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
        action = next(
            (
                item
                for item in understanding.action_candidates
                if item.candidate_id == action_candidate_id
                and item.decision is CandidateDecision.CONFIRMED
                and not item.stale
            ),
            None,
        )
        if action is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制动作尚未确认或已经失效")
        if understanding.confirmed_endpoint is None:
            raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "请先确认应用运行地址")
        identity = self._test_identities.get(test_identity_id)
        now_us = self._clock_us()
        recording_id = f"rec_{uuid4().hex}"
        duration_us = duration_seconds * 1_000_000
        session = self._recording_credentials.prepare(
            project_id=project_id,
            test_identity_id=test_identity_id,
            recording_id=recording_id,
            session_ref=f"session_{uuid4().hex}",
            now_us=now_us,
            expires_at_us=now_us + duration_us,
        )
        request = RecordingRunnerRequest(
            schema_version="1",
            recording_id=recording_id,
            project_id=project_id,
            action_candidate_id=action.candidate_id,
            created_at_us=now_us,
            target_scope=recording_target_scope(understanding.confirmed_endpoint),
            sessions=(session,),
            budget=RecordingBudget(max_duration_us=duration_us, max_contexts=1),
            headless=headless,
            trace_enabled=False,
        )
        try:
            result = self._recording_submission.submit(
                SubmitRecording(
                    request=request,
                    flow_id=f"flow-{action.candidate_id.removeprefix('action_')}",
                    purpose=purpose,
                    parent_recording_id=parent_recording_id,
                    idempotency_key=idempotency_key,
                    now_us=now_us,
                    available_at_us=now_us,
                )
            )
        except Exception:
            self._recording_credentials.clear(recording_id)
            raise
        return ProjectRecordingSubmission(
            request=request,
            result=result,
            action=action,
            test_identity=identity,
        )


__all__ = ["ProjectRecordingService", "ProjectRecordingSubmission"]
