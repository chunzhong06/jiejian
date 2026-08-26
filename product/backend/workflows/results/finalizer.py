# =============================================================================
# ResultFinalizer 结果最终化
#
# 定位
#   在可信 Run publication 之后串行整理 Finding/Occurrence 与派生状态
#
# 职责
#   校验 publication 身份｜按项目顺序调度 FindingMaterializer｜恢复和 repair
#
# 边界
#   只读 PublishedResultReader 的可信 View；不访问 Target、Verification、Worker、Runner、浏览器或秘密。
#
# 调用链
#   RunPublisher / 控制面 → ResultFinalizer → FindingMaterializer / Storage
# =============================================================================

from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Callable, Iterator

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import RunLifecycle
from product.backend.infra.artifacts.run_publication import publication_manifest_sha256
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.lock import try_lock_stream, unlock_stream
from product.backend.infra.storage import (
    BaseReportFinalizationState,
    FindingFinalizationState,
    RunFinalizationRecord,
    StorageUnitOfWork,
)
from product.backend.workflows.results.findings import FindingMaterializer
from product.backend.workflows.results.published import PublishedResultReader, PublishedRunView


class ResultFinalizer:
    """在单机全局锁内幂等推进 Finding 派生状态，不改变 Run 或 Evidence。"""

    def __init__(
        self,
        var_dir: Path,
        uow_factory: Callable[..., StorageUnitOfWork],
        published_reader: PublishedResultReader,
        materializer: FindingMaterializer,
        *,
        report_builder,
        utc_now_us: Callable[[], int] | None = None,
    ) -> None:
        self._var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._reader = published_reader
        self._materializer = materializer
        self._reports = report_builder
        self._utc_now_us = utc_now_us or (lambda: time.time_ns() // 1_000)

    def status(self, run_id: str) -> RunFinalizationRecord:
        with self._uow_factory() as work:
            record = work.finalizations.get(run_id)
        if record is None:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
        return record

    def finalize(self, run_id: str) -> RunFinalizationRecord:
        """获取全局锁后补齐目标 Run 及其更早同项目 Run。"""

        with self._global_lock() as acquired:
            if not acquired:
                return self.status(run_id)
            run = self._run(run_id)
            return self._process_project(run.project_id, target_run_id=run_id)

    def reconcile(self) -> dict[str, int]:
        """恢复缺失、PENDING 或遗留 RUNNING；不自动重试 FAILED。"""

        with self._global_lock() as acquired:
            if not acquired:
                return {"locked": 1, "processed": 0, "failed": 0, "blocked": 0}
            with self._uow_factory() as work:
                project_ids = tuple(item.project_id for item in work.projects.list_all())
            counts = {"locked": 0, "processed": 0, "failed": 0, "blocked": 0}
            for project_id in project_ids:
                try:
                    self._process_project(project_id, counts=counts)
                except JiejianError as exc:
                    if exc.code in {
                        ErrorCode.STORAGE_CONSTRAINT.value,
                        ErrorCode.STORAGE_FAILURE.value,
                        ErrorCode.STORAGE_STATE.value,
                    }:
                        raise
                    counts["failed"] += 1
            return counts

    def repair(self, run_id: str) -> RunFinalizationRecord:
        """只重置可信终态 Run 的 FAILED/BLOCKED 派生状态，然后继续项目顺序。"""

        with self._global_lock() as acquired:
            if not acquired:
                return self.status(run_id)
            run = self._run(run_id)
            if run.lifecycle not in {RunLifecycle.COMPLETED, RunLifecycle.SAFETY_STOPPED}:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_READY, "当前 Run 尚无可信 publication")
            _, record = self._load_or_initialize(run_id)
            if record.findings_state in {FindingFinalizationState.FAILED, FindingFinalizationState.BLOCKED}:
                with self._uow_factory() as work:
                    current = work.finalizations.get(run_id)
                    if current is None:
                        raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
                    work.finalizations.save(
                        _evolve(
                            current,
                            findings_state=FindingFinalizationState.PENDING,
                            findings_error_code=None,
                            blocked_by_run_id=None,
                            updated_at_us=self._utc_now_us(),
                        )
                    )
                    work.commit()
            elif record.base_report_state is BaseReportFinalizationState.FAILED:
                with self._uow_factory() as work:
                    current = work.finalizations.get(run_id)
                    if current is None:
                        raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
                    work.finalizations.save(
                        _evolve(
                            current,
                            base_report_state=BaseReportFinalizationState.PENDING,
                            base_report_error_code=None,
                            updated_at_us=self._utc_now_us(),
                        )
                    )
                    work.commit()
            # 即使目标本身已经 COMPLETE，也继续扫描并解除由它历史失败造成的后续 BLOCKED；
            # 返回值仍固定对应用户明确 repair 的 Run。
            self._process_project(run.project_id)
            return self.status(run_id)

    @contextmanager
    def _global_lock(self) -> Iterator[bool]:
        path = RuntimePaths(self._var_dir).locks / "result-finalization.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("a+b")
        acquired = try_lock_stream(stream)
        try:
            yield acquired
        finally:
            if acquired:
                unlock_stream(stream)
            stream.close()

    def _run(self, run_id: str):
        with self._uow_factory() as work:
            run = work.runs.get(run_id)
        if run is None:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
        return run

    def _process_project(
        self,
        project_id: str,
        *,
        target_run_id: str | None = None,
        counts: dict[str, int] | None = None,
    ) -> RunFinalizationRecord:
        with self._uow_factory() as work:
            runs = work.runs.list_finished_for_project(project_id)
        target_index = len(runs) - 1
        if target_run_id is not None:
            target_index = next((index for index, run in enumerate(runs) if run.run_id == target_run_id), -1)
            if target_index < 0:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_READY, "当前 Run 尚无可信 publication")
        blocked_by: str | None = None
        selected: RunFinalizationRecord | None = None
        for index, run in enumerate(runs):
            if index > target_index:
                break
            try:
                view, record = self._load_or_initialize(run.run_id)
            except JiejianError:
                try:
                    failed = self.status(run.run_id)
                except JiejianError:
                    if target_run_id == run.run_id:
                        raise
                else:
                    if failed.findings_state is FindingFinalizationState.FAILED:
                        selected = failed
                        blocked_by = run.run_id
                        if counts is not None:
                            counts["failed"] += 1
                        continue
                    if target_run_id == run.run_id:
                        raise
                blocked_by = run.run_id
                if counts is not None:
                    counts["failed"] += 1
                continue
            if blocked_by is not None:
                record = self._block(run.run_id, blocked_by, record)
                if counts is not None:
                    counts["blocked"] += 1
                selected = record
                continue
            if record.findings_state is FindingFinalizationState.COMPLETE:
                selected = self._process_base_report(run.run_id, record)
                continue
            if record.findings_state is FindingFinalizationState.FAILED:
                blocked_by = run.run_id
                selected = record
                if counts is not None:
                    counts["failed"] += 1
                continue
            if record.findings_state is FindingFinalizationState.BLOCKED:
                # 扫描到这里仍没有前序失败，说明原阻断源已经由显式 repair 修复；
                # 只有此时才允许把派生状态恢复到 PENDING 并继续稳定顺序。
                record = self._reset_pending(record)
            try:
                self._mark_running(record)
                self._materializer.materialize(view)
                selected = self._process_base_report(run.run_id, self.status(run.run_id))
                if counts is not None:
                    counts["processed"] += 1
            except Exception as exc:
                failed = self._fail(run.run_id, _stable_failure_code(exc))
                selected = failed
                blocked_by = run.run_id
                if counts is not None:
                    counts["failed"] += 1
        if selected is None:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
        if target_run_id is not None and selected.run_id != target_run_id:
            return self.status(target_run_id)
        return selected

    def _process_base_report(self, run_id: str, record: RunFinalizationRecord) -> RunFinalizationRecord:
        """Finding 完成后推进 Base 报告；报告失败不回滚 Finding。"""

        if record.base_report_state is BaseReportFinalizationState.BLOCKED:
            return record
        if record.base_report_state is BaseReportFinalizationState.FAILED:
            return record
        if record.base_report_state is BaseReportFinalizationState.COMPLETE:
            try:
                payload = self._reports.read(run_id, record.base_report_id)
            except Exception as exc:
                return self._fail_report(run_id, _stable_failure_code(exc))
            if (
                payload.get("report_type") != "BASE"
                or payload.get("report_id") != record.base_report_id
                or payload.get("semantic_input_sha256") != record.base_report_input_sha256
            ):
                return self._fail_report(run_id, ErrorCode.REPORT_INTEGRITY.value)
            return record
        self._mark_report_running(record)
        try:
            report = self._reports.generate_base(run_id)
            current = self.status(run_id)
            completed = _evolve(
                current,
                base_report_state=BaseReportFinalizationState.COMPLETE,
                base_report_error_code=None,
                base_report_input_sha256=report.semantic_input_sha256,
                base_report_id=report.report_id,
                base_report_completed_at_us=self._utc_now_us(),
                updated_at_us=self._utc_now_us(),
            )
            with self._uow_factory() as work:
                work.finalizations.save(completed)
                work.commit()
            return completed
        except Exception as exc:
            return self._fail_report(run_id, _stable_failure_code(exc))

    def _mark_report_running(self, record: RunFinalizationRecord) -> RunFinalizationRecord:
        with self._uow_factory() as work:
            current = work.finalizations.get(record.run_id)
            if current is None:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
            running = _evolve(
                current,
                base_report_state=BaseReportFinalizationState.RUNNING,
                base_report_attempt=current.base_report_attempt + 1,
                updated_at_us=self._utc_now_us(),
            )
            work.finalizations.save(running)
            work.commit()
            return running

    def _fail_report(self, run_id: str, code: str) -> RunFinalizationRecord:
        with self._uow_factory() as work:
            current = work.finalizations.get(run_id)
            if current is None:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
            failed = _evolve(
                current,
                base_report_state=BaseReportFinalizationState.FAILED,
                base_report_error_code=code,
                base_report_input_sha256=None,
                base_report_id=None,
                base_report_completed_at_us=None,
                updated_at_us=self._utc_now_us(),
            )
            work.finalizations.save(failed)
            work.commit()
            return failed

    def _load_or_initialize(self, run_id: str) -> tuple[PublishedRunView, RunFinalizationRecord]:
        with self._uow_factory() as work:
            existing = work.finalizations.get(run_id)
        try:
            view = self._reader.read(run_id)
        except JiejianError as exc:
            if existing is not None:
                self._fail(run_id, _stable_failure_code(exc))
            raise
        publication_sha256 = publication_manifest_sha256(view.publication.manifest)
        if existing is not None and existing.publication_sha256 != publication_sha256:
            self._fail(run_id, ErrorCode.ARTIFACT_HASH_MISMATCH.value)
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_CONFLICT, "publication 摘要发生变化")
        with self._uow_factory() as work:
            record = work.finalizations.ensure_initial(
                run_id,
                publication_sha256,
                max(view.publication.manifest.published_at_us, view.publication.result.finished_at_us),
            )
            work.commit()
        return view, record

    def _mark_running(self, record: RunFinalizationRecord) -> None:
        with self._uow_factory() as work:
            current = work.finalizations.get(record.run_id)
            if current is None:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
            work.finalizations.save(
                _evolve(
                    current,
                    findings_state=FindingFinalizationState.RUNNING,
                    findings_attempt=current.findings_attempt + 1,
                    updated_at_us=self._utc_now_us(),
                )
            )
            work.commit()

    def _reset_pending(self, record: RunFinalizationRecord) -> RunFinalizationRecord:
        """仅在稳定顺序已证明前序恢复后解除历史 BLOCKED。"""

        with self._uow_factory() as work:
            current = work.finalizations.get(record.run_id)
            if current is None:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
            pending = _evolve(
                current,
                findings_state=FindingFinalizationState.PENDING,
                findings_error_code=None,
                blocked_by_run_id=None,
                updated_at_us=self._utc_now_us(),
            )
            work.finalizations.save(pending)
            work.commit()
            return pending

    def _fail(self, run_id: str, code: str) -> RunFinalizationRecord:
        with self._uow_factory() as work:
            current = work.finalizations.get(run_id)
            if current is None:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
            if current.findings_state is FindingFinalizationState.COMPLETE:
                return current
            failed = _evolve(
                current,
                findings_state=FindingFinalizationState.FAILED,
                findings_error_code=code,
                findings_snapshot_sha256=None,
                findings_completed_at_us=None,
                blocked_by_run_id=None,
                updated_at_us=self._utc_now_us(),
            )
            work.finalizations.save(failed)
            work.commit()
            return failed

    def _block(self, run_id: str, blocked_by_run_id: str, record: RunFinalizationRecord) -> RunFinalizationRecord:
        if record.findings_state is FindingFinalizationState.COMPLETE:
            return record
        with self._uow_factory() as work:
            current = work.finalizations.get(run_id)
            if current is None:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
            blocked = _evolve(
                current,
                findings_state=FindingFinalizationState.BLOCKED,
                findings_error_code=ErrorCode.RESULT_FINALIZATION_BLOCKED.value,
                findings_snapshot_sha256=None,
                findings_completed_at_us=None,
                blocked_by_run_id=blocked_by_run_id,
                updated_at_us=self._utc_now_us(),
            )
            work.finalizations.save(blocked)
            work.commit()
            return blocked


def _stable_failure_code(error: Exception) -> str:
    """持久化底层稳定错误码；RESULT_FINALIZATION_* 只用于调用边界。"""

    if isinstance(error, JiejianError):
        return error.code
    return ErrorCode.STORAGE_FAILURE.value


def _evolve(record: RunFinalizationRecord, **updates: object) -> RunFinalizationRecord:
    return RunFinalizationRecord.model_validate({**record.model_dump(mode="python"), **updates})
