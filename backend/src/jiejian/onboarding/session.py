# 定位：C2a 新手会话的非秘密文件存储。
# 职责：校验会话路径、限制 JSON 大小并以临时文件原子替换；不保存凭据值。

from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path

from ..errors import ErrorCode, JiejianError
from .models import OnboardingSession

_MAX_SESSION_BYTES = 64 * 1024


class OnboardingSessionStore:
    def __init__(self, var_dir: Path) -> None:
        self.root = (var_dir.resolve() / "onboarding" / "sessions").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        if not re.fullmatch(r"onb_[0-9a-f]{32}", session_id):
            raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "新手会话标识无效")
        path = (self.root / f"{session_id}.json").resolve()
        if not path.is_relative_to(self.root):
            raise JiejianError(ErrorCode.ONBOARDING_PATH_UNSAFE, "新手会话路径不安全")
        return path

    def create(self, session: OnboardingSession) -> OnboardingSession:
        self.save(session)
        return session

    def load(self, session_id: str) -> OnboardingSession:
        path = self._path(session_id)
        try:
            raw = path.read_bytes()
        except OSError:
            raise JiejianError(ErrorCode.ONBOARDING_SESSION_NOT_FOUND, "新手会话不存在") from None
        if len(raw) > _MAX_SESSION_BYTES:
            raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "新手会话文件过大")
        try:
            value = json.loads(raw.decode("utf-8"))
            return OnboardingSession.model_validate(value, strict=True)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "新手会话文件无效") from None

    def save(self, session: OnboardingSession) -> None:
        path = self._path(session.session_id)
        payload = session.model_dump_json().encode("utf-8")
        if len(payload) > _MAX_SESSION_BYTES:
            raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "新手会话内容过大")
        temp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        try:
            temp.write_bytes(payload)
            os.replace(temp, path)
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "新手会话暂时无法保存") from None
