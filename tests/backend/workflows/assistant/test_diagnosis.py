# 验证 Assistant diagnosis 的结构化阶段与 cleanup 附加语义。

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

def test_error_diagnosis_uses_structured_phase_and_keeps_cleanup_additive() -> None:
    diagnosis = diagnose_error(
        ErrorDiagnosisContext(
            error_code=ErrorCode.TARGET_EXECUTION_FAILED.value,
            runner_phase=RunnerFailurePhase.TARGET,
            cause_code="HTTP_CONNECTION_RESET",
            cleanup_issue_codes=(CleanupIssueCode.POST_CASE_RECOVERY_FAILED,),
        )
    )
    self_target = diagnose_error(
        ErrorDiagnosisContext(error_code=ErrorCode.SELF_TARGET_FORBIDDEN.value)
    )
    expired = diagnose_error(
        ErrorDiagnosisContext(error_code=ErrorCode.RECORD_SESSION_EXPIRED.value)
    )
    observer = diagnose_error(
        ErrorDiagnosisContext(error_code=ErrorCode.OBSERVER_INCOMPLETE.value)
    )

    assert diagnosis.area is ErrorArea.TARGET
    assert diagnosis.phase is ErrorPhase.TARGET
    assert diagnosis.cause == "HTTP_CONNECTION_RESET"
    assert diagnosis.cleanup_warnings == ("业务检查结束后，测试现场没有完全恢复。",)
    assert self_target.route == "/application"
    assert expired.recovery_action.value == "RELOGIN"
    assert observer.recovery_action.value == "CONFIRM_REAL_RESULT"
