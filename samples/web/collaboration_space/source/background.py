# 协作空间 Sample 的有界导出后台任务与本地消息队列。

from __future__ import annotations

import queue
import threading
import time
from typing import Any

if __package__:
    from .storage import CollaborationStorage
else:
    # 正式 Sample 以 source 为模块根运行，仓库测试则通过命名空间包导入。
    from storage import CollaborationStorage


class ExportWorker:
    """单线程处理本地导出队列，确保 ZIP 存在后才发布最终状态。"""

    def __init__(self, storage: CollaborationStorage) -> None:
        self.storage = storage
        self._pending: queue.Queue[tuple | None] = queue.Queue(maxsize=128)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sample-export-worker", daemon=True)
        self._thread.start()

    def enqueue(self, job: dict[str, Any], *, dispatch_event_id=None, authorization_event_id=None,
                first_sequence=1, response_complete=None, export_effect_id=None) -> bool:
        try:
            self._pending.put_nowait((dict(job),dispatch_event_id,authorization_event_id,first_sequence,response_complete,export_effect_id))
            return True
        except queue.Full:
            self.storage.update_job(str(job["task_id"]), "FAILED")
            return False

    def stop(self) -> None:
        self._stop.set()
        try:
            self._pending.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._pending.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                return
            job,dispatch,authorization,sequence,response_complete,effect_id = item
            # 已真实入队后等待响应处理结束；这不是授权门禁，DENY 与异常同样释放。
            deadline=time.monotonic()+5
            while response_complete is not None and not response_complete.wait(0.05):
                if self._stop.is_set() or time.monotonic()>=deadline:
                    failed=self.storage.update_job(str(job["task_id"]),"FAILED")
                    self.storage.write_task(failed,final_result={"state":"FAILED","failure_code":"RESPONSE_WINDOW_CLOSED"})
                    break
            else:
                if not self._stop.is_set():
                    self._process(job,dispatch,authorization,sequence,effect_id)

    def _process(self, job, dispatch_event_id, authorization_event_id, first_sequence, export_effect_id) -> None:
        task_id=str(job["task_id"])
        marker = str(job["case_id"])
        self.storage.update_job(task_id, "RUNNING")
        running = {**job, "state": "RUNNING"}
        self.storage.write_task(running)
        started_event_id = self.storage.append_audit(
            marker=marker,
            task_id=task_id,
            event_type="export_job_started",
            sequence=first_sequence,
            result="running",
            effect="PROCESSING",
            parent_event_id=dispatch_event_id,
            kind="DELEGATION",
            semantic_key="export_job_started",
            subject_id=str(job["actor_id"]),
            actor_id="export-worker",
            origin_authorization_event_id=authorization_event_id,
            delegated_from_event_id=dispatch_event_id,
            source_component="export-worker",
            source_location="worker:export",
        )
        self.storage.append_queue_message(
            marker=marker,
            task_id=task_id,
            event_type="TASK_RUNNING",
            sequence=2,
            result="running",
            effect="PROCESSING",
        )
        try:
            artifact_id, archive = self.storage.create_archive(marker)
            if not archive.is_file():
                raise OSError("archive was not created")
            completed = self.storage.update_job(task_id, "SUCCESS", artifact_id=artifact_id)
            completed["artifact_id"] = artifact_id
            archive_event_id = self.storage.append_audit(
                marker=marker,
                task_id=task_id,
                event_type="archive_generated",
                sequence=first_sequence+1,
                result="ready",
                effect="APPLIED",
                effect_id=export_effect_id,
                parent_event_id=started_event_id,
                kind="FINAL_EFFECT",
                semantic_key="archive_generated",
                subject_id=str(job["actor_id"]),
                actor_id="export-worker",
                origin_authorization_event_id=authorization_event_id,
                delegated_from_event_id=started_event_id,
                source_component="export-worker",
                source_location="blob:project-export",
            )
            self.storage.append_audit(
                marker=marker,
                task_id=task_id,
                event_type="export_job_completed",
                sequence=first_sequence+2,
                result="ready",
                effect="READY",
                parent_event_id=archive_event_id,
                kind="FINAL_EFFECT",
                semantic_key="export_job_completed",
                subject_id=str(job["actor_id"]),
                actor_id="export-worker",
                origin_authorization_event_id=authorization_event_id,
                delegated_from_event_id=archive_event_id,
                source_component="export-worker",
                source_location="worker:export",
            )
            self.storage.append_queue_message(
                marker=marker,
                task_id=task_id,
                event_type="EXPORT_READY",
                sequence=3,
                result="ready",
                effect="READY",
            )
            # 终态任务文件最后发布，避免读取方在过程事实尚未完整时看到 SUCCESS。
            self.storage.write_task(
                completed,
                final_result={"artifact_id": artifact_id, "state": "READY"},
            )
        except Exception as error:
            # 只发布有界失败码，避免把路径、异常正文或运行凭据带入任务接口。
            failure_code = (
                "EXPORT_STORAGE_FAILED"
                if isinstance(error, (OSError, ValueError))
                else "EXPORT_INTERNAL_FAILED"
            )
            failed = self.storage.update_job(task_id, "FAILED")
            self.storage.write_task(
                failed,
                final_result={"state": "FAILED", "failure_code": failure_code},
            )
            self.storage.append_audit(
                marker=marker,
                task_id=task_id,
                event_type="EXPORT_FAILED",
                sequence=first_sequence+1,
                result="failed",
                effect="FAILED",
            )
            self.storage.append_queue_message(
                marker=marker,
                task_id=task_id,
                event_type="EXPORT_FAILED",
                sequence=3,
                result="failed",
                effect="FAILED",
            )

    def _job_by_task(self, task_id: str) -> dict[str, Any] | None:
        for record in self.storage.queue_records():
            if record.get("task_id") == task_id:
                return self.storage.find_job(str(record.get("case_tag", "")))
        return None
