# =============================================================================
# Project 归档生命周期服务
#
# 定位
#   普通用户“移除应用”与既有 Project 历史之间的业务编排边界。
#
# 职责
#   拒绝活动任务｜清理当前测试身份秘密｜将 Project 置为 ARCHIVED。
#
# 边界
#   不删除源码、Project、Run、Evidence、Finding、Report 或历史准备元数据；恢复由同源目录再次接入完成。
#
# 调用链
#   GUI / CLI / API → ProjectLifecycleService → UoW + TestIdentityService
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState, ProjectStatus, RunLifecycle
from product.backend.core.recording import RecordingState
from product.backend.infra.storage import ProjectRecord, StorageUnitOfWork
from product.backend.workflows.test_identities import TestIdentityService


_ACTIVE_JOB_STATES = {JobState.PENDING, JobState.RUNNING, JobState.RETRY_WAIT}
_ACTIVE_RUN_STATES = {RunLifecycle.QUEUED, RunLifecycle.RUNNING}
_TERMINAL_RECORDING_STATES = {
    RecordingState.COMPLETED,
    RecordingState.FAILED,
    RecordingState.CANCELLED,
    RecordingState.SAFETY_STOPPED,
}


class ProjectLifecycleService:
    """把移除应用收敛为可恢复、保留历史的 ARCHIVED 生命周期。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        test_identities: TestIdentityService,
        *,
        stop_official_sample: Callable[[str], bool],
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._test_identities = test_identities
        self._stop_official_sample = stop_official_sample
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)

    def archive(self, project_id: str) -> ProjectRecord:
        """移除当前应用视图；任何活动执行事实都使操作 fail-closed。"""

        project = self._require_archivable(project_id)
        if project.status is ProjectStatus.ARCHIVED:
            return project

        # 空闲官方体验属于 Project 的会话资源，移除应用时先走正式体验收口。
        self._stop_official_sample(project_id)
        # 先删除安全存储中的当前凭据；失败时不得推进 Project 状态。
        self._test_identities.remove_project_credentials(project_id)
        project = self._require_archivable(project_id)
        archived = ProjectRecord(
            **(
                project.model_dump()
                | {
                    "status": ProjectStatus.ARCHIVED,
                    "updated_at_us": max(self._clock_us(), project.updated_at_us),
                }
            )
        )
        with self._uow_factory() as work:
            current = work.projects.get(project_id)
            if current is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            if current.status is ProjectStatus.ARCHIVED:
                return current
            work.projects.replace(archived)
            work.commit()
        return archived

    def _require_archivable(self, project_id: str) -> ProjectRecord:
        with self._uow_factory() as work:
            project = work.projects.get(project_id)
            if project is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            active_runs = tuple(
                item.run_id
                for item in work.runs.list_for_project(project_id)
                if item.lifecycle in _ACTIVE_RUN_STATES
            )
            active_recordings = tuple(
                item.recording_id
                for item in work.recordings.list_for_project(project_id)
                if item.state not in _TERMINAL_RECORDING_STATES
            )
            active_jobs = tuple(
                item.job_id
                for item in work.jobs.list_for_project(project_id)
                if item.state in _ACTIVE_JOB_STATES
            )
        if active_runs or active_recordings or active_jobs:
            raise JiejianError(
                ErrorCode.PROJECT_ARCHIVE_CONFLICT,
                "应用仍有活动检查、录制或后台任务，请先结束后再移除",
                details={
                    "active_run_count": len(active_runs),
                    "active_recording_count": len(active_recordings),
                    "active_job_count": len(active_jobs),
                },
            )
        return project


__all__ = ["ProjectLifecycleService"]
