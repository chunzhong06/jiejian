# 官方样例配置把受控场景配方转换为正式 Recording、业务资源与权限检查输入，不生成安全结论。

from __future__ import annotations

import json
import hashlib
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingPurpose, RecordingState, RecordingStateEvent
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.models import ClaimJob
from product.backend.workflows.recording.credentials import RecordingCredentialProvider
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.recording.project_submission import (
    ProjectRecordingService,
    ProjectRecordingSubmission,
)
from product.backend.workflows.recording.submission import RecordingSubmission
from product.protocols import (
    ConfirmFlowDraftResource,
    ConfirmFlowDraftTarget,
    ConfirmFlowDraftVariableChoice,
    RecordingCleanupStatus,
    RecordingEvent,
    RecordingEventKind,
    RecordingRunnerResult,
    RecordingRunnerResultType,
    ValueSlotConsumer,
    flow_draft_source_choice_id,
)


SAMPLE_PROJECT_ID = "campus-digital-museum"
SAMPLE_RESOURCE_ID = "campus-digital-museum-package"
EXPORT_ACTION_KEY = "POST /api/projects/{project_id}/exports"
VIEW_ACTION_KEY = "GET /api/projects/{project_id}/collaboration"


class OfficialScenarioInstaller:
    """安装可追溯的官方场景输入；正式 Runner 仍独立形成 BLOCK、PASS 或证据不足。"""

    def __init__(
        self,
        project_recordings: ProjectRecordingService,
        recording_submission: RecordingSubmission,
        attempts: JobAttempts,
        *,
        var_dir: Path,
        recording_credentials: RecordingCredentialProvider,
        lifecycle: RecordingLifecycle,
        clock_us: Callable[[], int],
        preparation,
    ) -> None:
        self._project_recordings = project_recordings
        self._recording_submission = recording_submission
        self._attempts = attempts
        self._var_dir = var_dir
        self._recording_credentials = recording_credentials
        self._lifecycle = lifecycle
        self._clock_us = clock_us
        self._preparation = preparation
        self._submissions = {}

    def install(
        self,
        *,
        project_id: str,
        endpoint: str,
        export_action_id: str,
        view_action_id: str,
        owner_identity_id: str,
        member_identity_id: str,
        source_fingerprint: str,
    ) -> tuple[str, str]:
        """发布两条已审阅场景流程；它们只定义考题，不代表任何运行结果。"""

        export_recording = self._install_recording(
            project_id=project_id,
            action_id=export_action_id,
            identity_id=owner_identity_id,
            endpoint=endpoint,
            event_factory=_export_events,
            resource_consumer=ValueSlotConsumer.JSON_BODY,
            resource_location="$.resource_id",
            source_fingerprint=source_fingerprint,
        )
        view_recording = self._install_recording(
            project_id=project_id,
            action_id=view_action_id,
            identity_id=member_identity_id,
            endpoint=endpoint,
            event_factory=_view_events,
            resource_consumer=ValueSlotConsumer.PATH,
            resource_location="path[2]",
            source_fingerprint=source_fingerprint,
            target_request_id="request_000002",
        )
        self._install_recording(project_id=project_id,action_id=export_action_id,identity_id=owner_identity_id,
            endpoint=endpoint,event_factory=_recovery_events,resource_consumer=ValueSlotConsumer.JSON_BODY,
            resource_location="$.resource_id",source_fingerprint=source_fingerprint,
            purpose=RecordingPurpose.RECOVERY,parent_recording_id=export_recording)
        return export_recording, view_recording

    def _install_recording(
        self,
        *,
        project_id: str,
        action_id: str,
        identity_id: str,
        endpoint: str,
        event_factory: Callable[[str, str, int], tuple[RecordingEvent, ...]],
        resource_consumer: ValueSlotConsumer,
        resource_location: str,
        source_fingerprint: str,
        purpose=RecordingPurpose.TARGET,
        parent_recording_id=None,
        target_request_id="request_000001",
    ) -> str:
        from product.backend.workflows.preparation.demonstrations import legal_demonstrations
        action=next(item for item in self._preparation.get(project_id).actions if item.action_id==action_id)
        choices=legal_demonstrations(action.assurance_contract,action.permissions,action.identity_requirements)
        choice=next((item for item in choices if item.can_execute and item.subject_test_identity_id==identity_id
            and item.resource_owner_test_identity_id==identity_id),None)
        if choice is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,"官方示例缺少已确认的合法演示组合")
        key=(project_id,action_id,action.action_revision,identity_id,choice.resource_owner_test_identity_id,
             choice.subject_slot_id,choice.resource_owner_slot_id,source_fingerprint,purpose.value,parent_recording_id,
             resource_consumer.value,resource_location,target_request_id,"official-recipe-v2")
        submitted=self._project_recordings.submit_captured(project_id,
            events=event_factory(endpoint,identity_id,self._clock_us()),
            business_action_id=action_id,action_revision=action.action_revision,
            subject_test_identity_id=identity_id,resource_owner_test_identity_id=choice.resource_owner_test_identity_id,
            subject_slot_id=choice.subject_slot_id,resource_owner_slot_id=choice.resource_owner_slot_id,
            resource_owner_confirmed=True,duration_seconds=60,purpose=purpose,parent_recording_id=parent_recording_id,
            idempotency_key="official-"+hashlib.sha256(json.dumps(key,separators=(",",":")).encode()).hexdigest(),headless=True)
        recording_id=submitted.result.recording.recording_id
        status=self._lifecycle.status(recording_id)
        if status.recording.state is RecordingState.COMPLETED:
            return recording_id
        draft=status.draft
        if status.recording.state is not RecordingState.PENDING_REVIEW or draft is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,"固定流程需要人工处理既有任务")
        # 只补尚未确认的选择，恢复时不得重新消费 raw 或重复增加已确认 revision。
        target_step=next(step for step in draft.steps if step.request_id==target_request_id)
        for variable in draft.variables:
            if variable.confirmed_source is None:
                source=variable.candidate_sources[0]
                self._lifecycle.review(recording_id,ConfirmFlowDraftVariableChoice(schema_version="1",
                    operation="CONFIRM_VARIABLE_CHOICE",variable_name=variable.name,
                    choice_id=flow_draft_source_choice_id(source)))
        if draft.target_step_id != target_step.id:
            self._lifecycle.review(recording_id,ConfirmFlowDraftTarget(schema_version="1",
                operation="CONFIRM_TARGET_STEP",step_id=target_step.id))
        draft=self._lifecycle.status(recording_id).draft
        if purpose is RecordingPurpose.TARGET:
            resource=next(candidate for candidate in target_step.resource_candidates
                if candidate.consumer is resource_consumer and candidate.location==resource_location)
            if draft.resource_candidate_id != resource.candidate_id:
                self._lifecycle.review(recording_id,ConfirmFlowDraftResource(schema_version="1",
                    operation="CONFIRM_RESOURCE_SLOT",candidate_id=resource.candidate_id))
        self._lifecycle.finalize(recording_id,var_dir=self._var_dir,now_us=self._clock_us())
        return recording_id


def _view_events(endpoint: str, identity_id: str, now_us: int) -> tuple[RecordingEvent, ...]:
    url = f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}/collaboration"
    body = json.dumps(
        {
            "project_id": SAMPLE_PROJECT_ID,
            "resource_id": SAMPLE_PROJECT_ID,
            "collaboration_material": {"title":"校园数字展馆","summary":"展馆项目申报说明、展陈视觉设计稿、项目预算摘要、内部评审纪要"},
            "name": "校园数字展馆",
            "members": [
                {"user_id": "alice", "role": "PROJECT_OWNER"},
                {"user_id": "bob", "role": "MEMBER"},
            ],
            "materials": [
                {"name": "展馆项目申报说明", "kind": "APPLICATION_NOTE"},
                {"name": "展陈视觉设计稿", "kind": "DESIGN_SOURCE"},
                {"name": "项目预算摘要", "kind": "BUDGET_SUMMARY"},
                {"name": "内部评审纪要", "kind": "REVIEW_NOTE"},
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return (
        # 项目详情给出真实资源来源，使普通录制器能识别路径中间的项目 ID。
        _event(1, now_us, RecordingEventKind.REQUEST, identity_id, "request_000001",
            f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}", method="GET"),
        _event(2, now_us, RecordingEventKind.RESPONSE, identity_id, "request_000001",
            f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}", status_code=200, body=json.dumps({"project_id": SAMPLE_PROJECT_ID})),
        _event(3, now_us, RecordingEventKind.REQUEST, identity_id, "request_000002", url, method="GET"),
        _event(4, now_us, RecordingEventKind.RESPONSE, identity_id, "request_000002", url, status_code=200, body=body),
    )


def _export_events(endpoint: str, identity_id: str, now_us: int) -> tuple[RecordingEvent, ...]:
    requests = (
        ("POST", "request_000001", f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}/exports", json.dumps({"resource_id": SAMPLE_RESOURCE_ID}), 202, "{}"),
    )
    output: list[RecordingEvent] = []
    sequence = 1
    for method, request_id, url, body, status_code, response_body in requests:
        output.append(_event(sequence, now_us + 10 + sequence, RecordingEventKind.REQUEST, identity_id, request_id, url, method=method, body=body))
        sequence += 1
        output.append(_event(sequence, now_us + 10 + sequence, RecordingEventKind.RESPONSE, identity_id, request_id, url, status_code=status_code, body=response_body))
        sequence += 1
    return tuple(output)


def _recovery_events(endpoint: str, identity_id: str, now_us: int) -> tuple[RecordingEvent,...]:
    """撤销是独立正式补录，不能混进 TARGET Flow 提前抹去待观察后果。"""
    url=f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}/exports"
    return (_event(1,now_us+11,RecordingEventKind.REQUEST,identity_id,"request_000001",url,
        method="DELETE",body=json.dumps({"resource_id":SAMPLE_RESOURCE_ID})),
        _event(2,now_us+12,RecordingEventKind.RESPONSE,identity_id,"request_000001",url,status_code=200,body="{}"))


def _event(
    sequence: int,
    occurred_at_us: int,
    kind: RecordingEventKind,
    identity_id: str,
    request_id: str,
    url: str,
    *,
    method: str | None = None,
    status_code: int | None = None,
    body: str | None = None,
) -> RecordingEvent:
    return RecordingEvent(
        sequence=sequence,
        occurred_at_us=occurred_at_us,
        kind=kind,
        identity_id=identity_id,
        page_id="page_000001",
        frame_id="frame_000001",
        request_id=request_id,
        url=url,
        method=method,
        status_code=status_code,
        resource_type="fetch" if method is not None else None,
        body=body,
    )


def _recording_state_events(now_us: int) -> tuple[RecordingStateEvent, ...]:
    states = (
        RecordingState.CREATED,
        RecordingState.STARTING,
        RecordingState.RECORDING,
        RecordingState.CLEANING,
        RecordingState.PROCESSING,
    )
    return tuple(
        RecordingStateEvent(
            sequence=index,
            source=source,
            target=target,
            operator="OFFICIAL_SCENARIO_SETUP",
            occurred_at_us=now_us + index + 1,
        )
        for index, (source, target) in enumerate(pairwise(states), start=1)
    )

__all__ = [
    "EXPORT_ACTION_KEY",
    "OfficialScenarioInstaller",
    "SAMPLE_RESOURCE_ID",
    "VIEW_ACTION_KEY",
]
