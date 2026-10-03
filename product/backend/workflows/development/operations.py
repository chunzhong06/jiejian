# 定义开发与加载共用的操作指纹和活动版本检查；不提交事务或改变任务状态。
import hashlib
import json
import re
from product.backend.core.errors import ErrorCode, JiejianError


def operation_fingerprint(project_id, kind, operation_id, payload):
    if not isinstance(operation_id, str) or re.fullmatch(r"[0-9a-f]{32}", operation_id) is None:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "操作标识必须是稳定的 32 位十六进制值")
    encoded = json.dumps({"project_id": project_id, "kind": kind, "payload": payload},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_active_task_version(work, project_id, task_id, expected_version):
    task = work.development.task(project_id, task_id)
    if task is None or task.status != "ACTIVE" or type(expected_version) is not int or task.version != expected_version:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "任务状态或版本已变化，请读取当前任务")
    return task
