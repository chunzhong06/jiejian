# 本地观察环境注册表；按当前源码根与确认地址解析活跃体验的机械 descriptor。

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from threading import RLock
from urllib.parse import urlsplit

from product.backend.core.errors import ErrorCode, JiejianError


_EXPERIENCE_ID = re.compile(r"exp_[0-9a-f]{32}\Z")


@dataclass(frozen=True, slots=True)
class LocalObserverEnvironment:
    """一个活跃本地体验的非秘密观察连接事实。"""

    experience_id: str
    source_root: Path
    origin: str
    descriptor_path: Path


class LocalObserverEnvironmentRegistry:
    """只在当前 ApplicationCore 生命周期内保存活跃本地观察环境。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._entries: dict[str, LocalObserverEnvironment] = {}

    def register(
        self,
        *,
        experience_id: str,
        source_root: str | Path,
        confirmed_endpoint: str,
        descriptor_path: str | Path,
    ) -> LocalObserverEnvironment:
        clean_id = experience_id.strip()
        if _EXPERIENCE_ID.fullmatch(clean_id) is None:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "本地体验标识无效",
            )
        source = Path(source_root).expanduser().resolve()
        descriptor = Path(descriptor_path).expanduser().resolve()
        if not source.is_dir() or not descriptor.is_file():
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "本地观察环境尚未准备完成",
            )
        entry = LocalObserverEnvironment(
            experience_id=clean_id,
            source_root=source,
            origin=_normalize_origin(confirmed_endpoint),
            descriptor_path=descriptor,
        )
        with self._lock:
            for current_id, current in self._entries.items():
                if current_id != clean_id and (
                    current.source_root == source or current.origin == entry.origin
                ):
                    raise JiejianError(
                        ErrorCode.STATE_PRECONDITION,
                        "本地应用已经绑定其他活跃体验",
                    )
            self._entries[clean_id] = entry
        return entry

    def unregister(self, experience_id: str) -> None:
        with self._lock:
            self._entries.pop(experience_id, None)

    def resolve(
        self,
        source_root: str | Path,
        confirmed_endpoint: str | None,
    ) -> str | None:
        """精确匹配源码根与 origin；无活跃体验时保留普通单 Observer 路线。"""

        if confirmed_endpoint is None:
            return None
        try:
            source = Path(source_root).expanduser().resolve()
            origin = _normalize_origin(confirmed_endpoint)
        except (OSError, RuntimeError, JiejianError):
            return None
        with self._lock:
            for entry in self._entries.values():
                if entry.source_root == source and entry.origin == origin:
                    return str(entry.descriptor_path)
        return None


def _normalize_origin(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except (AttributeError, ValueError) as exc:
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "本地体验地址无效",
        ) from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not 1 <= port <= 65535
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "本地体验只能使用规范化回环地址",
        )
    origin = f"http://127.0.0.1:{port}"
    if value.strip() != origin:
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "本地体验地址未规范化",
        )
    return origin


__all__ = ["LocalObserverEnvironment", "LocalObserverEnvironmentRegistry"]
