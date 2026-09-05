# 验证权限草稿只整理用户原文与正式原子选项，失败或异常输出都不改变权限事实。

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.permission_semantics import PermissionExpectation
from product.backend.core.business_boundary import BusinessRevisionState
from tests.fixtures.assurance import actor, action, permission
from product.backend.infra.llm.adapters.base import LLMTransportError
from product.backend.workflows.permission_drafting import (
    PermissionDraftService,
    PermissionDraftStatus,
)


_OPTION_ID = "opt_" + "1" * 32
_TEXT = "Bob 可以读取自己的文件。"


class _Boundaries:
    def __init__(self) -> None:
        self.oracle = (7, (("pin_1", 3, "hash"),))
        self.current = SimpleNamespace(actors=(actor().model_copy(update={"project_id": "app_demo", "display_name": "Bob"}),),
            actions=(action().model_copy(update={"project_id": "app_demo", "display_name": "读取文件"}),),
            permission_intents=(permission().model_copy(update={"project_id": "app_demo"}),))

    def view(self, project_id: str):
        assert project_id == "app_demo"
        return self.current


class _Provider:
    def __init__(self, payload: object = None, *, error: bool = False) -> None:
        self.payload = payload
        self.error = error
        self.calls = 0
        self.prompt = ""

    def invoke(self, prompt: str, *, json_schema: dict[str, object]):
        self.calls += 1
        self.prompt = prompt
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
    permissions = _Boundaries()
    ids = iter([_OPTION_ID] + [f"opt_{number:032x}" for number in range(1, 300)])
    service = PermissionDraftService(
        business_boundaries=permissions,
        llm_profiles=_Profiles(_Provider(payload, error=error), enabled=enabled),
        option_id_factory=lambda: next(ids),
    )
    return service, permissions


def test_valid_option_is_ready_for_review_without_oracle_change() -> None:
    service, permissions = _service(
        {
            "suggestions": [
                {
                    "option_id": _OPTION_ID,
                    "expectation": "ALLOW",
                    "source_quote": _TEXT,
                }
            ],
            "unresolved_quotes": [],
        }
    )
    before = permissions.oracle

    draft = service.draft("app_demo", _TEXT)

    assert draft.status is PermissionDraftStatus.READY_FOR_REVIEW
    assert draft.suggestions[0].business_action_id == action().action_id
    assert draft.suggestions[0].option_ids == (_OPTION_ID,)
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


def _suggestion(option_id=_OPTION_ID, expectation="ALLOW", quote=_TEXT):
    return {"option_id": option_id, "expectation": expectation, "source_quote": quote}


def test_atomic_universe_is_complete_without_existing_permissions_and_opaque():
    service, boundaries = _service({"suggestions": [_suggestion()], "unresolved_quotes": []})
    boundaries.current.permission_intents = ()
    boundaries.current.actors += (actor("bar_" + "2" * 32).model_copy(update={"project_id": "app_demo"}),)
    draft = service.draft("app_demo", _TEXT)
    provider = service._llm_profiles.provider
    data = json.loads(provider.prompt.split("USER_DATA=", 1)[1])
    assert len(data["options"]) == 12
    assert all(set(item) == {"option_id", "subject", "action", "resource_owner", "effect", "relation", "current_expectation"} for item in data["options"])
    assert all(item["relation"] in ({"OWNS", "SAME_ROLE_OTHER_ACCOUNT"} if item["subject"] == item["resource_owner"] else {"OTHER_ROLE"}) for item in data["options"])
    assert all(item["current_expectation"] is None for item in data["options"])
    for forbidden in ("bar_", "bac_", "bef_", "pin_", "source_root", "Observer", "secret_ref"):
        assert forbidden not in provider.prompt
    assert draft.status is PermissionDraftStatus.READY_FOR_REVIEW


@pytest.mark.parametrize("different", [False, True])
def test_effects_merge_only_for_same_expectation_and_keep_atomic_ids(different):
    service, _ = _service({"suggestions": [_suggestion(), _suggestion(f"opt_{1:032x}", "DENY" if different else "ALLOW")], "unresolved_quotes": []})
    draft = service.draft("app_demo", _TEXT)
    assert draft.status is PermissionDraftStatus.READY_FOR_REVIEW
    assert len(draft.suggestions) == (2 if different else 1)
    assert sum(len(item.protected_effect_ids) for item in draft.suggestions) == 2
    if not different:
        item = draft.suggestions[0]
        assert item.option_ids == (_OPTION_ID, f"opt_{1:032x}")
        assert item.protected_effect_ids == tuple(effect.effect_id for effect in action().effect_catalog)
        assert len(item.effect_display_names) == 2
        assert item.current_expectation is None
        assert item.source_quotes == (_TEXT,)


@pytest.mark.parametrize("case", ["no_actors", "inactive_actor", "inactive_action", "large_universe"])
def test_empty_inactive_or_large_universe_never_calls_provider(case):
    service, boundaries = _service({"suggestions": [], "unresolved_quotes": []})
    if case == "no_actors":
        boundaries.current.actors = ()
    elif case == "inactive_actor":
        boundaries.current.actors = (boundaries.current.actors[0].model_copy(update={"effective_state": BusinessRevisionState.RETIRED}),)
    elif case == "inactive_action":
        boundaries.current.actions = (boundaries.current.actions[0].model_copy(update={"effective_state": BusinessRevisionState.RETIRED}),)
    else:
        boundaries.current.actors = tuple(actor(f"bar_{number:032x}").model_copy(update={"project_id": "app_demo"}) for number in range(1, 9))
    draft = service.draft("app_demo", _TEXT)
    assert draft.status is PermissionDraftStatus.PARTIAL and draft.suggestions == ()
    assert draft.issues[0].code == ("OPTION_UNIVERSE_TOO_LARGE" if case == "large_universe" else "OPTION_UNIVERSE_EMPTY")
    assert service._llm_profiles.provider.calls == 0


def test_uncovered_original_text_is_preserved_even_when_model_omits_it():
    service, _ = _service({"suggestions": [_suggestion()], "unresolved_quotes": []})
    draft = service.draft("app_demo", _TEXT + "管理员不能删除。")
    assert draft.status is PermissionDraftStatus.PARTIAL
    assert any(issue.code == "UNRESOLVED_TEXT" and issue.source_quote == "管理员不能删除。" for issue in draft.issues)


def test_long_uncovered_text_is_returned_as_contiguous_bounded_fragments():
    service, _ = _service({"suggestions": [], "unresolved_quotes": []})
    text = "请手工确认权限" * 200
    draft = service.draft("app_demo", text)
    fragments = [item.source_quote for item in draft.issues if item.code == "UNRESOLVED_TEXT"]
    assert fragments and all(len(item) <= 512 and item in text for item in fragments)
    assert "".join(fragments) == text


def test_conflicting_atom_is_removed_while_other_effect_is_kept():
    service, _ = _service({"suggestions": [_suggestion(), _suggestion(expectation="DENY"), _suggestion(f"opt_{1:032x}")], "unresolved_quotes": []})
    draft = service.draft("app_demo", _TEXT)
    assert draft.status is PermissionDraftStatus.PARTIAL
    assert draft.suggestions[0].option_ids == (f"opt_{1:032x}",)
    assert "CONFLICTING_SUGGESTIONS" in {item.code for item in draft.issues}


def test_provider_return_cannot_apply_to_changed_boundary():
    service, boundaries = _service()
    before = boundaries.oracle
    def invoke(*args, **kwargs):
        boundaries.current.actors = (boundaries.current.actors[0].model_copy(update={"revision": 2}),)
        return SimpleNamespace(final_payload=json.dumps({"suggestions": [_suggestion()], "unresolved_quotes": []}))
    service._llm_profiles.provider.invoke = invoke
    draft = service.draft("app_demo", _TEXT)
    assert draft.status is PermissionDraftStatus.UNAVAILABLE and draft.suggestions == ()
    assert draft.issues[0].code == "BOUNDARY_CHANGED"
    assert boundaries.oracle == before


def test_technical_binding_change_does_not_invalidate_formal_boundary_fingerprint():
    service, boundaries = _service()
    def invoke(*args, **kwargs):
        boundaries.current.actor_bindings = ("technical-only-change",)
        return SimpleNamespace(final_payload=json.dumps({"suggestions": [_suggestion()], "unresolved_quotes": []}))
    service._llm_profiles.provider.invoke = invoke
    assert service.draft("app_demo", _TEXT).status is PermissionDraftStatus.READY_FOR_REVIEW
    assert not hasattr(service, "_uow_factory") and not hasattr(service, "_cache")
    assert set(vars(service)) == {"_business_boundaries", "_llm_profiles", "_option_id_factory"}


@pytest.mark.parametrize("payload", ["{}" + " " * 16_384, json.dumps({"suggestions": [{"option_id": _OPTION_ID, "expectation": "ALLOW", "source_quote": _TEXT, "command": "forbidden"}]}),
    json.dumps({"suggestions": [_suggestion()] * 33}), "not-json"])
def test_provider_payload_budget_and_unknown_fields_fail_closed(payload):
    service, _ = _service()
    service._llm_profiles.provider.invoke = lambda *_args, **_kwargs: SimpleNamespace(final_payload=payload)
    draft = service.draft("app_demo", _TEXT)
    assert draft.status is PermissionDraftStatus.UNAVAILABLE and draft.suggestions == ()
    assert draft.issues[0].code == "MODEL_OUTPUT_INVALID"


def test_unconfigured_profile_and_fake_unresolved_quote_are_explicit():
    service, _ = _service({"suggestions": [], "unresolved_quotes": ["编造原文"]})
    draft = service.draft("app_demo", _TEXT)
    assert {item.code for item in draft.issues} == {"UNRESOLVED_QUOTE_INVALID", "UNRESOLVED_TEXT"}
    service._llm_profiles.get = lambda _: SimpleNamespace(enabled=True, secret_configured=False)
    assert service.draft("app_demo", _TEXT).issues[0].code == "MODEL_UNCONFIGURED"
