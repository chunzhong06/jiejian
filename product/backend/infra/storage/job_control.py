# =============================================================================
# Job 原子控制仓储
#
# 定位
#   attempt、lease、fencing、cancel、recovery 状态竞争的数据库原子边界
#
# 职责
#   执行条件状态更新｜验证 owner 与 fencing token｜保持 Job 和 Run 完成态一致
#
# 边界
#   运行态更新必须匹配 lease_owner 与 fencing token；过期执行者不得完成新状态。
#
# 调用链
#   Execution services → JobControlRepository → SQLAlchemy conditional SQL
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, and_, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from product.backend.core.lifecycle import JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.jobs import JobRow
from product.backend.infra.storage.recordings import RecordingRow
from product.backend.infra.storage.runs import RunRow
from product.backend.infra.storage.jobs import JobRecord, JobRepository
from product.backend.infra.storage.runs import RunRecord, RunRepository

_NONTERMINAL_RUNS = (
    RunLifecycle.QUEUED.value,
    RunLifecycle.PREFLIGHT.value,
    RunLifecycle.PLANNING.value,
    RunLifecycle.EXECUTING.value,
    RunLifecycle.VERIFYING.value,
    RunLifecycle.REPORTING.value,
)


class JobControlRepository:
    """只暴露原子 Job/Run 条件更新，不把 ORM 行或 Session 交给调用方。"""

    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._jobs = JobRepository(session, known_secrets)
        self._runs = RunRepository(session, known_secrets)

    def claim(
        self,
        *,
        job_id: str | None,
        lease_owner: str,
        now_us: int,
        lease_expires_at_us: int,
    ) -> JobRecord | None:
        """原子领取一个可运行 Job，并同时递增 attempt 与 fencing token。"""

        eligible = (
            select(JobRow.job_id)
            .outerjoin(RunRow, RunRow.run_id == JobRow.run_id)
            .outerjoin(
                RecordingRow,
                RecordingRow.recording_id == JobRow.recording_id,
            )
            .where(
                JobRow.state.in_(
                    (JobState.PENDING.value, JobState.RETRY_WAIT.value)
                ),
                JobRow.available_at_us <= now_us,
                JobRow.cancel_requested_at_us.is_(None),
                JobRow.attempt < JobRow.max_attempts,
                JobRow.lease_owner.is_(None),
                JobRow.lease_expires_at_us.is_(None),
                JobRow.updated_at_us <= now_us,
                or_(
                    and_(
                        JobRow.run_id.is_not(None),
                        RunRow.lifecycle.in_(_NONTERMINAL_RUNS),
                        RunRow.verdict.is_(None),
                    ),
                    and_(
                        JobRow.recording_id.is_not(None),
                        RecordingRow.state.in_(("CREATED", "STARTING")),
                    ),
                ),
            )
            .order_by(JobRow.available_at_us, JobRow.created_at_us, JobRow.job_id)
            .limit(1)
        )
        if job_id is not None:
            eligible = eligible.where(JobRow.job_id == job_id)
        claimed_id = _scalar_value(
            self._session,
            update(JobRow)
            .where(JobRow.job_id == eligible.scalar_subquery())
            .values(
                state=JobState.RUNNING.value,
                attempt=JobRow.attempt + 1,
                fencing_token=JobRow.fencing_token + 1,
                lease_owner=lease_owner,
                lease_expires_at_us=lease_expires_at_us,
                updated_at_us=now_us,
            )
            .returning(JobRow.job_id),
        )
        return self._jobs.get(claimed_id) if claimed_id is not None else None

    def advance_run_after_claim(self, run_id: str, now_us: int) -> RunRecord | None:
        _execute(
            self._session,
            update(RunRow)
            .where(
                RunRow.run_id == run_id,
                RunRow.lifecycle == RunLifecycle.QUEUED.value,
                RunRow.verdict.is_(None),
                RunRow.updated_at_us <= now_us,
            )
            .values(lifecycle=RunLifecycle.PREFLIGHT.value, updated_at_us=now_us),
        )
        run = self._runs.get(run_id)
        if run is None or run.lifecycle not in {
            RunLifecycle.PREFLIGHT,
            RunLifecycle.PLANNING,
            RunLifecycle.EXECUTING,
            RunLifecycle.VERIFYING,
            RunLifecycle.REPORTING,
        }:
            return None
        return run

    def renew_lease(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        now_us: int,
        lease_expires_at_us: int,
    ) -> JobRecord | None:
        """仅允许当前 owner/token 在旧租约尚有效时单调延长租约。"""

        renewed_id = _scalar_value(
            self._session,
            update(JobRow)
            .where(
                JobRow.job_id == job_id,
                JobRow.state == JobState.RUNNING.value,
                JobRow.lease_owner == lease_owner,
                JobRow.fencing_token == fencing_token,
                JobRow.lease_expires_at_us > now_us,
                JobRow.lease_expires_at_us < lease_expires_at_us,
                JobRow.updated_at_us <= now_us,
            )
            .values(
                lease_expires_at_us=lease_expires_at_us,
                updated_at_us=now_us,
            )
            .returning(JobRow.job_id),
        )
        return self._jobs.get(renewed_id) if renewed_id is not None else None

    def set_cancel_requested_at_if_absent(
        self,
        job_id: str,
        now_us: int,
    ) -> tuple[JobRecord | None, bool]:
        changed_id = _scalar_value(
            self._session,
            update(JobRow)
            .where(
                JobRow.job_id == job_id,
                JobRow.state.in_(
                    (
                        JobState.PENDING.value,
                        JobState.RUNNING.value,
                        JobState.RETRY_WAIT.value,
                    )
                ),
                JobRow.cancel_requested_at_us.is_(None),
                JobRow.updated_at_us <= now_us,
            )
            .values(cancel_requested_at_us=now_us, updated_at_us=now_us)
            .returning(JobRow.job_id),
        )
        if changed_id is not None:
            return self._jobs.get(changed_id), True
        return self._jobs.get(job_id), False

    def cancel_waiting(self, job_id: str, now_us: int) -> JobRecord | None:
        cancelled_id = _scalar_value(
            self._session,
            update(JobRow)
            .where(
                JobRow.job_id == job_id,
                JobRow.state.in_(
                    (JobState.PENDING.value, JobState.RETRY_WAIT.value)
                ),
                JobRow.cancel_requested_at_us.is_not(None),
                JobRow.updated_at_us <= now_us,
            )
            .values(state=JobState.CANCELLED.value, updated_at_us=now_us)
            .returning(JobRow.job_id),
        )
        return self._jobs.get(cancelled_id) if cancelled_id is not None else None

    def complete_running_cancellation(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        now_us: int,
    ) -> JobRecord | None:
        return self._finish_running_job(
            job_id=job_id,
            lease_owner=lease_owner,
            fencing_token=fencing_token,
            now_us=now_us,
            target_state=JobState.CANCELLED,
            available_at_us=None,
            require_cancel=True,
            require_expired=False,
        )

    def record_running_failure(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        now_us: int,
        target_state: JobState,
        available_at_us: int | None,
    ) -> JobRecord | None:
        if target_state not in {JobState.RETRY_WAIT, JobState.FAILED}:
            raise JiejianError(ErrorCode.STORAGE_STATE, "任务失败目标状态无效")
        return self._finish_running_job(
            job_id=job_id,
            lease_owner=lease_owner,
            fencing_token=fencing_token,
            now_us=now_us,
            target_state=target_state,
            available_at_us=available_at_us,
            require_cancel=False,
            require_expired=False,
        )

    def record_waiting_failure(
        self,
        *,
        job_id: str,
        now_us: int,
    ) -> JobRecord | None:
        """仅把仍处于无租约等待态的指定 Job 原子结束为失败。"""

        changed_id = _scalar_value(
            self._session,
            update(JobRow)
            .where(
                JobRow.job_id == job_id,
                JobRow.state.in_(
                    (JobState.PENDING.value, JobState.RETRY_WAIT.value)
                ),
                JobRow.lease_owner.is_(None),
                JobRow.lease_expires_at_us.is_(None),
                JobRow.cancel_requested_at_us.is_(None),
                JobRow.updated_at_us <= now_us,
            )
            .values(
                state=JobState.FAILED.value,
                updated_at_us=now_us,
            )
            .returning(JobRow.job_id),
        )
        return self._jobs.get(changed_id) if changed_id is not None else None

    def list_expired_running(self, now_us: int, limit: int) -> tuple[JobRecord, ...]:
        rows = _scalars(
            self._session,
            select(JobRow.job_id)
            .where(
                JobRow.state == JobState.RUNNING.value,
                JobRow.lease_expires_at_us <= now_us,
            )
            .order_by(JobRow.lease_expires_at_us, JobRow.created_at_us, JobRow.job_id)
            .limit(limit),
        )
        return tuple(
            job
            for job_id in rows
            if (job := self._jobs.get(job_id)) is not None
        )

    def confirm_recovery(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        now_us: int,
        target_state: JobState,
        available_at_us: int | None,
    ) -> JobRecord | None:
        if target_state not in {JobState.RETRY_WAIT, JobState.FAILED}:
            raise JiejianError(ErrorCode.STORAGE_STATE, "任务恢复目标状态无效")
        return self._finish_running_job(
            job_id=job_id,
            lease_owner=lease_owner,
            fencing_token=fencing_token,
            now_us=now_us,
            target_state=target_state,
            available_at_us=available_at_us,
            require_cancel=False,
            require_expired=True,
        )

    def transition_run_terminal(
        self,
        run_id: str,
        target: RunLifecycle,
        now_us: int,
    ) -> RunRecord | None:
        if target not in {RunLifecycle.FAILED, RunLifecycle.CANCELLED}:
            raise JiejianError(ErrorCode.STORAGE_STATE, "运行终态无效")
        changed_id = _scalar_value(
            self._session,
            update(RunRow)
            .where(
                RunRow.run_id == run_id,
                RunRow.lifecycle.in_(_NONTERMINAL_RUNS),
                RunRow.verdict.is_(None),
                RunRow.updated_at_us <= now_us,
            )
            .values(
                lifecycle=target.value,
                verdict=None,
                updated_at_us=now_us,
                finished_at_us=now_us,
            )
            .returning(RunRow.run_id),
        )
        return self._runs.get(changed_id) if changed_id is not None else None

    def complete_published_result(
        self,
        *,
        job_id: str,
        run_id: str,
        attempt: int,
        lease_owner: str,
        fencing_token: int,
        lifecycle: RunLifecycle,
        verdict: RunVerdict | None,
        completed_at_us: int,
        require_active_lease: bool,
    ) -> tuple[JobRecord, RunRecord] | None:
        """仅为已发布结果执行 fenced Job/Run 完成态条件更新。"""

        if lifecycle not in {RunLifecycle.COMPLETED, RunLifecycle.SAFETY_STOPPED}:
            raise JiejianError(ErrorCode.STORAGE_STATE, "发布结果运行终态无效")
        if (lifecycle is RunLifecycle.COMPLETED) != (verdict is not None):
            raise JiejianError(ErrorCode.STORAGE_STATE, "发布结果结论矩阵无效")
        job_conditions = [
            JobRow.job_id == job_id,
            JobRow.run_id == run_id,
            JobRow.state == JobState.RUNNING.value,
            JobRow.attempt == attempt,
            JobRow.lease_owner == lease_owner,
            JobRow.fencing_token == fencing_token,
            JobRow.updated_at_us <= completed_at_us,
        ]
        if require_active_lease:
            job_conditions.append(JobRow.lease_expires_at_us > completed_at_us)
        changed_job_id = _scalar_value(
            self._session,
            update(JobRow)
            .where(and_(*job_conditions))
            .values(
                state=JobState.SUCCEEDED.value,
                lease_owner=None,
                lease_expires_at_us=None,
                updated_at_us=completed_at_us,
            )
            .returning(JobRow.job_id),
        )
        if changed_job_id is None:
            return None
        changed_run_id = _scalar_value(
            self._session,
            update(RunRow)
            .where(
                RunRow.run_id == run_id,
                RunRow.lifecycle.in_(_NONTERMINAL_RUNS),
                RunRow.verdict.is_(None),
                RunRow.updated_at_us <= completed_at_us,
            )
            .values(
                lifecycle=lifecycle.value,
                verdict=verdict.value if verdict is not None else None,
                updated_at_us=completed_at_us,
                finished_at_us=completed_at_us,
            )
            .returning(RunRow.run_id),
        )
        if changed_run_id is None:
            raise JiejianError(ErrorCode.STORAGE_STATE, "运行完成态条件不匹配")
        job = self._jobs.get(changed_job_id)
        run = self._runs.get(changed_run_id)
        if job is None or run is None:
            raise JiejianError(ErrorCode.STORAGE_STATE, "发布完成态读取失败")
        return job, run

    def complete_recording_result(
        self,
        *,
        job_id: str,
        recording_id: str,
        attempt: int,
        lease_owner: str,
        fencing_token: int,
        completed_at_us: int,
    ) -> JobRecord | None:
        """在当前有效 fence 下把已持久化录制结果标记为成功。"""

        changed_id = _scalar_value(
            self._session,
            update(JobRow)
            .where(
                JobRow.job_id == job_id,
                JobRow.recording_id == recording_id,
                JobRow.run_id.is_(None),
                JobRow.state == JobState.RUNNING.value,
                JobRow.attempt == attempt,
                JobRow.lease_owner == lease_owner,
                JobRow.fencing_token == fencing_token,
                JobRow.lease_expires_at_us > completed_at_us,
                JobRow.updated_at_us <= completed_at_us,
            )
            .values(
                state=JobState.SUCCEEDED.value,
                lease_owner=None,
                lease_expires_at_us=None,
                updated_at_us=completed_at_us,
            )
            .returning(JobRow.job_id),
        )
        return self._jobs.get(changed_id) if changed_id is not None else None

    def _finish_running_job(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        now_us: int,
        target_state: JobState,
        available_at_us: int | None,
        require_cancel: bool,
        require_expired: bool,
    ) -> JobRecord | None:
        conditions = [
            JobRow.job_id == job_id,
            JobRow.state == JobState.RUNNING.value,
            JobRow.lease_owner == lease_owner,
            JobRow.fencing_token == fencing_token,
            JobRow.updated_at_us <= now_us,
        ]
        conditions.append(
            JobRow.lease_expires_at_us <= now_us
            if require_expired
            else JobRow.lease_expires_at_us > now_us
        )
        if require_cancel:
            conditions.append(JobRow.cancel_requested_at_us.is_not(None))
        values: dict[str, Any] = {
            "state": target_state.value,
            "lease_owner": None,
            "lease_expires_at_us": None,
            "updated_at_us": now_us,
        }
        if available_at_us is not None:
            values["available_at_us"] = available_at_us
        changed_id = _scalar_value(
            self._session,
            update(JobRow)
            .where(and_(*conditions))
            .values(**values)
            .returning(JobRow.job_id),
        )
        return self._jobs.get(changed_id) if changed_id is not None else None


def _execute(session: Session, statement: Any) -> None:
    try:
        session.execute(statement)
        session.flush()
    except IntegrityError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "数据库约束拒绝写入") from None
    except SQLAlchemyError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None

def _scalar_value(session: Session, statement: Any) -> Any | None:
    try:
        value = session.execute(statement).scalar_one_or_none()
        session.flush()
        return value
    except IntegrityError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "数据库约束拒绝写入") from None
    except SQLAlchemyError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None


def _scalars(session: Session, statement: Select[Any]) -> tuple[Any, ...]:
    try:
        return tuple(session.execute(statement).scalars())
    except SQLAlchemyError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None
