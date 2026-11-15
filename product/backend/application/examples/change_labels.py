"""官方展馆修改的阅读名称，只接受稳定操作回执与准确修改的关联。"""
import hashlib


def gallery_operation_key(workspace_id, stage):
    return hashlib.sha256(('gallery:' + workspace_id + ':' + stage).encode()).hexdigest()[:32]


def gallery_change_labels(work, project_id, change_ids):
    if not change_ids:
        return {}
    workspace = work.sample_workspaces.for_project(project_id)
    if workspace is None or workspace['runtime_kind'] != 'NODE_ESM':
        return {}
    labels = {}
    # 当前实现状态不参与历史命名；旧交付必须由本项目稳定回执定位。
    for stage, label in (
        ('VULNERABLE', '移除内部包下载限制'),
        ('EXPOSE_REVOKE', '开放内部包后再拒绝并撤回'),
        ('FIXED', '恢复内部包下载权限检查'),
        ('PREVIEW_CHANGED', '调整公开预览的返回内容'),
    ):
        receipt = work.development.receipt(project_id, 'DELIVER', gallery_operation_key(workspace['workspace_id'], stage))
        if receipt is not None and receipt.change_id in change_ids:
            labels[receipt.change_id] = label
    return labels
