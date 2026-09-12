# Worker 在同一 fenced 事务发布不可变检查包及索引；故障恢复只补交既有包，不再执行目标。
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.artifacts.check_packages import (
    MANIFEST_NAME, CheckPackage, check_final_directory, read_check_bytes,
    reject_check_links, validate_check_package,
)
from product.backend.infra.runtime.jobs.events import append_job_event
from product.backend.infra.artifacts.check_validation import validate_check_decisions
from product.backend.infra.runtime.jobs.models import JobEventType
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.storage.results.check_publications import CheckPublicationRecord
from product.backend.infra.storage.results.evidence import EvidenceIndexRecord
from product.protocols.check_publication import CheckPublicationManifest
from product.protocols.check_result import canonical_check_document


class CheckPublisher:
    """只接收当前检查包；以数据库写锁收敛并发发布，唯一收据收敛恢复重试。"""

    def __init__(self, var_dir: Path, uow_factory, *, clock_us=None):
        self._var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._clock_us = clock_us or (lambda: time.time_ns() // 1000)

    def publish(self, staging: Path, *, known_secrets=()) -> CheckPackage:
        reject_check_links(RuntimePaths(self._var_dir).jobs, staging)
        has_manifest = (staging / MANIFEST_NAME).exists()
        package = validate_check_package(staging, published=has_manifest, known_secrets=known_secrets)
        validate_check_decisions(package)
        result = package.result
        expected_staging = RuntimePaths(self._var_dir).jobs / result.job_id / "attempts" / f"{result.attempt}-{result.fencing_token}" / "staging"
        if staging != expected_staging:
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "Runner 结果关联信息不匹配")
        final = check_final_directory(self._var_dir, package.request.project_id, result.run_id)
        if final.exists():
            existing = validate_check_package(final, published=True, known_secrets=known_secrets)
            if existing.result != result or existing.files != package.files:
                raise JiejianError(ErrorCode.ARTIFACT_FENCE, "Runner 结果关联信息不匹配")
            return self.complete_existing(final, known_secrets=known_secrets)
        now = self._clock_us()
        with self._uow_factory(known_secrets=known_secrets) as work:
            job = self._validate_job(work, package)
            if job.lease_expires_at_us is None or now >= job.lease_expires_at_us or result.completed_at_us > now:
                raise JiejianError(ErrorCode.ARTIFACT_FENCE, "Runner 结果关联信息不匹配")
            manifest = package.manifest or CheckPublicationManifest(project_id=job.project_id, run_id=result.run_id, job_id=result.job_id,
                attempt=result.attempt, lease_owner=result.lease_owner, fencing_token=result.fencing_token,
                lease_expires_at_us=job.lease_expires_at_us, published_at_us=now,
                request_hash=result.request_hash, config_hash=result.config_hash,
                result_hash=next(item.sha256 for item in package.files if item.path == "result.json"), files=package.files)
            raw = canonical_check_document(manifest, known_secrets=tuple(known_secrets))
            self._complete(work, package, manifest, raw, now, recovery=False)
            # CAS 已持有写锁；文件提升后事务失败会留下唯一不可变 manifest，供后续恢复核验。
            final.parent.mkdir(parents=True, exist_ok=True)
            reject_check_links(RuntimePaths(self._var_dir).projects, final)
            manifest_path = staging / MANIFEST_NAME
            if not has_manifest:
                with manifest_path.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            try:
                os.rename(staging, final)
            except OSError:
                raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "工件目录原子发布失败") from None
            work.commit()
        return validate_check_package(final, published=True, known_secrets=known_secrets)

    def complete_existing(self, directory: Path, *, known_secrets=()) -> CheckPackage:
        """仅恢复精确 manifest 的数据库提交；旧 fence、取消和文件漂移仍拒绝。"""
        package = validate_check_package(directory, published=True, known_secrets=known_secrets)
        manifest = package.manifest
        if directory != check_final_directory(self._var_dir, manifest.project_id, manifest.run_id):
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "Runner 结果关联信息不匹配")
        raw = read_check_bytes(directory / MANIFEST_NAME, known_secrets=known_secrets)
        digest = hashlib.sha256(raw).hexdigest()
        with self._uow_factory(known_secrets=known_secrets) as work:
            receipt = work.check_publications.get(manifest.run_id)
            if receipt is not None:
                if (receipt.job_id, receipt.attempt, receipt.fencing_token, receipt.request_hash,
                    receipt.result_hash, receipt.manifest_hash, receipt.published_at_us) != (
                    manifest.job_id, manifest.attempt, manifest.fencing_token, manifest.request_hash,
                    manifest.result_hash, digest, manifest.published_at_us
                ):
                    raise JiejianError(ErrorCode.ARTIFACT_FENCE, "Runner 结果关联信息不匹配")
                self._validate_receipt_state(work, package)
                return package
            self._validate_job(work, package)
            validate_check_decisions(package)
            self._complete(work, package, manifest, raw, self._clock_us(), recovery=True)
            work.commit()
        return package

    def _validate_job(self, work, package):
        result, request = package.result, package.request
        job = work.jobs.get(result.job_id)
        run = work.runs.get(result.run_id)
        if job is None or run is None or job.state is not JobState.RUNNING or (
            job.operation_type, job.run_id, job.project_id, job.attempt, job.lease_owner,
            job.fencing_token, job.request_hash, job.cancel_requested_at_us
        ) != ("CHECK", result.run_id, request.project_id, result.attempt, result.lease_owner,
            result.fencing_token, result.request_hash, None) or (
            run.project_id, run.request_hash, run.plan_fingerprint, run.source_fingerprint, run.policy_epoch, run.engine_version
        ) != (request.project_id, result.request_hash, request.plan_fingerprint, request.source_fingerprint,
            request.policy_epoch, request.engine_version):
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "Runner 结果关联信息不匹配")
        if result.result_type not in ("SUCCESS", "SAFETY_STOPPED"):
            raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "该结果类型不得发布完成态")
        return job

    def _complete(self, work, package, manifest, manifest_raw, now, *, recovery):
        result = package.result
        changed = work.job_control.complete_published_result(job_id=result.job_id, run_id=result.run_id,
            attempt=result.attempt, lease_owner=result.lease_owner, fencing_token=result.fencing_token,
            lifecycle=result.lifecycle, verdict=result.verdict, completed_at_us=now,
            require_active_lease=not recovery, request_hash=result.request_hash,
            published_at_us=manifest.published_at_us if recovery else None)
        if changed is None:
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "Runner 结果关联信息不匹配")
        files = {item.path: item for item in package.files}
        for evidence in package.evidence:
            relative = f"evidence/{evidence.evidence_id}.json"
            work.evidence.add(EvidenceIndexRecord(evidence_id=evidence.evidence_id, run_id=result.run_id,
                case_id=evidence.case.case_id, artifact_path=relative, sha256=evidence.evidence_id[3:],
                byte_count=files[relative].byte_count, created_at_us=manifest.published_at_us))
        work.check_publications.add(CheckPublicationRecord(run_id=result.run_id, job_id=result.job_id,
            attempt=result.attempt, fencing_token=result.fencing_token, request_hash=result.request_hash,
            result_hash=manifest.result_hash, manifest_hash=hashlib.sha256(manifest_raw).hexdigest(),
            published_at_us=manifest.published_at_us))
        append_job_event(work, job=changed[0], event_type=JobEventType.JOB_SUCCEEDED,
            source_state=JobState.RUNNING, target_state=JobState.SUCCEEDED, occurred_at_us=now,
            metadata={"attempt": result.attempt, "fencing_token": result.fencing_token})

    def _validate_receipt_state(self, work, package):
        result = package.result
        run, job = work.runs.get(result.run_id), work.jobs.get(result.job_id)
        if run is None or job is None or (run.lifecycle, run.verdict, run.request_hash,
            job.state, job.attempt, job.fencing_token, job.request_hash) != (
            result.lifecycle, result.verdict, result.request_hash, JobState.SUCCEEDED,
            result.attempt, result.fencing_token, result.request_hash
        ):
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "Runner 结果关联信息不匹配")
