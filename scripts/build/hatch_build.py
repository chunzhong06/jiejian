# =============================================================================
# Wheel 前端映射构建钩子
#
# 定位
#   开发态 editable 与可选发布 Wheel 的前端资产依赖分界。
#
# 职责
#   仅在标准 Wheel 构建时把已准备的 var/runtime/frontend 映射进包内静态目录。
#
# 边界
#   editable 安装不读取前端产物；钩子不创建目录、不构建前端、不回写源码树。
# =============================================================================

from __future__ import annotations

import os
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """只为显式 package 流程附加已经生成且可读的前端资源。"""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        if version == "editable":
            return
        raw = os.environ.get("JIEJIAN_PACKAGE_FRONTEND_DIR")
        if not raw:
            raise RuntimeError("标准 Wheel 构建缺少 JIEJIAN_PACKAGE_FRONTEND_DIR")
        frontend = Path(raw).resolve()
        if not frontend.is_dir() or not (frontend / "index.html").is_file():
            raise RuntimeError("标准 Wheel 构建缺少已准备的前端入口")
        force_include = build_data.setdefault("force_include", {})
        if not isinstance(force_include, dict):
            raise RuntimeError("Hatch force_include 构建数据无效")
        force_include[str(frontend)] = "product/frontend/dist"
