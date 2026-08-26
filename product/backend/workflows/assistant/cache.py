# =============================================================================
# 受限 AI 辅助缓存
#
# 定位
#   AssistantService 与 var/cache/assistant 之间的可删除文件缓存边界
#
# 职责
#   隔离事实指纹｜原子写入有界记录｜命中时重新执行本地白名单校验
#
# 边界
#   只保存已验证推荐或最小退避事实；不保存提示词、秘密、供应商原文或产品真源。
#
# 调用链
#   AssistantService → AssistantCache → var/cache/assistant
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from product.backend.core.errors import JiejianError
from product.backend.workflows.assistant.templates import (
    AssistantRecommendation,
    AssistantTemplateId,
    parse_assistant_result,
)


class AssistantCache:
    """为同一项目、模板和事实指纹提供可删除的有界文件缓存。"""

    def __init__(self, root: Path) -> None:
        self._root = root / "cache" / "assistant"

    def read(
        self,
        project_id: str,
        template_id: AssistantTemplateId,
        fingerprint: str,
        *,
        allowed_option_ids: tuple[str, ...],
    ) -> dict[str, Any] | None:
        path = self._path(project_id, template_id, fingerprint)
        try:
            if not path.is_file() or path.stat().st_size > 64 * 1024:
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(value, dict) or value.get("state_fingerprint") != fingerprint:
            return None
        if value.get("entry_type") == "success":
            # 文件缓存不是信任边界；即使文件被外部改写，未知 option 也只能退化为未命中。
            return self._read_success(
                value,
                template_id,
                allowed_option_ids=allowed_option_ids,
            )
        if value.get("entry_type") == "failure":
            return self._read_failure(value, template_id)
        return None

    def write_success(
        self,
        project_id: str,
        template_id: AssistantTemplateId,
        fingerprint: str,
        *,
        provider: str,
        profile: str,
        model: str,
        reasoning_setting: str | None,
        recommendations: tuple[AssistantRecommendation, ...],
        generated_at_us: int,
    ) -> None:
        payload = {
            "schema_version": "1",
            "entry_type": "success",
            "provider": provider,
            "profile": profile,
            "model": model,
            "reasoning_setting": reasoning_setting,
            "template_id": template_id.value,
            "template_version": "1",
            "state_fingerprint": fingerprint,
            "recommendations": [item.model_dump(mode="json") for item in recommendations],
            "generated_at_us": generated_at_us,
        }
        self._write(project_id, template_id, fingerprint, payload)

    def write_failure(
        self,
        project_id: str,
        template_id: AssistantTemplateId,
        fingerprint: str,
        *,
        code: str,
        retry_after_us: int,
    ) -> None:
        self._write(
            project_id,
            template_id,
            fingerprint,
            {
                "schema_version": "1",
                "entry_type": "failure",
                "template_id": template_id.value,
                "template_version": "1",
                "state_fingerprint": fingerprint,
                "code": code,
                "retry_after_us": retry_after_us,
            },
        )

    def _write(self, project_id: str, template_id: AssistantTemplateId, fingerprint: str, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 64 * 1024:
            return
        path = self._path(project_id, template_id, fingerprint)
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            temporary: Path | None = None
            with tempfile.NamedTemporaryFile("wb", dir=self._root, prefix=".assistant-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            # 同目录替换避免并发读者观察到半个 JSON 文档。
            os.replace(temporary, path)
        except OSError:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def _path(self, project_id: str, template_id: AssistantTemplateId, fingerprint: str) -> Path:
        key = f"{project_id}\x00{template_id.value}\x00{fingerprint}".encode("utf-8")
        return self._root / f"{hashlib.sha256(key).hexdigest()}.json"

    @staticmethod
    def _read_success(
        value: dict[str, Any],
        template_id: AssistantTemplateId,
        *,
        allowed_option_ids: tuple[str, ...],
    ) -> dict[str, Any] | None:
        required = {
            "schema_version", "entry_type", "provider", "profile", "model", "reasoning_setting",
            "template_id", "template_version", "state_fingerprint", "recommendations", "generated_at_us",
        }
        if set(value) != required or value["schema_version"] != "1" or value["entry_type"] != "success":
            return None
        if value["template_id"] != template_id.value or value["template_version"] != "1":
            return None
        if not all(isinstance(value[key], str) and value[key] for key in ("provider", "profile", "model")):
            return None
        if value["reasoning_setting"] is not None and not isinstance(value["reasoning_setting"], str):
            return None
        if not isinstance(value["generated_at_us"], int) or isinstance(value["generated_at_us"], bool) or value["generated_at_us"] < 0:
            return None
        try:
            result = parse_assistant_result(
                {
                    "schema_version": value["schema_version"],
                    "template_id": value["template_id"],
                    "template_version": value["template_version"],
                    "recommendations": value["recommendations"],
                },
                template_id=template_id,
                allowed_option_ids=allowed_option_ids,
            )
        except JiejianError:
            return None
        return {**value, "recommendations": result.recommendations}

    @staticmethod
    def _read_failure(value: dict[str, Any], template_id: AssistantTemplateId) -> dict[str, Any] | None:
        required = {"schema_version", "entry_type", "template_id", "template_version", "state_fingerprint", "code", "retry_after_us"}
        if set(value) != required or value["schema_version"] != "1" or value["entry_type"] != "failure":
            return None
        if value["template_id"] != template_id.value or value["template_version"] != "1":
            return None
        if not isinstance(value["code"], str) or not value["code"] or len(value["code"]) > 96:
            return None
        if not isinstance(value["retry_after_us"], int) or isinstance(value["retry_after_us"], bool) or value["retry_after_us"] < 0:
            return None
        return value
