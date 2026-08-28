# 验证 Assistant service 的缓存去重、退避与并发 provider 边界。

from __future__ import annotations
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.llm.adapters.base import LLMInvokeResult, LLMTransportError
from product.backend.infra.llm.config import AIAssistanceSettings, LLMProviderType
from product.backend.infra.storage import ExecutionProfileRecord, ProjectRecord
from product.backend.workflows.assistant import (
    ASSISTANT_TEMPLATES,
    AssistantFactField,
    AssistantTemplateId,
    ErrorArea,
    ErrorDiagnosisContext,
    ErrorPhase,
    GuidanceOptionKind,
    GuidancePriorityTier,
    build_guidance_snapshot,
    build_template_input,
    diagnose_error,
    parse_assistant_result,
    render_assistant_prompt,
)
from product.backend.workflows.assistant.service import AssistantService, AssistantStatus
from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.projects.readiness import ProjectReadinessService, ProjectReadinessView
from product.backend.workflows.security_setup.checks import (
    CheckPreview,
    CheckPreviewAction,
    CheckPreviewGap,
)
from product.protocols import TargetType
from product.protocols.runner import CleanupIssueCode, RunnerFailurePhase

def _guidance_readiness(
    *,
    runnable: bool,
    remaining_gap_count: int,
) -> ProjectReadinessView:
    return ProjectReadinessView(
        project_id="guide-app",
        project_status=ProjectStatus.READY,
        application_connected=True,
        endpoint_status="CONFIRMED",
        source_analysis_status="COMPLETED",
        discovered_role_count=2,
        confirmed_role_count=2,
        discovered_action_count=2,
        confirmed_action_count=2,
        execution_profile_available=runnable,
        completed_flow_available=True,
        active_contract_available=runnable,
        current_scope_runnable=runnable,
        remaining_gap_count=remaining_gap_count,
        active_tasks=(),
        latest_verified_run_id="run-guide-1" if runnable else None,
        next_required_action="RUN_CHECK" if runnable else "RECORD_FLOW",
    )

def _guidance_gap(code: str, path: str, label: str) -> CheckPreviewGap:
    return CheckPreviewGap(
        code=code,
        message=label,
        next_path=path,
        next_label=label,
    )

class _AssistantProvider:
    provider = LLMProviderType.OPENAI
    profile_name = "assistant-default"

    def __init__(self, guidance, *, error: str | None = None) -> None:
        self.guidance = guidance
        self.error = error
        self.calls = 0

    def invoke(self, prompt: str, *, json_schema: dict[str, object]):
        self.calls += 1
        if self.error is not None:
            raise LLMTransportError(self.error)
        option_id = self.guidance.get("guide-app").options[0].option_id
        return LLMInvokeResult(
            model="gpt-test",
            reasoning_effort=None,
            structured_output_mode="json_schema",
            final_payload=json.dumps({
                "schema_version": "1",
                "template_id": "jiejian.next_step",
                "template_version": "1",
                "recommendations": [{"option_id": option_id, "explanation": "按系统确定的下一步继续。"}],
            }, ensure_ascii=False),
            usage=None,
            latency_ms=1,
        )

class _AssistantProfiles:
    def __init__(
        self,
        guidance,
        provider,
        *,
        enabled: bool = True,
        secret_configured: bool = True,
    ) -> None:
        self._guidance = guidance
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
        return type(
            "Profile",
            (),
            {"enabled": True, "secret_configured": self._secret_configured},
        )()

    def resolve_provider(self, name: str):
        return self._provider

def test_assistant_service_deduplicates_fingerprint_and_keeps_cache_whitelist(tmp_path) -> None:
    gap = _guidance_gap("OBSERVATION_UNCONFIRMED", "/flows", "去确认观察方式")
    preview = CheckPreview(
        project_id="guide-app",
        ready=True,
        actions=(),
        gaps=(gap,),
        next_path="/flows",
        next_label="去确认观察方式",
        case_count=1,
        differential_pair_count=1,
    )
    current = [_guidance_readiness(runnable=True, remaining_gap_count=1)]
    guidance = type("Guidance", (), {"get": lambda self, project_id: build_guidance_snapshot(current[0], preview)})()
    provider = _AssistantProvider(guidance)
    service = AssistantService(tmp_path / "var", guidance=guidance, llm_profiles=_AssistantProfiles(guidance, provider), clock_us=lambda: 10)

    assert service.get("guide-app").status is AssistantStatus.REFRESH_NEEDED
    assert service.refresh("guide-app").status is AssistantStatus.READY
    assert service.get("guide-app").status is AssistantStatus.READY
    assert service.refresh("guide-app").status is AssistantStatus.READY
    assert provider.calls == 1

    cache_file = next((tmp_path / "var" / "cache" / "assistant").glob("*.json"))
    cache_payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert "prompt" not in cache_payload
    assert "response" not in cache_payload
    assert "secret" not in cache_payload
    assert set(cache_payload) == {
        "schema_version", "entry_type", "provider", "profile", "model", "reasoning_setting",
        "template_id", "template_version", "state_fingerprint", "recommendations", "generated_at_us",
    }
    cache_payload["recommendations"] = [
        {"option_id": "opt_000000000000000000000000", "explanation": "越过当前白名单"}
    ]
    cache_file.write_text(json.dumps(cache_payload, ensure_ascii=False), encoding="utf-8")
    assert service.get("guide-app").status is AssistantStatus.REFRESH_NEEDED
    assert service.refresh("guide-app").status is AssistantStatus.READY
    assert provider.calls == 2

    current[0] = _guidance_readiness(runnable=True, remaining_gap_count=2)
    assert service.get("guide-app").status is AssistantStatus.REFRESH_NEEDED
    assert service.refresh("guide-app").status is AssistantStatus.READY
    assert provider.calls == 3

def test_assistant_service_failure_backoff_and_disabled_are_provider_cold(tmp_path) -> None:
    guidance = type("Guidance", (), {"get": lambda self, project_id: build_guidance_snapshot(_guidance_readiness(runnable=True, remaining_gap_count=1))})()
    provider = _AssistantProvider(guidance, error="timeout")
    failing = AssistantService(tmp_path / "failed", guidance=guidance, llm_profiles=_AssistantProfiles(guidance, provider), clock_us=lambda: 10)

    assert failing.refresh("guide-app").status is AssistantStatus.BACKOFF
    assert failing.get("guide-app").status is AssistantStatus.BACKOFF
    assert failing.refresh("guide-app").status is AssistantStatus.BACKOFF
    assert provider.calls == 1
    assert failing.refresh("guide-app", retry=True).status is AssistantStatus.BACKOFF
    assert provider.calls == 2

    disabled_provider = _AssistantProvider(guidance)
    disabled = AssistantService(
        tmp_path / "disabled",
        guidance=guidance,
        llm_profiles=_AssistantProfiles(guidance, disabled_provider, enabled=False),
    )
    assert disabled.get("guide-app").status is AssistantStatus.DISABLED
    assert disabled.refresh("guide-app").status is AssistantStatus.DISABLED
    assert disabled_provider.calls == 0

    missing_secret = AssistantService(
        tmp_path / "missing-secret",
        guidance=guidance,
        llm_profiles=_AssistantProfiles(
            guidance,
            disabled_provider,
            secret_configured=False,
        ),
    )
    assert missing_secret.get("guide-app").status is AssistantStatus.DISABLED
    assert missing_secret.refresh("guide-app").status is AssistantStatus.DISABLED
    assert disabled_provider.calls == 0

def test_assistant_service_exposes_generating_without_duplicate_provider_call(tmp_path) -> None:
    guidance = type(
        "Guidance",
        (),
        {
            "get": lambda self, project_id: build_guidance_snapshot(
                _guidance_readiness(runnable=True, remaining_gap_count=1)
            )
        },
    )()

    class BlockingProvider(_AssistantProvider):
        def __init__(self) -> None:
            super().__init__(guidance)
            self.entered = threading.Event()
            self.release = threading.Event()

        def invoke(self, prompt: str, *, json_schema: dict[str, object]):
            self.entered.set()
            assert self.release.wait(timeout=3)
            return super().invoke(prompt, json_schema=json_schema)

    provider = BlockingProvider()
    service = AssistantService(
        tmp_path / "var",
        guidance=guidance,
        llm_profiles=_AssistantProfiles(guidance, provider),
        clock_us=lambda: 10,
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(service.refresh, "guide-app")
        assert provider.entered.wait(timeout=3)
        assert service.refresh("guide-app").status is AssistantStatus.GENERATING
        provider.release.set()
        assert first.result(timeout=3).status is AssistantStatus.READY
    assert provider.calls == 1
