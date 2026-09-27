# 当前受限辅助的事实投影类型和短文本转换；不保留旧引导流程。
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Protocol
from .templates import AssistantEntity, AssistantEntityType, AssistantFact, AssistantSurfaceInput, AssistantTemplateId, SafeFactValue

@dataclass(frozen=True, slots=True)
class ResolvedAssistantSurface:
    subject_id: str
    state_fingerprint: str
    surface_input: AssistantSurfaceInput
    can_generate: bool = True


def _entity(
    entity_id: str,
    entity_type: AssistantEntityType,
    display_name: str,
    facts: Mapping[str, SafeFactValue],
) -> AssistantEntity:
    return AssistantEntity(
        entity_id=entity_id,
        entity_type=entity_type,
        display_name=_short(display_name),
        facts=tuple(
            AssistantFact(field=field, value=_safe_value(value))
            for field, value in sorted(facts.items())
        ),
    )


def _safe_value(value) -> SafeFactValue:
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(_short(item) for item in list(value)[:64])
    return _short(value)


def _short(value, limit: int = 160) -> str:
    normalized = " ".join(str(value).split()).strip()
    return (normalized[:limit] or "未提供")


def _unique_short(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_short(value) for value in values))[:64]

class AssistantSurfaceResolver(Protocol):
    """项目准备与已发布结果的只读事实入口，不接受自由文本作为判断依据。"""
    def resolve_project(self, project_id: str, template_id: AssistantTemplateId, **references) -> ResolvedAssistantSurface: ...
    def resolve_result(self, run_id: str) -> ResolvedAssistantSurface: ...
