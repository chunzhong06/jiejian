# 协作空间 Sample 的有界导出后台任务与本地消息队列。

from __future__ import annotations

import queue
import threading
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
        self._pending: queue.Queue[str | None] = queue.Queue(maxsize=128)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sample-export-worker", daemon=True)
        self._thread.start()

    def enqueue(self, job: dict[str, Any]) -> None:
        try:
            self._pending.put_nowait(str(job["task_id"]))
        except queue.Full:
            self.storage.update_job(str(job["task_id"]), "FAILED")

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
                task_id = self._pending.get(timeout=0.1)
            except queue.Empty:
                continue
            if task_id is None:
                return
            self._process(task_id)

    def _process(self, task_id: str) -> None:
        job = self._job_by_task(task_id)
        if job is None:
            return
        marker = str(job["case_id"])
        self.storage.update_job(task_id, "RUNNING")
        running = {**job, "state": "RUNNING"}
        self.storage.write_task(running)
        self.storage.append_audit(
            marker=marker,
            task_id=task_id,
            event_type="TASK_RUNNING",
            sequence=2,
            result="running",
            effect="PROCESSING",
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
            self.storage.write_task(completed, final_result={"artifact_id": artifact_id, "state": "READY"})
            self.storage.append_audit(
                marker=marker,
                task_id=task_id,
                event_type="EXPORT_READY",
                sequence=3,
                result="ready",
                effect="READY",
            )
            self.storage.append_queue_message(
                marker=marker,
                task_id=task_id,
                event_type="EXPORT_READY",
                sequence=3,
                result="ready",
                effect="READY",
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
                sequence=3,
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
