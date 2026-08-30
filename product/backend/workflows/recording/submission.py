# =============================================================================
# Recording 应用服务
#
# 定位
#   控制面、持久 Recording 与隔离 Recording Runner 之间的应用边界
#
# 职责
#   幂等提交 Recording Job｜校验可信 Runner 结果｜生成 FlowDraft 并提交完成态
#
# 边界
#   控制面不执行浏览器操作；只消费当前 fencing token 对应的 Runner 结果。
#
# 调用链
#   CLI / API → RecordingSubmission → RequestStore / JobAttemptPort / Storage
# =============================================================================

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.identifiers import JOB_ID_PATTERN, PROJECT_ID_PATTERN, RECORDING_ID_PATTERN
from product.backend.core.lifecycle import JobState
from product.backend.core.recording import Recording, RecordingPurpose, RecordingState, transition_recording_state
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import FlowDraft, RecordingRunnerRequest, RecordingRunnerResultType, RecordingRunnerResult, canonical_flow_draft_json_bytes, canonical_recording_json_bytes
from product.protocols.web.target import WebTargetScope
from product.backend.infra.storage import FlowDraftRevisionRecord, JobRecord, RecordingRecord, StorageUnitOfWork
from product.backend.infra.runtime.jobs.events import append_job_event
from product.backend.infra.runtime.jobs.handlers import JobAttemptPort
from product.backend.infra.runtime.jobs.models import CompleteCancellation, FatalFailureCode, FatalFailure, JobEventType, RetryableFailureCode, RetryableFailure
from product.backend.workflows.recording.processing import FlowDraftProcessor
from product.backend.infra.recording.request_store import RecordingRequestStore


class RecordingApplicationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class SubmitRecording(RecordingApplicationModel):
    request: RecordingRunnerRequest
    flow_id: str = Field(pattern=PROJECT_ID_PATTERN)
    purpose: RecordingPurpose = RecordingPurpose.TARGET
    parent_recording_id: str | None = Field(default=None, pattern=RECORDING_ID_PATTERN)
    idempotency_key: str = Field(min_length=1, max_length=128)
    max_attempts: int = Field(default=3, ge=1, le=1_000)
    available_at_us: int = Field(ge=0)
    now_us: int = Field(ge=0)
    job_id: str | None = Field(default=None, pattern=JOB_ID_PATTERN)


class RecordingSubmissionResult(RecordingApplicationModel):
    created: bool
    job: JobRecord
    recording: RecordingRecord


class RecordingCompletionResult(RecordingApplicationModel):
    job: JobRecord
    recording: RecordingRecord
    draft: FlowDraft | None = None


def recording_target_scope(endpoint: str) -> WebTargetScope:
    """在应用层把已确认 endpoint 收敛为录制 Runner 的 Web 目标范围。"""

    parsed = urlsplit(endpoint)
    if parsed.hostname is None:
        raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "应用运行地址无效")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    origin = f"{parsed.scheme}://{parsed.hostname}:{port}"
    return WebTargetScope(
        base_url=origin,
        allowed_origins=(origin,),
        allowed_hosts=(parsed.hostname,),
        allowed_ports=(port,),
        allow_private_network=True,
        follow_redirects=False,
    )


class RecordingSubmission:
    """创建 Recording Job，并消费当前 fenced Runner 结果。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        request_store: RecordingRequestStore,
        *,
        attempts: JobAttemptPort | None = None,
        processor: FlowDraftProcessor | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._request_store = request_store
        self._attempts = attempts
        self._processor = processor or FlowDraftProcessor()

    def submit(
        self,
        command: SubmitRecording,
        *,
        known_secrets: Sequence[str] = (),
    ) -> RecordingSubmissionResult:
        """原子保存录制请求并创建幂等 Job；事务失败时移除本次孤立快照。"""

        if command.request.created_at_us != command.now_us:
            raise JiejianError(ErrorCode.JOB_TIME_INVALID, "录制请求创建时间不一致")
        job_id = command.job_id or f"job_{uuid4().hex}"
        request_hash, snapshot_created = self._request_store.write(
            job_id,
            command.request,
            known_secrets=known_secrets,
        )
        try:
            # 请求文件先于数据库事务落盘；异常路径必须按 hash 精确清理，不能删除其他提交者的快照。
            result = self._submit_transaction(
                command,
                job_id,
                request_hash,
                known_secrets,
            )
            if result.job.job_id != job_id:
                self._request_store.write(
                    result.job.job_id,
                    command.request,
                    known_secrets=known_secrets,
                )
                if snapshot_created:
                    self._request_store.remove_if_matches(job_id, request_hash)
            return result
        except Exception:
            if snapshot_created:
                self._request_store.remove_if_matches(job_id, request_hash)
            raise

    def consume_result(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        result: RecordingRunnerResult,
        now_us: int,
        known_secrets: Sequence[str] = (),
    ) -> RecordingCompletionResult:
        """校验 RunnerResult 后按结果类型完成、取消或重试当前 fenced attempt。"""

        if self._attempts is None:
            raise RuntimeError("consume_result requires an injected JobAttemptPort")
        attempts = self._attempts
        canonical_recording_json_bytes(result, known_secrets=known_secrets)
        # --- 阶段：可信成功结果进入 FlowDraft 物化 ---
        if result.result_type in {
            RecordingRunnerResultType.CAPTURED,
            RecordingRunnerResultType.SAFETY_STOPPED,
        }:
            return self._persist_success(
                job_id=job_id,
                lease_owner=lease_owner,
                fencing_token=fencing_token,
                result=result,
                now_us=now_us,
                known_secrets=known_secrets,
            )
        # --- 阶段：非成功结果只更新 Job/Recording 生命周期 ---
        if result.result_type is RecordingRunnerResultType.CANCELLED:
            mutation = attempts.complete_cancellation(
                CompleteCancellation(
                    job_id=job_id,
                    lease_owner=lease_owner,
                    fencing_token=fencing_token,
                    now_us=now_us,
                ),
                known_secrets=known_secrets,
            )
        elif result.error is not None and result.error.retryable:
            mutation = attempts.record_retryable_failure(
                RetryableFailure(
                    job_id=job_id,
                    lease_owner=lease_owner,
                    fencing_token=fencing_token,
                    now_us=now_us,
                    reason_code=RetryableFailureCode.WORKER_INTERRUPTED,
                ),
                known_secrets=known_secrets,
            )
        else:
            mutation = attempts.record_fatal_failure(
                FatalFailure(
                    job_id=job_id,
                    lease_owner=lease_owner,
                    fencing_token=fencing_token,
                    now_us=now_us,
                    reason_code=(
                        FatalFailureCode.CLEANUP_FAILED
                        if result.cleanup_status.value == "FAILED"
                        else FatalFailureCode.RUNNER_FATAL
                    ),
                ),
                known_secrets=known_secrets,
            )
        if mutation.recording is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "录制任务目标不一致")
        return RecordingCompletionResult(
            job=mutation.job,
            recording=mutation.recording,
        )

    def _submit_transaction(
        self,
        command: SubmitRecording,
        job_id: str,
        request_hash: str,
        known_secrets: Sequence[str],
    ) -> RecordingSubmissionResult:
        """在一个 UoW 内解析幂等性、创建 Recording 与 Job，并提交初始事件。"""

        with self._new_uow(known_secrets) as work:
            existing = work.jobs.get_by_idempotency(
                command.request.project_id,
                "BROWSER_RECORDING",
                command.idempotency_key,
            )
            if existing is not None:
                return self._existing(work, existing, request_hash)
            if work.projects.get(command.request.project_id) is None:
                raise JiejianError(ErrorCode.JOB_PERSISTENCE, "录制所属项目不存在")
            domain = Recording(
                recording_id=command.request.recording_id,
                project_id=command.request.project_id,
                purpose=command.purpose,
                parent_recording_id=command.parent_recording_id,
                created_at_us=command.now_us,
                updated_at_us=command.now_us,
            )
            recording = RecordingRecord.from_domain(
                domain,
                flow_id=command.flow_id,
            )
            job = JobRecord(
                job_id=job_id,
                project_id=command.request.project_id,
                run_id=None,
                recording_id=command.request.recording_id,
                operation_type="BROWSER_RECORDING",
                state=JobState.PENDING,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
                attempt=0,
                max_attempts=command.max_attempts,
                available_at_us=command.available_at_us,
                lease_owner=None,
                fencing_token=0,
                lease_expires_at_us=None,
                cancel_requested_at_us=None,
                created_at_us=command.now_us,
                updated_at_us=command.now_us,
            )
            work.recordings.add(recording)
            work.jobs.add(job)
            append_job_event(
                work,
                job=job,
                event_type=JobEventType.JOB_SUBMITTED,
                source_state=None,
                target_state=JobState.PENDING,
                occurred_at_us=command.now_us,
                metadata={"attempt": 0, "target_type": "RECORDING"},
            )
            work.commit()
            return RecordingSubmissionResult(
                created=True,
                job=job,
                recording=recording,
            )

    def _persist_success(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        result: RecordingRunnerResult,
        now_us: int,
        known_secrets: Sequence[str],
    ) -> RecordingCompletionResult:
        """把已捕获事件编译为 FlowDraft，并与 fenced Job 完成态原子提交。"""

        with self._new_uow(known_secrets) as work:
            job = work.jobs.get(job_id)
            if (
                job is None
                or job.recording_id != result.recording_id
                or job.run_id is not None
                or job.project_id != result.project_id
                or job.state is not JobState.RUNNING
                or job.lease_owner != lease_owner
                or job.fencing_token != fencing_token
                or job.lease_expires_at_us is None
                or job.lease_expires_at_us <= now_us
                or result.finished_at_us > now_us
            ):
                raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "录制结果租约不匹配")
            existing = work.recordings.get(result.recording_id)
            if existing is None:
                raise JiejianError(ErrorCode.JOB_PERSISTENCE, "录制对象不存在")
            persisted = self._record_from_result(existing, result)
            draft = None
            if result.result_type is RecordingRunnerResultType.CAPTURED:
                request = self._request_store.load(
                    job.job_id,
                    expected_hash=job.request_hash,
                    known_secrets=known_secrets,
                )
                draft = self._processor.build(
                    recording_id=result.recording_id,
                    flow_id=existing.flow_id,
                    action_candidate_id=request.action_candidate_id,
                    events=result.events,
                    known_secrets=known_secrets,
                )
                pending = transition_recording_state(
                    persisted.to_domain(),
                    RecordingState.PENDING_REVIEW,
                    operator="RECORDING_SERVICE",
                    occurred_at_us=now_us,
                )
                persisted = RecordingRecord.from_domain(
                    pending,
                    flow_id=existing.flow_id,
                    browser_events=result.events,
                )
                encoded = canonical_flow_draft_json_bytes(
                    draft,
                    known_secrets=known_secrets,
                )
                work.flow_drafts.add(
                    FlowDraftRevisionRecord(
                        recording_id=draft.recording_id,
                        revision=draft.revision,
                        flow_id=draft.flow_id,
                        draft=draft,
                        draft_sha256=hashlib.sha256(encoded).hexdigest(),
                        created_at_us=now_us,
                    )
                )
            work.recordings.replace(persisted)
            completed = work.job_control.complete_recording_result(
                job_id=job.job_id,
                recording_id=persisted.recording_id,
                attempt=job.attempt,
                lease_owner=lease_owner,
                fencing_token=fencing_token,
                completed_at_us=now_us,
            )
            if completed is None:
                raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "录制结果租约不匹配")
            append_job_event(
                work,
                job=completed,
                event_type=JobEventType.JOB_SUCCEEDED,
                source_state=JobState.RUNNING,
                target_state=JobState.SUCCEEDED,
                occurred_at_us=now_us,
                metadata={
                    "attempt": completed.attempt,
                    "fencing_token": fencing_token,
                    "result_type": result.result_type.value,
                    "draft_revision": draft.revision if draft is not None else 0,
                },
            )
            work.commit()
            return RecordingCompletionResult(
                job=completed,
                recording=persisted,
                draft=draft,
            )

    def _existing(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        request_hash: str,
    ) -> RecordingSubmissionResult:
        if job.request_hash != request_hash or job.recording_id is None:
            raise JiejianError(
                ErrorCode.JOB_IDEMPOTENCY_CONFLICT,
                "幂等键对应的录制请求不一致",
            )
        recording = work.recordings.get(job.recording_id)
        if recording is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "录制对象不存在")
        return RecordingSubmissionResult(
            created=False,
            job=job,
            recording=recording,
        )

    @staticmethod
    def _record_from_result(
        existing: RecordingRecord,
        result: RecordingRunnerResult,
    ) -> RecordingRecord:
        runner_events = result.state_events
        if (
            existing.state is RecordingState.STARTING
            and runner_events
            and runner_events[0].source is RecordingState.CREATED
            and runner_events[0].target is RecordingState.STARTING
        ):
            runner_events = runner_events[1:]
        merged_events = list(existing.state_events)
        current_state = existing.state
        current_time = existing.updated_at_us
        for runner_event in runner_events:
            if (
                runner_event.source is not current_state
                or runner_event.occurred_at_us < current_time
            ):
                raise JiejianError(
                    ErrorCode.RECORD_PROTOCOL_INVALID,
                    "录制结果生命周期与持久状态不一致",
                )
            merged_events.append(
                runner_event.model_copy(update={"sequence": len(merged_events) + 1})
            )
            current_state = runner_event.target
            current_time = runner_event.occurred_at_us
        if current_state is not result.recording_state:
            raise JiejianError(
                ErrorCode.RECORD_PROTOCOL_INVALID,
                "录制结果生命周期未到达声明状态",
            )
        capture_finished = next(
            (
                event.occurred_at_us
                for event in merged_events
                if event.target is RecordingState.PROCESSING
            ),
            None,
        )
        last_event_at = merged_events[-1].occurred_at_us
        terminal = result.recording_state in {
            RecordingState.COMPLETED,
            RecordingState.FAILED,
            RecordingState.CANCELLED,
            RecordingState.SAFETY_STOPPED,
        }
        domain = Recording(
            recording_id=existing.recording_id,
            project_id=existing.project_id,
            purpose=existing.purpose,
            parent_recording_id=existing.parent_recording_id,
            state=result.recording_state,
            created_at_us=existing.created_at_us,
            updated_at_us=last_event_at,
            started_at_us=existing.started_at_us,
            capture_finished_at_us=capture_finished,
            finished_at_us=last_event_at if terminal else None,
            reason_codes=tuple(
                dict.fromkeys((*existing.reason_codes, *result.reason_codes))
            ),
            events=tuple(merged_events),
        )
        return RecordingRecord.from_domain(
            domain,
            flow_id=existing.flow_id,
            browser_events=result.events,
        )

    def _new_uow(self, known_secrets: Sequence[str]) -> StorageUnitOfWork:
        return self._uow_factory(
            known_secrets=tuple(secret for secret in known_secrets if secret)
        )
