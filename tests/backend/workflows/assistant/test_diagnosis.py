# 验证 Assistant diagnosis 的结构化阶段与 cleanup 附加语义。

from __future__ import annotations

from product.backend.core.errors import ErrorCode
from product.backend.workflows.assistant import (
    ErrorArea,
    ErrorDiagnosisContext,
    ErrorPhase,
    diagnose_error,
)
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


def test_project_archive_conflict_has_specific_chinese_recovery() -> None:
    diagnosis = diagnose_error(
        ErrorDiagnosisContext(error_code=ErrorCode.PROJECT_ARCHIVE_CONFLICT.value)
    )

    assert diagnosis.area is ErrorArea.APPLICATION
    assert diagnosis.phase is ErrorPhase.APPLICATION_MAINTENANCE
    assert diagnosis.recovery_action.value == "FINISH_ACTIVE_TASKS"
    assert diagnosis.route == "/check"
    assert diagnosis.headline == "当前应用仍有任务在进行"
    assert "结束当前检查、录制或后台任务" in diagnosis.short_message
