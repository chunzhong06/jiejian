# sample-test 公开验证清单：只承载可交给产品与 fixture 的业务输入，不接触 private oracle。

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_PUBLIC_ID = re.compile(r"^[a-z][a-z0-9_-]{0,79}$")
_APPLICATIONS = ("collaboration-space", "tenant-records")
_BREAK_MODES = (
    "object_tenant_check_missing",
    "new_entry_inheritance",
    "feature_authorization_bypass",
    "delegation_authority_expansion",
    "deny_async_consequence",
)
_STATES = (
    ("MODE_FAULT_PRESENT", "AVAILABLE"),
    ("MODE_GUARD_ACTIVE", "AVAILABLE"),
    ("MODE_GUARD_ACTIVE", "UNAVAILABLE"),
)
_PRIVATE_KEYS = frozenset(
    {
        "expected_verdict",
        "breakpoint_type",
        "breakpoint_location",
        "breakpoint_range",
        "maximum_precision",
        "golden_answer",
    }
)
_CASE_KEYS = frozenset(
    {
        "case_id",
        "application_id",
        "mode",
        "source_root",
        "business_action",
        "identity",
        "resource",
        "permission_intent",
        "protected_effects",
        "observation_config",
        "allow_control_identity",
        "state_selector",
    }
)


class ValidationRegistryError(RuntimeError):
    """表示公开清单不完整、越界或混入 private oracle 字段。"""


@dataclass(frozen=True, slots=True)
class PublicValidationCase:
    """一个不含答案的公开验证输入。"""

    case_id: str
    application_id: str
    mode: str
    source_root: Path
    business_action: str
    identity: str
    resource: str
    permission_intent: Mapping[str, object]
    protected_effects: tuple[str, ...]
    observation_config: Mapping[str, object]
    allow_control_identity: str
    state_selector: Mapping[str, object]

    def product_input(self, root: Path) -> dict[str, object]:
        """投影产品可消费输入；路径限于授权源码根且不会附带 oracle。"""

        return {
            "case_id": self.case_id,
            "application_id": self.application_id,
            "mode": self.mode,
            "source_root": self.source_root.relative_to(root).as_posix(),
            "business_action": self.business_action,
            "identity": self.identity,
            "resource": self.resource,
            "permission_intent": dict(self.permission_intent),
            "protected_effects": list(self.protected_effects),
            "observation_config": dict(self.observation_config),
            "allow_control_identity": self.allow_control_identity,
            "state_selector": dict(self.state_selector),
        }


@dataclass(frozen=True, slots=True)
class ValidationCaseResult:
    """由公开执行事实形成的实际结果，不包含期望答案。"""

    case_id: str
    application_id: str
    mode: str
    verdict: str
    allow_control_valid: bool
    breakpoint_type: str | None
    breakpoint_location: str | None
    breakpoint_range: tuple[str, ...]
    precision: str | None
    effect_state: str
    authorization_continuity: str
    orphan_effect_detected: bool | None
    actual_identity_attributed: bool
    recovery_success: bool
    baseline_verdicts: Mapping[str, str]

    def public_payload(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "application_id": self.application_id,
            "mode": self.mode,
            "verdict": self.verdict,
            "allow_control_valid": self.allow_control_valid,
            "breakpoint": {
                "type": self.breakpoint_type,
                "location": self.breakpoint_location,
                "range": list(self.breakpoint_range),
                "precision": self.precision,
            },
            "effect_state": self.effect_state,
            "authorization_continuity": self.authorization_continuity,
            "orphan_effect_detected": self.orphan_effect_detected,
            "actual_identity_attributed": self.actual_identity_attributed,
            "recovery_success": self.recovery_success,
            "baseline_verdicts": dict(self.baseline_verdicts),
        }


def load_public_registry(root: Path) -> tuple[PublicValidationCase, ...]:
    """从固定 tests/validation 边界读取并严格校验公开清单。"""

    root = root.resolve()
    path = root / "tests" / "validation" / "public_registry.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationRegistryError("VALIDATION_PUBLIC_REGISTRY_UNREADABLE") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "cases"}:
        raise ValidationRegistryError("VALIDATION_PUBLIC_REGISTRY_SHAPE_INVALID")
    if payload.get("schema_version") != "1" or not isinstance(payload.get("cases"), list):
        raise ValidationRegistryError("VALIDATION_PUBLIC_REGISTRY_VERSION_INVALID")
    cases = tuple(_parse_case(root, item) for item in payload["cases"])
    case_ids = tuple(item.case_id for item in cases)
    if not cases or len(case_ids) != len(set(case_ids)):
        raise ValidationRegistryError("VALIDATION_PUBLIC_CASE_IDS_INVALID")
    actual_matrix = {
        (
            item.application_id,
            item.mode,
            str(item.state_selector.get("implementation")),
            str(item.state_selector.get("observation")),
        )
        for item in cases
    }
    expected_matrix = {
        (application, mode, implementation, observation)
        for application in _APPLICATIONS
        for mode in _BREAK_MODES
        for implementation, observation in _STATES
    }
    if len(cases) != 30 or actual_matrix != expected_matrix:
        raise ValidationRegistryError("VALIDATION_PUBLIC_MATRIX_INVALID")
    return cases


def public_registry_payload(
    root: Path,
    cases: tuple[PublicValidationCase, ...],
) -> dict[str, object]:
    """生成可审计的公开产品输入，递归拒绝 private oracle 字段。"""

    payload = {
        "schema_version": "1",
        "cases": [item.product_input(root.resolve()) for item in cases],
    }
    private = _find_private_keys(payload)
    if private:
        raise ValidationRegistryError("VALIDATION_PRIVATE_FIELDS_IN_PUBLIC_INPUT")
    return payload


def _parse_case(root: Path, value: object) -> PublicValidationCase:
    if not isinstance(value, dict) or set(value) != _CASE_KEYS:
        raise ValidationRegistryError("VALIDATION_PUBLIC_CASE_SHAPE_INVALID")
    private = _find_private_keys(value)
    if private:
        raise ValidationRegistryError("VALIDATION_PRIVATE_FIELDS_IN_PUBLIC_INPUT")
    case_id = _public_text(value, "case_id")
    application_id = _public_text(value, "application_id")
    mode = _public_text(value, "mode")
    business_action = _public_text(value, "business_action")
    identity = _public_text(value, "identity")
    resource = _public_text(value, "resource")
    allow_control_identity = _public_text(value, "allow_control_identity")
    for field, text in (
        ("case_id", case_id),
        ("application_id", application_id),
        ("mode", mode),
        ("business_action", business_action),
        ("identity", identity),
        ("resource", resource),
        ("allow_control_identity", allow_control_identity),
    ):
        if _PUBLIC_ID.fullmatch(text) is None:
            raise ValidationRegistryError(f"VALIDATION_PUBLIC_{field.upper()}_INVALID")
    source_value = value.get("source_root")
    if not isinstance(source_value, str) or not source_value or Path(source_value).is_absolute():
        raise ValidationRegistryError("VALIDATION_SOURCE_ROOT_INVALID")
    source_root = (root / source_value).resolve()
    try:
        source_root.relative_to(root)
    except ValueError as exc:
        raise ValidationRegistryError("VALIDATION_SOURCE_ROOT_OUTSIDE_REPOSITORY") from exc
    if not source_root.is_dir():
        raise ValidationRegistryError("VALIDATION_SOURCE_ROOT_UNAVAILABLE")
    effects = value.get("protected_effects")
    if (
        not isinstance(effects, list)
        or not effects
        or any(not isinstance(item, str) or _PUBLIC_ID.fullmatch(item) is None for item in effects)
        or len(effects) != len(set(effects))
    ):
        raise ValidationRegistryError("VALIDATION_PROTECTED_EFFECTS_INVALID")
    permission_intent = _public_mapping(value, "permission_intent")
    observation_config = _public_mapping(value, "observation_config")
    state_selector = _public_mapping(value, "state_selector")
    return PublicValidationCase(
        case_id=case_id,
        application_id=application_id,
        mode=mode,
        source_root=source_root,
        business_action=business_action,
        identity=identity,
        resource=resource,
        permission_intent=permission_intent,
        protected_effects=tuple(effects),
        observation_config=observation_config,
        allow_control_identity=allow_control_identity,
        state_selector=state_selector,
    )


def _public_text(source: Mapping[str, object], name: str) -> str:
    value = source.get(name)
    if not isinstance(value, str) or not value:
        raise ValidationRegistryError(f"VALIDATION_PUBLIC_{name.upper()}_INVALID")
    return value


def _public_mapping(source: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = source.get(name)
    if not isinstance(value, dict) or not value or _find_private_keys(value):
        raise ValidationRegistryError(f"VALIDATION_PUBLIC_{name.upper()}_INVALID")
    return value


def _find_private_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _PRIVATE_KEYS or key.startswith("expected_") or key.startswith("golden_"):
                found.add(key)
            found.update(_find_private_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_private_keys(item))
    return found


__all__ = [
    "PublicValidationCase",
    "ValidationCaseResult",
    "ValidationRegistryError",
    "load_public_registry",
    "public_registry_payload",
]
