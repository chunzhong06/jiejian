# 定位：C2a 进程内运行时秘密端口。
# 职责：保存 opaque 凭据、按会话清理并提供最小名称解析；不序列化、不落盘。

from __future__ import annotations

from collections.abc import Mapping, Sequence
from threading import RLock


class RuntimeSecretVault:
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
