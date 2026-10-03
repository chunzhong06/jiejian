# 提供 MCP 控制面的实际装配入口；工具实现、传输与事实投影由包内模块分别负责。
from product.backend.api.mcp.server import MCPControl, build_mcp_control

__all__ = ["MCPControl", "build_mcp_control"]
