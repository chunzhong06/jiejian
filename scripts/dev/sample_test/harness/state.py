# 验收运行状态与固定场景常量，不持有秘密。
from __future__ import annotations

from dataclasses import dataclass



PROJECT_KEY = "campus-digital-museum"


RESOURCE_ID = "campus-digital-museum-package"


EXPORT_ACTION_KEY = "POST /api/projects/{project_id}/exports"


VIEW_ACTION_KEY = "GET /api/projects/{project_id}/collaboration"


CONTROL_PORT = 8765


PHASE_TITLES = {
    1: "启动隔离实例", 2: "准备官方示例", 3: "确认权限与准备材料", 4: "起始验证与异步优化检查",
    5: "观察不足的新检查", 6: "原题修复与新检查", 7: "结果与历史证据核对", 8: "退出与资源清理",
}


ROLE_LABELS = {
    "project_owner": "项目负责人",
    "member": "普通成员",
}


SOURCE_LABELS = (
    ("OWNER_API", "目标业务状态", "SUPPORTING"),
    ("READ_ONLY_SQLITE", "只读数据库", "SUPPORTING"),
    ("STRUCTURED_AUDIT_LOG", "结构化审计记录", "DIAGNOSIS_REQUIRED"),
    ("ASYNC_TASK_STATUS", "后台任务", "SUPPORTING"),
    ("AZURE_QUEUE_PEEK", "消息通道", "SUPPORTING"),
    ("AZURE_BLOB_OBJECT", "最终对象/文件", "VERDICT_REQUIRED"),
)


SOURCE_TYPES = {item[0] for item in SOURCE_LABELS}


class SampleTestError(RuntimeError):
    """只承载无秘密的公开验收失败摘要。"""


@dataclass(slots=True)
class HarnessState:
    """保存失败清理所需的最小公开身份与当前验收步骤。"""

    stage: int = 0
    active_run_id: str | None = None
    active_run_job_id: str | None = None
    sample_started: bool = False
    product_ready: bool = False
    mcp_project_id: str | None = None
    mcp_created_pairing: bool = False
    mcp_cleanup_pending: bool = False
    mcp_forget_attempted: bool = False
