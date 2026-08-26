# 验证项目就绪状态的确定性事实投影。

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

def _project(project_id: str, *, status: ProjectStatus) -> ProjectRecord:
    return ProjectRecord(
        project_id=project_id,
        name="演示应用",
        status=status,
        target_type=TargetType.WEB,
        created_at_us=1,
        updated_at_us=1,
    )

def test_draft_project_requires_application_connection(tmp_path) -> None:
    application = ApplicationCore(tmp_path / "var", environ={})
    try:
        with application.uow_factory() as work:
            work.projects.add(_project("draft-app", status=ProjectStatus.DRAFT))
            work.commit()

        view = application.project_readiness.get("draft-app")

        assert view.application_connected is False
        assert view.endpoint_status == "NEEDS_CONNECTION"
        assert view.next_required_action == "CONNECT_APPLICATION"
    finally:
        application.close()

def test_legacy_profile_project_recovers_without_reconnecting(tmp_path) -> None:
    application = ApplicationCore(tmp_path / "var", environ={})
    try:
        with application.uow_factory() as work:
            work.projects.add(_project("legacy-app", status=ProjectStatus.READY))
            work.execution_profiles.add(
                ExecutionProfileRecord(
                    profile_id="legacy-profile",
                    project_id="legacy-app",
                    source_path=str(tmp_path / "profile.json"),
                    source_hash="a" * 64,
                    contract_id="legacy-contract",
                    contract_version=1,
                    contract_fingerprint="b" * 64,
                    plan_fingerprint="c" * 64,
                    engine_version="test",
                    created_at_us=1,
                    updated_at_us=1,
                )
            )
            work.commit()

        view = ProjectReadinessService(application.uow_factory).get("legacy-app")

        assert view.application_connected is True
        assert view.endpoint_status == "LEGACY_PROFILE"
        assert view.execution_profile_available is True
        assert view.next_required_action == "RECORD_FLOW"
    finally:
        application.close()
