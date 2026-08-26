# =============================================================================
# HTTP 路由公共校验
#
# 定位
#   Contract Analysis 与 Application Understanding 共享的纯 Core 边界
#
# 职责
#   冻结受支持 HTTP method｜校验有限绝对路由路径
#
# 边界
#   不解析 OpenAPI，不生成候选，也不携带任何 Contract 或权限语义。
# =============================================================================

from __future__ import annotations


HTTP_METHODS = ("GET", "PATCH", "POST", "PUT", "DELETE")


def safe_route_path(path: str) -> bool:
    """只接受单斜杠起始且不含父目录片段的应用路由。"""

    return bool(
        path.startswith("/")
        and not path.startswith("//")
        and ".." not in path.split("/")
    )
