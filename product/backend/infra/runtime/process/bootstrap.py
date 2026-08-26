# =============================================================================
# Python 子进程启动闸门
#
# 定位
#   新 Python 根进程与真正产品模块之间的最小启动隔离层
#
# 职责
#   等待监督者完成 Job/session 绑定｜有界失败｜在当前进程执行目标模块
#
# 边界
#   闸门放行前不得导入目标模块或产生后代；超时只退出，不猜测监督者状态。
# =============================================================================

from __future__ import annotations

import argparse
import runpy
import sys
import time
from pathlib import Path

_GATE_TIMEOUT_SECONDS = 10.0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    parsed = parser.parse_args()
    deadline = time.monotonic() + _GATE_TIMEOUT_SECONDS
    while not parsed.gate.is_file():
        if time.monotonic() >= deadline:
            return 75
        time.sleep(0.01)
    parsed.gate.unlink(missing_ok=True)
    # 只有监督者完成 Job/session 绑定后才导入项目代码并核对主子进程身份。
    from product.backend.infra.runtime.process.identity import (
        require_python_environment,
    )

    require_python_environment()
    arguments = parsed.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    sys.argv = [parsed.module, *arguments]
    runpy.run_module(parsed.module, run_name="__main__", alter_sys=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
