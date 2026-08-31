# 验证权限草稿只整理人类原文与当前矩阵选项，失败或异常输出都不改变权限事实。

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.infra.llm.adapters.base import LLMTransportError
from product.backend.workflows.permission_drafting import (
    PermissionDraftService,
    PermissionDraftStatus,
)


_OPTION_ID = "opt_" + "1" * 32
_TEXT = "Bob 可以读取自己的文件。"


class _PermissionIntents:
    def __init__(self) -> None:
        self.oracle = (7, (("pin_1", 3, "hash"),))

    def matrix(self, project_id: str):
        assert project_id == "app_demo"
        cell = SimpleNamespace(
            subject_role_candidate_id="role_bob",
            resource_owner_role_candidate_id="role_bob",
            relation=PermissionIntentRelation.OWNS,
            subject_role_display_name="Bob",
            resource_owner_role_display_name="Bob",
            expectation=PermissionExpectation.ALLOW,
        )
        action = SimpleNamespace(
            action_candidate_id="action_read_file",
            action_display_name="读取文件",
            cells=(cell,),
        )
        return SimpleNamespace(actions=(action,))


class _Provider:
    def __init__(self, payload: object = None, *, error: bool = False) -> None:
        self.payload = payload
        self.error = error

    def invoke(self, prompt: str, *, json_schema: dict[str, object]):
        assert "candidate_id" not in prompt
        assert "additionalProperties" in json.dumps(json_schema)
        if self.error:
            raise LLMTransportError("timeout")
        return SimpleNamespace(final_payload=json.dumps(self.payload, ensure_ascii=False))


class _Profiles:
    def __init__(self, provider: _Provider, *, enabled: bool = True) -> None:
        self.provider = provider
        self.enabled = enabled

    def get_settings(self):
        return SimpleNamespace(
            enabled=self.enabled,
            default_profile_name="default" if self.enabled else None,
        )

    def get(self, name: str):
        assert name == "default"
        return SimpleNamespace(enabled=True, secret_configured=True)

    def resolve_provider(self, name: str):
        assert name == "default"
        return self.provider


def _service(payload: object = None, *, error: bool = False, enabled: bool = True):
    permissions = _PermissionIntents()
    service = PermissionDraftService(
        permission_intents=permissions,
        llm_profiles=_Profiles(_Provider(payload, error=error), enabled=enabled),
        option_id_factory=lambda: _OPTION_ID,
    )
    return service, permissions


def test_valid_option_is_ready_for_review_without_oracle_change() -> None:
    service, permissions = _service(
        {
            "suggestions": [
                {
                    "option_id": _OPTION_ID,
                    "expectation": "ALLOW",
                    "source_quote": "可以读取",
                }
            ],
            "unresolved_quotes": [],
        }
    )
    before = permissions.oracle

    draft = service.draft("app_demo", _TEXT)

    assert draft.status is PermissionDraftStatus.READY_FOR_REVIEW
    assert draft.suggestions[0].action_candidate_id == "action_read_file"
    assert draft.suggestions[0].suggested_expectation is PermissionExpectation.ALLOW
    assert permissions.oracle == before


@pytest.mark.parametrize(
    ("payload", "expected_status", "expected_code"),
    (
        (
            {
                "suggestions": [
                    {
                        "option_id": "opt_" + "2" * 32,
                        "expectation": "ALLOW",
                        "source_quote": "可以读取",
                    }
                ],
                "unresolved_quotes": [],
            },
            PermissionDraftStatus.PARTIAL,
            "UNKNOWN_OPTION",
        ),
        (
            {
                "suggestions": [
                    {
                        "option_id": _OPTION_ID,
                        "expectation": "ALLOW",
                        "source_quote": "不存在的原文",
                    }
                ],
                "unresolved_quotes": [],
            },
            PermissionDraftStatus.PARTIAL,
            "SOURCE_QUOTE_INVALID",
        ),
        (
            {
                "suggestions": [
                    {
                        "option_id": _OPTION_ID,
                        "expectation": "ALLOW",
                        "source_quote": "可以读取",
                    },
                    {
                        "option_id": _OPTION_ID,
                        "expectation": "DENY",
                        "source_quote": "可以读取",
                    },
                ],
                "unresolved_quotes": [],
            },
            PermissionDraftStatus.PARTIAL,
            "CONFLICTING_SUGGESTIONS",
        ),
        (
            {
                "suggestions": [
                    {
                        "option_id": _OPTION_ID,
                        "expectation": "MAYBE",
                        "source_quote": "可以读取",
                    }
                ],
                "unresolved_quotes": [],
            },
            PermissionDraftStatus.UNAVAILABLE,
            "MODEL_OUTPUT_INVALID",
        ),
    ),
)
def test_invalid_model_suggestions_are_never_repaired(
    payload: object,
    expected_status: PermissionDraftStatus,
    expected_code: str,
) -> None:
    service, _ = _service(payload)

    draft = service.draft("app_demo", _TEXT)

    assert draft.status is expected_status
    assert draft.suggestions == ()
    assert expected_code in {item.code for item in draft.issues}


@pytest.mark.parametrize("mode", ("disabled", "provider_error", "invalid_json"))
def test_model_unavailable_never_blocks_matrix(mode: str) -> None:
    if mode == "disabled":
        service, _ = _service(enabled=False)
    elif mode == "provider_error":
        service, _ = _service(error=True)
    else:
        service, _ = _service({"unexpected": True})

    draft = service.draft("app_demo", _TEXT)

    assert draft.status is PermissionDraftStatus.UNAVAILABLE
    assert draft.suggestions == ()

