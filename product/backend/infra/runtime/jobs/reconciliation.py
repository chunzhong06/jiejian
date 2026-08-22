# =============================================================================
# Execution publication 对账恢复
#
# 定位
#   修复“最终目录已发布、数据库仍未完成”崩溃窗口的恢复边界
#
# 职责
#   验证已发布工件｜幂等提交完成态｜隔离不可信或孤立 staging
#
# 边界
#   不修补损坏 publication；身份、hash 或 fence 不一致时只隔离并报告。
#
# 调用链
#   VerificationRunJobHandler → RunReconciler → Publication / quarantine
# =============================================================================

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.lifecycle import JobState
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import JobRecord, StorageUnitOfWork
from product.backend.infra.artifacts.run_publication import RunPublisher
from product.backend.infra.artifacts.run_packages import PUBLICATION_MANIFEST_NAME, StagedAttempt, attempt_paths_for, validate_published_run, validate_runner_staging
from product.backend.infra.runtime.paths import RuntimePaths


class ReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1"] = "1"
    published_completed: int = Field(ge=0)
    published_already_complete: int = Field(ge=0)
    published_quarantined: int = Field(ge=0)
    staging_quarantined: int = Field(ge=0)
    active_staging: int = Field(ge=0)
    recovery_required: int = Field(ge=0)


class RunReconciler:
    """不重跑目标流量，只补事务或把失效目录移入 quarantine。"""

    def __init__(
        self,
        var_dir: Path,
        uow_factory: Callable[..., StorageUnitOfWork],
        publication_service: RunPublisher,
        *,
        utc_now_us: Callable[[], int] | None = None,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._publication = publication_service
        self._utc_now_us = utc_now_us or (lambda: time.time_ns() // 1_000)

    def reconcile(
        self,
        *,
        known_secrets: Sequence[str] = (),
    ) -> ReconciliationResult:
        """核对数据库与 staging/publication 工件，隔离损坏内容并补齐可证明的终态。"""

        counts = {
            "published_completed": 0,
            "published_already_complete": 0,
            "published_quarantined": 0,
            "staging_quarantined": 0,
            "active_staging": 0,
            "recovery_required": 0,
        }
        # 已发布事实优先：只有完整性成立的 publication 才能反向完成数据库状态。
        self._reconcile_published(counts, known_secrets)
        self._reconcile_staging(counts, known_secrets)
        return ReconciliationResult(schema_version="1", **counts)

    def _reconcile_published(
        self,
        counts: dict[str, int],
        known_secrets: Sequence[str],
    ) -> None:
        projects_root = RuntimePaths(self.var_dir).projects
        if not projects_root.is_dir():
            return
        for final_dir in sorted(projects_root.glob("*/runs/*")):
            if not (final_dir / PUBLICATION_MANIFEST_NAME).is_file():
                continue
            try:
                validated = validate_published_run(
                    final_dir,
                    known_secrets=known_secrets,
                )
                job = self._read_job(validated.manifest.job_id)
                was_complete = job is not None and job.state is JobState.SUCCEEDED
                self._publication.complete_existing(
                    final_dir,
                    known_secrets=known_secrets,
                    require_active_lease=False,
                )
                key = (
                    "published_already_complete" if was_complete else "published_completed"
                )
                counts[key] += 1
            except JiejianError as exc:
                if exc.code in {
                    ErrorCode.STORAGE_FAILURE.value,
                    ErrorCode.STORAGE_CONSTRAINT.value,
                }:
                    raise
                self._quarantine(final_dir, "published")
                counts["published_quarantined"] += 1

    def _reconcile_staging(
        self,
        counts: dict[str, int],
        known_secrets: Sequence[str],
    ) -> None:
        jobs_root = RuntimePaths(self.var_dir).jobs
        if not jobs_root.is_dir():
            return
        for staging in sorted(jobs_root.glob("job_*/attempts/*/staging")):
            job_id = staging.parents[2].name
            job = self._read_job(job_id)
            attempt_token = staging.parent.name.split("-", 1)
            try:
                attempt, token = (int(item) for item in attempt_token)
            except (TypeError, ValueError):
                self._quarantine(staging, "staging")
                counts["staging_quarantined"] += 1
                continue
            if (
                job is None
                or job.attempt != attempt
                or job.fencing_token != token
                or job.state is not JobState.RUNNING
            ):
                self._quarantine(staging, "staging")
                counts["staging_quarantined"] += 1
                continue
            if job.lease_expires_at_us is None or job.lease_expires_at_us <= self._utc_now_us():
                counts["recovery_required"] += 1
                continue
            paths = attempt_paths_for(self.var_dir, job)
            if not (staging / PUBLICATION_MANIFEST_NAME).is_file():
                counts["active_staging"] += 1
                continue
            try:
                result, _ = validate_runner_staging(
                    paths,
                    job,
                    known_secrets=known_secrets,
                    require_receipt=True,
                )
                self._publication.publish(
                    StagedAttempt(result=result, paths=paths),
                    known_secrets=known_secrets,
                )
                counts["published_completed"] += 1
            except JiejianError as exc:
                if exc.code in {
                    ErrorCode.STORAGE_FAILURE.value,
                    ErrorCode.STORAGE_CONSTRAINT.value,
                }:
                    raise
                self._quarantine(staging, "staging")
                counts["staging_quarantined"] += 1

    def _read_job(self, job_id: str) -> JobRecord | None:
        with self._uow_factory() as work:
            return work.jobs.get(job_id)

    def _quarantine(self, path: Path, category: str) -> None:
        quarantine_root = Path(os.path.abspath(RuntimePaths(self.var_dir).data / "quarantine" / category))
        source = Path(os.path.abspath(path))
        if os.path.commonpath((self.var_dir, source)) != str(self.var_dir):
            raise JiejianError(ErrorCode.ARTIFACT_RECONCILE, "隔离源路径越界")
        quarantine_root.mkdir(parents=True, exist_ok=True)
        destination = quarantine_root / f"{path.name}-{uuid4().hex}"
        try:
            os.replace(source, destination)
        except OSError:
            raise JiejianError(ErrorCode.ARTIFACT_RECONCILE, "孤儿工件隔离失败") from None
