# 组合各页面操作，所有动作共享同一控制会话与验收记录。
from .gui.environment import EnvironmentActions
from .gui.boundaries import BoundariesActions
from .gui.checks import ChecksActions
from .gui.history import HistoryActions
from .gui.mcp import McpActions


class CurrentGui(EnvironmentActions, BoundariesActions, ChecksActions, HistoryActions, McpActions):
    """正式验收唯一的页面操作入口。"""
