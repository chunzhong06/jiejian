# 持久化测试状态；只保存位置、结果与耗时，不保存断言值、请求正文或环境变量。
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path


def write_report(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def public_node(nodeid: str) -> str:
    # 参数化 id 可由请求、密码等任意测试值产生，不能原样进入长期报告。
    base, separator, parameters = nodeid.partition("[")
    if separator:
        return base + "[case-" + hashlib.sha256(parameters.encode()).hexdigest()[:12] + "]"
    return base


def result_status(*, failures: int, collected: int, skipped: int, exit_code: int, collect_only: bool = False) -> str:
    if failures or exit_code not in {0, 5}:
        return "FAILED"
    if not collected or exit_code == 5:
        return "EMPTY"
    if skipped and not collect_only:
        return "INCOMPLETE"
    return "COLLECTED" if collect_only else "PASSED"


def safe_reason(value: object) -> str:
    # 原始 skip/异常正文也可能包含目标响应；报告仅采用明确的大写原因码。
    text = str(value)
    return text if re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", text) else "DETAILS_IN_LOCAL_CONSOLE"
