# =============================================================================
# 应用接入会话存储
#
# 定位
# 短期 onboarding 会话模型与 var 文件之间的非秘密持久化边界。
#
# 职责
# 校验会话标识与路径｜限制 JSON 大小｜原子创建和替换会话文件
#
# 边界
# 只保存凭据引用和脱敏字段；凭据正文不得序列化或写入磁盘。
#
# 调用链
# OnboardingWorkflow → OnboardingSessionStore → var/onboarding/sessions
# =============================================================================

from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.onboarding.models import OnboardingSession

_MAX_SESSION_BYTES = 64 * 1024


class OnboardingSessionStore:
    """以有界、原子 JSON 文件保存不含凭据正文的 onboarding 会话。"""

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
        """读取并严格校验一个会话；缺失、超限和损坏使用不同稳定错误。"""

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
        """先写同目录临时文件再原子替换，失败时只清理本次临时文件。"""

        path = self._path(session.session_id)
        payload = session.model_dump_json().encode("utf-8")
        if len(payload) > _MAX_SESSION_BYTES:
            raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "新手会话内容过大")
        temp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        try:
            temp.write_bytes(payload)
            os.replace(temp, path)
        except OSError:
            # 资源生命周期：清理目标仅是本次唯一命名临时文件，既有会话不可被失败写入破坏。
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "新手会话暂时无法保存") from None
