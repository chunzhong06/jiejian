# =============================================================================
# 系统目录选择进程
#
# 定位
# Web 控制面与 Windows 原生目录对话框之间的短生命周期 UI 进程边界。
#
# 职责
# 在主线程显示有父级对话框｜规范选择结果｜输出单个版本化响应
#
# 边界
# 只返回用户选择的绝对路径，不读取目录内容，也不把 Tk 生命周期带回服务进程。
#
# 调用链
# SystemFolderSelector → folder_picker_process → Windows directory dialog
# =============================================================================

from __future__ import annotations

import json
import os
from typing import Any

from product.backend.workflows.onboarding.models import FolderSelectionResult


def show_directory_dialog(
    *,
    platform_name: str | None = None,
    tk_module: Any | None = None,
    filedialog_module: Any | None = None,
) -> str:
    """在当前进程主线程显示目录选择器；不读取所选目录。"""

    if (platform_name or os.name) != "nt":
        raise RuntimeError("Windows directory picker is unavailable")
    if tk_module is None or filedialog_module is None:
        import tkinter as tk
        from tkinter import filedialog

        tk_module = tk
        filedialog_module = filedialog

    root = tk_module.Tk()
    try:
        # 创建透明、置顶且可获得焦点的真实父窗口，避免原生对话框落到浏览器后方。
        root.withdraw()
        root.overrideredirect(True)
        root.geometry("1x1+0+0")
        root.attributes("-alpha", 0.0)
        root.attributes("-topmost", True)
        root.deiconify()
        root.lift()
        root.focus_force()
        root.update()
        return str(
            filedialog_module.askdirectory(
                parent=root,
                title="选择要检查的应用文件夹",
                mustexist=True,
            )
        )
    finally:
        root.destroy()


def main() -> int:
    try:
        selected = show_directory_dialog()
        result = (
            FolderSelectionResult(status="selected", path=selected)
            if selected
            else FolderSelectionResult(status="cancelled")
        )
    except Exception:
        # 子进程异常不得暴露桌面、路径或 Tcl/Tk 诊断；父进程只消费稳定状态。
        result = FolderSelectionResult(
            status="unavailable",
            message="系统目录选择器当前不可用，请改用手工绝对路径",
        )
    print(
        json.dumps(
            {
                "schema_version": "1",
                **result.model_dump(mode="json", exclude_none=True),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
