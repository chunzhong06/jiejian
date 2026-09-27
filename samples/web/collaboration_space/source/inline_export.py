# 原始同步导出：在请求线程内真实生成文件，不入队、不伪造 Worker 或消息事实。
from typing import Any


def complete_inline_export(storage, job: dict[str, Any], *, parent_event_id: str,
                           authorization_event_id: str, sequence: int, effect_id: str | None) -> bool:
    marker, task_id, account = str(job["case_id"]), str(job["task_id"]), str(job["actor_id"])
    try:
        artifact_id, archive = storage.create_archive(marker)
        if not archive.is_file():
            raise OSError("archive missing")
        completed = storage.update_job(task_id, "SUCCESS", artifact_id=artifact_id)
        storage.append_audit(marker=marker, task_id=task_id, event_type="archive_generated",
            sequence=sequence, result="ready", effect="APPLIED", effect_id=effect_id,
            parent_event_id=parent_event_id, kind="FINAL_EFFECT", semantic_key="archive_generated",
            subject_id=account, actor_id=account, origin_authorization_event_id=authorization_event_id,
            source_component="collaboration-server", source_location="export:inline")
        storage.write_task(completed, final_result={"artifact_id": artifact_id, "state": "READY"})
        return True
    except (OSError, ValueError):
        failed = storage.update_job(task_id, "FAILED")
        storage.write_task(failed, final_result={"state": "FAILED", "failure_code": "EXPORT_STORAGE_FAILED"})
        return False
