# 验证九类 AI surface 共用的缓存、退避和并发 provider 边界。

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from product.backend.infra.llm.adapters.base import LLMInvokeResult, LLMTransportError
from product.backend.infra.llm.config import AIAssistanceSettings, LLMProviderType
from product.backend.workflows.assistant.diagnosis import ErrorDiagnosis
from product.backend.workflows.assistant.service import AssistantService, AssistantStatus
from product.backend.workflows.assistant.surfaces import ResolvedAssistantSurface
from product.backend.workflows.assistant.templates import (
    AssistantEntity,
    AssistantEntityType,
    AssistantFact,
    AssistantSuggestionKind,
    AssistantTemplateId,
    build_surface_input,
)


def _surface(*, fingerprint_seed: str = "one") -> ResolvedAssistantSurface:
    surface_input = build_surface_input(
        AssistantTemplateId.NEXT_STEP,
        subject_id="guide_app",
        facts={"phase": "CHECK_READY", "current_scope_runnable": True, "remaining_gap_count": 1},
        entities=(
            AssistantEntity(
                entity_id="opt_111111111111111111111111",
                entity_type=AssistantEntityType.OPTION,
                display_name="开始检查当前可运行范围",
                facts=(
                    AssistantFact(field="kind", value="START_CURRENT_CHECK"),
                    AssistantFact(field="reason_codes", value=("CURRENT_SCOPE_RUNNABLE",)),
                    AssistantFact(field="priority_tier", value="PRIMARY"),
                    AssistantFact(field="route", value="/validation"),
                ),
            ),
        ),
    )
    return ResolvedAssistantSurface(
        subject_id=surface_input.subject_id,
        state_fingerprint=hashlib.sha256(fingerprint_seed.encode()).hexdigest(),
        surface_input=surface_input,
    )


class _Resolver:
    def __init__(self) -> None:
        self.current = _surface()

    def resolve_project(self, project_id: str, template_id: AssistantTemplateId):
        return self.current

    def resolve_result(self, run_id: str):
        return self.current

    def resolve_error(self, error_code: str, diagnosis: ErrorDiagnosis):
        return self.current


class _Provider:
    provider = LLMProviderType.OPENAI
    profile_name = "assistant-default"

    def __init__(self, resolver: _Resolver, *, error: str | None = None) -> None:
        self.resolver = resolver
        self.error = error
        self.calls = 0

    def invoke(self, prompt: str, *, json_schema: dict[str, object]):
        self.calls += 1
        if self.error is not None:
            raise LLMTransportError(self.error)
        current = self.resolver.current.surface_input
        return LLMInvokeResult(
            model="gpt-test",
            reasoning_effort=None,
            structured_output_mode="json_schema",
            final_payload=json.dumps(
                {
                    "schema_version": "1",
                    "template_id": current.template_id.value,
                    "template_version": "1",
                    "suggestions": [{
                        "kind": AssistantSuggestionKind.NEXT_STEP.value,
                        "entity_ids": [current.entities[0].entity_id],
                        "explanation": "按界鉴确定的当前可运行范围继续。",
                    }],
                },
                ensure_ascii=False,
            ),
            usage=None,
            latency_ms=1,
        )


class _Profiles:
    def __init__(self, provider, *, enabled: bool = True, secret_configured: bool = True) -> None:
        self._provider = provider
        self._secret_configured = secret_configured
        self._settings = AIAssistanceSettings(
            enabled=enabled,
            default_profile_name="assistant-default" if enabled else None,
            updated_at_us=1,
        )

    def get_settings(self):
        return self._settings

    def get(self, name: str):
        return type("Profile", (), {"enabled": True, "secret_configured": self._secret_configured})()

    def resolve_provider(self, name: str):
        return self._provider


def test_service_deduplicates_surface_fingerprint_and_revalidates_cache(tmp_path) -> None:
    resolver = _Resolver()
    provider = _Provider(resolver)
    service = AssistantService(
        tmp_path / "var",
        surfaces=resolver,
        llm_profiles=_Profiles(provider),
        clock_us=lambda: 10,
    )

    assert service.get_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.REFRESH_NEEDED
    assert service.generate_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.READY
    assert service.get_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.READY
    assert service.generate_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.READY
    assert provider.calls == 1

    cache_file = next((tmp_path / "var" / "cache" / "assistant").glob("*.json"))
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert "prompt" not in payload and "response" not in payload and "secret" not in payload
    assert "suggestions" in payload and "recommendations" not in payload
    payload["suggestions"] = [{
        "kind": "NEXT_STEP",
        "entity_ids": ["opt_000000000000000000000000"],
        "explanation": "越过当前实体白名单。",
    }]
    cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert service.get_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.REFRESH_NEEDED
    assert service.generate_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.READY
    assert provider.calls == 2

    resolver.current = _surface(fingerprint_seed="two")
    assert service.get_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.REFRESH_NEEDED
    assert service.generate_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.READY
    assert provider.calls == 3


def test_service_failure_backoff_and_disabled_state_are_provider_cold(tmp_path) -> None:
    resolver = _Resolver()
    provider = _Provider(resolver, error="timeout")
    failing = AssistantService(
        tmp_path / "failed",
        surfaces=resolver,
        llm_profiles=_Profiles(provider),
        clock_us=lambda: 10,
    )
    assert failing.generate_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.BACKOFF
    assert failing.get_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.BACKOFF
    assert failing.generate_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.BACKOFF
    assert provider.calls == 1
    assert failing.generate_project("guide_app", AssistantTemplateId.NEXT_STEP, retry=True).status is AssistantStatus.BACKOFF
    assert provider.calls == 2

    disabled_provider = _Provider(resolver)
    disabled = AssistantService(
        tmp_path / "disabled",
        surfaces=resolver,
        llm_profiles=_Profiles(disabled_provider, enabled=False),
    )
    assert disabled.get_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.DISABLED
    assert disabled.generate_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.DISABLED
    assert disabled_provider.calls == 0


def test_service_exposes_generating_without_duplicate_provider_call(tmp_path) -> None:
    resolver = _Resolver()

    class _BlockingProvider(_Provider):
        def __init__(self) -> None:
            super().__init__(resolver)
            self.entered = threading.Event()
            self.release = threading.Event()

        def invoke(self, prompt: str, *, json_schema: dict[str, object]):
            self.entered.set()
            assert self.release.wait(timeout=3)
            return super().invoke(prompt, json_schema=json_schema)

    provider = _BlockingProvider()
    service = AssistantService(tmp_path / "var", surfaces=resolver, llm_profiles=_Profiles(provider))
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(service.generate_project, "guide_app", AssistantTemplateId.NEXT_STEP)
        assert provider.entered.wait(timeout=3)
        assert service.generate_project("guide_app", AssistantTemplateId.NEXT_STEP).status is AssistantStatus.GENERATING
        provider.release.set()
        assert first.result(timeout=3).status is AssistantStatus.READY
    assert provider.calls == 1
