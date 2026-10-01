# 预设演练复用普通开发任务与交付回执；固定操作键恢复丢失响应，不伪造客户端接收。
import hashlib
from product.backend.core.errors import ErrorCode, JiejianError


def preset_operation(experience_id, stage):
    return hashlib.sha256(f"preset:{experience_id}:{stage}".encode()).hexdigest()[:32]


def prepare_preset_task(service, current):
    if service is None:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "开发任务服务尚未就绪")
    key = preset_operation(current.runtime.experience_id, "task")
    created = service.receipt(current.project_id, "CREATE", key)
    active = service.active(current.project_id)
    if active is not None and (created is None or created.task_id != active.task_id):
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "已有其它开发任务，请先结束它或由真实 Agent 继续，不覆盖当前目标")
    if created is None:
        created = service.create(current.project_id, operation_id=key, title="让导出更顺畅，保留原来的权限",
            goal="将同步导出改为后台任务，提供任务进度；保持负责人正常导出、成员禁止越权导出和日常查看能力。")
    elif active is None:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "预设开发任务已经结束；请创建新任务继续开发")
    return created


def register_preset_delivery(service, current, version, reference, understanding, created):
    key = preset_operation(current.runtime.experience_id, version.value)
    saved = service.receipt(current.project_id, "DELIVER", key)
    if saved is not None:
        return saved
    if version.value == "FIXED" and reference is None:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "恢复修复交付仍需要原题引用")
    manifest = current.runtime.launch_manifest
    if manifest is None or understanding.inspect_source_fingerprint(current.project_id) != manifest.source_fingerprint:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前源码已不同于已加载的预设代码，不能冒充预设交付")
    previous = service.receipt(current.project_id, "DELIVER", preset_operation(current.runtime.experience_id, "VULNERABLE")) if version.value == "FIXED" else None
    context = previous or created
    return service.deliver(current.project_id, context.task_id, operation_id=key, expected_version=context.task_version,
        context_id=context.context_id, reason="预设开发变更：先授权再派发，保留异步导出" if version.value == "FIXED" else "预设开发变更：将同步导出改为后台队列处理",
        repair_reference=reference, submitted_by="预设演示 · 本机用户")


def preset_change_id(service, current, stage):
    """只读固定回执，覆盖提交成功但进程内赋值/响应丢失的窗口。"""
    if current is None or service is None:
        return None
    saved = service.receipt(current.project_id, "DELIVER", preset_operation(current.runtime.experience_id, stage))
    return None if saved is None else saved.change_id
