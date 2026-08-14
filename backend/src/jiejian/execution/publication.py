# =============================================================================
# Execution Run 发布
#
# 定位
#   可信 staging 与数据库完成态之间的原子 publication 边界
#
# 职责
#   重验当前 fence｜原子 promote 最终目录｜在同一事务写 Run/Job/Evidence 完成态
#
# 调用链
#   WorkerSupervisor / Reconciliation → RunPublicationService → filesystem / StorageUnitOfWork
# =============================================================================

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from ..domain.lifecycle import JobState
from ..errors import ErrorCode, JiejianError
from ..protocols import RunnerResultType, RunnerResultV1, RunnerResultV2, StagedArtifactV1
from ..storage import JobRecord, StorageUnitOfWork
from .events import append_job_event
from .models import JobEventType
from .published_artifacts import (
    PUBLICATION_MANIFEST_NAME,
    PublicationManifestV1,
    StagedAttempt,
    ValidatedPublication,
    evidence_records_for_publication,
    final_run_dir,
    read_publication_manifest,
    reject_reparse_parents,
    validate_published_run,
    validate_runner_staging,
    write_publication_manifest,
)

_TERMINAL_PUBLISH_TYPES = {
    RunnerResultType.SUCCESS,
    RunnerResultType.SAFETY_STOPPED,
}


class RunPublicationService:
    """在有效 fence 下发布目录，并在发布后提交数据库完成态。"""

    def __init__(
        self,
        var_dir: Path,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        utc_now_us: Callable[[], int] | None = None,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._utc_now_us = utc_now_us or (lambda: time.time_ns() // 1_000)

    def publish(
        self,
        staged: StagedAttempt,
        *,
        known_secrets: Sequence[str] = (),
    ) -> StagedAttempt:
        """重新验证可信 staging，原子 promote 后提交完成态。"""

        now_us = self._utc_now_us()
        job = self._running_job(staged.result.job_id, now_us, require_active_lease=True)
        result, files = validate_runner_staging(
            staged.paths,
            job,
            known_secrets=known_secrets,
            require_receipt=True,
        )
        if result.result_type.value not in {"SUCCESS", "SAFETY_STOPPED"}:
            raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "该结果类型不得发布完成态")
        final_dir = final_run_dir(self.var_dir, job.project_id, job.run_id)
        if final_dir.exists():
            existing = self.complete_existing(
                final_dir,
                known_secrets=known_secrets,
                require_active_lease=False,
            )
            if (
                existing.result.job_id != result.job_id
                or existing.result.attempt != result.attempt
                or existing.result.fencing_token != result.fencing_token
            ):
                raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "最终运行目录已被占用")
        else:
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            reject_reparse_parents(self.var_dir, final_dir.parent)
            self._prepare_manifest(staged.paths.staging_dir, job, result, files, now_us)
            try:
                os.replace(staged.paths.staging_dir, final_dir)
            except OSError:
                raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "工件目录原子发布失败") from None
            existing = self.complete_existing(
                final_dir,
                known_secrets=known_secrets,
                require_active_lease=True,
            )
        published_paths = replace(
            staged.paths,
            staging_dir=final_dir,
            result_path=final_dir / "result.json",
        )
        return StagedAttempt(result=existing.result, paths=published_paths)

    def complete_existing(
        self,
        final_dir: Path,
        *,
        known_secrets: Sequence[str] = (),
        require_active_lease: bool,
    ) -> ValidatedPublication:
        """校验已发布目录，并幂等补齐其数据库事务。"""

        validated = validate_published_run(final_dir, known_secrets=known_secrets)
        manifest = validated.manifest
        result = validated.result
        with self._uow_factory(known_secrets=known_secrets) as work:
            job = work.jobs.get(manifest.job_id)
            run = work.runs.get(manifest.run_id)
            if job is None or run is None:
                raise JiejianError(ErrorCode.ARTIFACT_RECONCILE, "发布记录缺少数据库对象")
            if (
                job.attempt != manifest.attempt
                or job.fencing_token != manifest.fencing_token
                or job.run_id != manifest.run_id
                or job.project_id != manifest.project_id
            ):
                raise JiejianError(ErrorCode.ARTIFACT_FENCE, "发布记录 fencing 已失效")
            existing_evidence = work.evidence.list_for_run(run.run_id)
            expected_evidence = evidence_records_for_publication(
                final_dir,
                result,
                created_at_us=max(manifest.published_at_us, result.finished_at_us),
                known_secrets=known_secrets,
            )
            if job.state is JobState.SUCCEEDED:
                if (
                    run.lifecycle is not result.run_lifecycle
                    or run.verdict is not result.verdict
                    or tuple(existing_evidence) != expected_evidence
                ):
                    raise JiejianError(ErrorCode.ARTIFACT_RECONCILE, "发布完成态不一致")
                return validated
            completed_at_us = max(
                self._utc_now_us(),
                job.updated_at_us,
                run.updated_at_us,
                result.finished_at_us,
            )
            changed = work.job_control.complete_published_result(
                job_id=job.job_id,
                run_id=run.run_id,
                attempt=manifest.attempt,
                lease_owner=manifest.lease_owner,
                fencing_token=manifest.fencing_token,
                lifecycle=result.run_lifecycle,
                verdict=result.verdict,
                completed_at_us=completed_at_us,
                require_active_lease=require_active_lease,
            )
            if changed is None:
                raise JiejianError(ErrorCode.ARTIFACT_FENCE, "发布完成态条件不匹配")
            for record in expected_evidence:
                work.evidence.add(record)
            append_job_event(
                work,
                job=job,
                event_type=JobEventType.JOB_SUCCEEDED,
                source_state=JobState.RUNNING,
                target_state=JobState.SUCCEEDED,
                occurred_at_us=completed_at_us,
                metadata={
                    "attempt": manifest.attempt,
                    "fencing_token": manifest.fencing_token,
                    "result_type": result.result_type.value,
                    "verdict": result.verdict.value if result.verdict is not None else None,
                },
            )
            work.commit()
        return validated

    def _running_job(
        self,
        job_id: str,
        now_us: int,
        *,
        require_active_lease: bool,
    ) -> JobRecord:
        with self._uow_factory() as work:
            job = work.jobs.get(job_id)
        if job is None:
            raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")
        if (
            job.state is not JobState.RUNNING
            or job.lease_owner is None
            or job.lease_expires_at_us is None
            or (require_active_lease and job.lease_expires_at_us <= now_us)
        ):
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "当前任务租约不可发布")
        return job

    def _prepare_manifest(
        self,
        staging_dir: Path,
        job: JobRecord,
        result: RunnerResultV1 | RunnerResultV2,
        files: tuple[StagedArtifactV1, ...],
        now_us: int,
    ) -> PublicationManifestV1:
        if job.lease_owner is None or job.lease_expires_at_us is None:
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "当前任务没有发布租约")
        manifest_path = staging_dir / PUBLICATION_MANIFEST_NAME
        result_hash = hashlib.sha256((staging_dir / "result.json").read_bytes()).hexdigest()
        if manifest_path.exists():
            manifest = read_publication_manifest(manifest_path)
            if (
                manifest.project_id != job.project_id
                or manifest.job_id != job.job_id
                or manifest.run_id != job.run_id
                or manifest.attempt != job.attempt
                or manifest.lease_owner != job.lease_owner
                or manifest.fencing_token != job.fencing_token
                or manifest.lease_expires_at_us != job.lease_expires_at_us
                or manifest.result_sha256 != result_hash
                or manifest.files != files
            ):
                raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "暂存发布清单不匹配")
            return manifest
        manifest = PublicationManifestV1(
            schema_version="1",
            project_id=job.project_id,
            run_id=job.run_id,
            job_id=job.job_id,
            attempt=job.attempt,
            lease_owner=job.lease_owner,
            fencing_token=job.fencing_token,
            lease_expires_at_us=job.lease_expires_at_us,
            published_at_us=now_us,
            result_sha256=result_hash,
            files=files,
        )
        write_publication_manifest(manifest_path, manifest)
        return manifest
