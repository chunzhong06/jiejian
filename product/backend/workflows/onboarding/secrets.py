# =============================================================================
# 应用接入运行时秘密
#
# 定位
# onboarding 会话与后续执行环境之间的进程内凭据端口。
#
# 职责
# 按会话保存 opaque 凭据｜解析明确名称｜在完成或停止时清理
#
# 边界
# 不序列化、不落盘、不返回全量值，repr 和状态输出只暴露计数。
#
# 调用链
# OnboardingWorkflow → RuntimeSecretVault → execution environment
# =============================================================================

from __future__ import annotations

from collections.abc import Mapping, Sequence
from threading import RLock


class RuntimeSecretVault:
    """线程安全保存短期会话秘密，并以最小名称集合向执行环境投影。"""

    def __init__(self) -> None:
        self._values: dict[str, dict[str, str]] = {}
        self._lock = RLock()

    def put(self, session_id: str, values: Mapping[str, str]) -> None:
        with self._lock:
            self._values[session_id] = {
                name: value for name, value in values.items() if value
            }

    def configured(self, session_id: str, names: Sequence[str]) -> tuple[bool, ...]:
        with self._lock:
            values = self._values.get(session_id, {})
            return tuple(bool(values.get(name)) for name in names)

    def resolve(self, names: Sequence[str]) -> dict[str, str]:
        with self._lock:
            result: dict[str, str] = {}
            for values in self._values.values():
                for name in names:
                    if name in values:
                        result[name] = values[name]
            return result

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._values.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def model_dump(self) -> dict[str, int]:
        with self._lock:
            return {"session_count": len(self._values)}

    def __repr__(self) -> str:
        return "RuntimeSecretVault(<opaque>)"
