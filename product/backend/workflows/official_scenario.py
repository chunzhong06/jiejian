# 官方样例配置把受控场景配方转换为正式 Recording、业务资源与权限检查输入，不生成安全结论。

from __future__ import annotations

import json
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingState, RecordingStateEvent
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
    ) -> None:
        self._project_recordings = project_recordings
        self._recording_submission = recording_submission
        self._attempts = attempts
        self._var_dir = var_dir
        self._recording_credentials = recording_credentials
        self._lifecycle = lifecycle
        self._clock_us = clock_us

    def install(
        self,
        *,
        project_id: str,
        endpoint: str,
        export_action_id: str,
        view_action_id: str,
        owner_identity_id: str,
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
        )
        view_recording = self._install_recording(
            project_id=project_id,
            action_id=view_action_id,
            identity_id=owner_identity_id,
            endpoint=endpoint,
            event_factory=_view_events,
            resource_consumer=ValueSlotConsumer.PATH,
            resource_location="path[3]",
        )
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
    ) -> str:
        submitted = self._project_recordings.submit(
            project_id,
            action_candidate_id=action_id,
            test_identity_id=identity_id,
            duration_seconds=60,
            idempotency_key=f"official-scenario-{project_id}-{action_id}",
            headless=True,
        )
        recording_id = submitted.result.recording.recording_id
        try:
            return self._complete_recording(
                submitted,
                project_id=project_id,
                identity_id=identity_id,
                endpoint=endpoint,
                event_factory=event_factory,
                resource_consumer=resource_consumer,
                resource_location=resource_location,
            )
        finally:
            self._recording_credentials.clear(recording_id)

    def _complete_recording(
        self,
        submitted: ProjectRecordingSubmission,
        *,
        project_id: str,
        identity_id: str,
        endpoint: str,
        event_factory: Callable[[str, str, int], tuple[RecordingEvent, ...]],
        resource_consumer: ValueSlotConsumer,
        resource_location: str,
    ) -> str:
        """让固定场景轨迹经过提交、租约、结果消费、审阅和最终化服务。"""

        recording_id = submitted.result.recording.recording_id
        job_id = submitted.result.job.job_id
        now_us = submitted.request.created_at_us
        lease_owner = f"official-scenario:{recording_id}"
        events = event_factory(endpoint, identity_id, now_us)
        claimed = self._attempts.claim(
            ClaimJob(
                job_id=job_id,
                lease_owner=lease_owner,
                now_us=now_us + 1,
                lease_duration_us=60_000_000,
            )
        )
        if claimed is None:
            raise JiejianError(ErrorCode.JOB_CLAIM_CONFLICT, "官方样例流程未能进入正式录制处理")
        completion = self._recording_submission.consume_result(
            job_id=job_id,
            lease_owner=lease_owner,
            fencing_token=claimed.job.fencing_token,
            result=RecordingRunnerResult(
                recording_id=recording_id,
                project_id=project_id,
                finished_at_us=now_us + 30,
                result_type=RecordingRunnerResultType.CAPTURED,
                recording_state=RecordingState.PROCESSING,
                cleanup_status=RecordingCleanupStatus.SUCCEEDED,
                state_events=_recording_state_events(now_us),
                events=events,
            ),
            now_us=now_us + 31,
        )
        draft = completion.draft
        if draft is None:
            raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, "官方样例流程没有形成可审阅草稿")
        target_step = next(step for step in draft.steps if step.request_id == "request_000001")
        for variable in draft.variables:
            source = variable.candidate_sources[0]
            self._lifecycle.review(
                recording_id,
                ConfirmFlowDraftVariableChoice(
                    schema_version="1",
                    operation="CONFIRM_VARIABLE_CHOICE",
                    variable_name=variable.name,
                    choice_id=flow_draft_source_choice_id(source),
                ),
            )
        self._lifecycle.review(
            recording_id,
            ConfirmFlowDraftTarget(
                schema_version="1",
                operation="CONFIRM_TARGET_STEP",
                step_id=target_step.id,
            ),
        )
        resource = next(
            candidate
            for candidate in target_step.resource_candidates
            if candidate.consumer is resource_consumer
            and candidate.location == resource_location
        )
        self._lifecycle.review(
            recording_id,
            ConfirmFlowDraftResource(
                schema_version="1",
                operation="CONFIRM_RESOURCE_SLOT",
                candidate_id=resource.candidate_id,
            ),
        )
        self._lifecycle.finalize(
            recording_id,
            var_dir=self._var_dir,
            now_us=now_us + 40,
        )
        return recording_id


def _view_events(endpoint: str, identity_id: str, now_us: int) -> tuple[RecordingEvent, ...]:
    url = f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}/collaboration"
    body = json.dumps(
        {
            "project_id": SAMPLE_PROJECT_ID,
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
        _event(1, now_us + 11, RecordingEventKind.REQUEST, identity_id, "request_000001", url, method="GET"),
        _event(2, now_us + 12, RecordingEventKind.RESPONSE, identity_id, "request_000001", url, status_code=200, body=body),
    )


def _export_events(endpoint: str, identity_id: str, now_us: int) -> tuple[RecordingEvent, ...]:
    requests = (
        ("POST", "request_000001", f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}/exports", json.dumps({"resource_id": SAMPLE_RESOURCE_ID}), 202, "{}"),
        ("GET", "request_000002", f"{endpoint}/api/observer/resources/{SAMPLE_RESOURCE_ID}", None, 200, json.dumps({"resource_id": SAMPLE_RESOURCE_ID, "workflow_state": "READY", "value": "recorded-artifact"})),
        ("DELETE", "request_000003", f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}/exports", json.dumps({"resource_id": SAMPLE_RESOURCE_ID}), 200, "{}"),
        ("GET", "request_000004", f"{endpoint}/api/observer/resources/{SAMPLE_RESOURCE_ID}", None, 200, json.dumps({"resource_id": SAMPLE_RESOURCE_ID, "workflow_state": "ABSENT", "value": ""})),
    )
    output: list[RecordingEvent] = []
    sequence = 1
    for method, request_id, url, body, status_code, response_body in requests:
        output.append(_event(sequence, now_us + 10 + sequence, RecordingEventKind.REQUEST, identity_id, request_id, url, method=method, body=body))
        sequence += 1
        output.append(_event(sequence, now_us + 10 + sequence, RecordingEventKind.RESPONSE, identity_id, request_id, url, status_code=status_code, body=response_body))
        sequence += 1
    return tuple(output)


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
