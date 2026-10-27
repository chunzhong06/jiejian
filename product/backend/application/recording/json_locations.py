# 录制候选生成与人工审阅共用的 JSON 字段定位，不修改正文或猜测缺失字段。
import re
from typing import Any


def read_json_location(value: Any, path: str) -> Any:
    current = value
    for field, offset in re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)|\[([0-9]+)\]", path):
        key: str | int = field if field else int(offset)
        try:
            current = current[key]
        except (KeyError, IndexError, TypeError):
            return None
    return current
