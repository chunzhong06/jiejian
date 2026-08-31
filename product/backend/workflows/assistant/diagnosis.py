# =============================================================================
# 确定性错误诊断
#
# 定位
#   把稳定错误码、Runner 阶段和清理事实转换为普通用户可执行的恢复说明。
#
# 职责
#   区分失败区域与阶段｜选择确定性恢复入口｜保留附加清理问题
#
# 边界
#   不用字符串正则猜原因，不调用模型，不把 BLOCK 或 INCONCLUSIVE 当成程序错误。
#
# 调用链
#   Result / API projection → diagnose_error → ErrorDiagnosis
# =============================================================================

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from product.backend.core.errors import ErrorCode
from product.backend.core.lifecycle import RunLifecycle
from product.protocols.runner import CleanupIssueCode, RunnerFailurePhase


DiagnosisRoute = Literal[
    "/workspace",
    "/application",
    "/preparation",
    "/validation",
    "/results",
    "/settings/models",
    "/settings/system",
]


class ErrorArea(StrEnum):
    APPLICATION = "APPLICATION"
    IDENTITY = "IDENTITY"
    RECORDING = "RECORDING"
    PERMISSION_PREPARATION = "PERMISSION_PREPARATION"
    RECOVERY = "RECOVERY"
    TARGET = "TARGET"
    OBSERVER = "OBSERVER"
    RUNNER = "RUNNER"
    STORAGE = "STORAGE"
    MODEL = "MODEL"
    UNKNOWN = "UNKNOWN"


class ErrorPhase(StrEnum):
    APPLICATION_CONNECTION = "APPLICATION_CONNECTION"
    APPLICATION_MAINTENANCE = "APPLICATION_MAINTENANCE"
    IDENTITY_PREPARATION = "IDENTITY_PREPARATION"
    RECORDING = "RECORDING"
    PERMISSION_PREPARATION = "PERMISSION_PREPARATION"
    PREPARE_RECOVERY = "PREPARE_RECOVERY"
    TARGET = "TARGET"
    OBSERVER = "OBSERVER"
    POST_CASE_RECOVERY = "POST_CASE_RECOVERY"
    RUNNER = "RUNNER"
    STORAGE = "STORAGE"
    MODEL = "MODEL"
    UNKNOWN = "UNKNOWN"


class ErrorIntervention(StrEnum):
    USER_ACTION = "USER_ACTION"
    RETRY = "RETRY"
    REVIEW_CONFIGURATION = "REVIEW_CONFIGURATION"
    VERIFY_REAL_STATE = "VERIFY_REAL_STATE"
    REPAIR_RUNTIME = "REPAIR_RUNTIME"
    CONFIGURE_MODEL = "CONFIGURE_MODEL"
    CONTACT_MAINTAINER = "CONTACT_MAINTAINER"


class RecoveryAction(StrEnum):
    CONFIRM_APPLICATION = "CONFIRM_APPLICATION"
    FINISH_ACTIVE_TASKS = "FINISH_ACTIVE_TASKS"
    RELOGIN = "RELOGIN"
    REVIEW_RECORDING = "REVIEW_RECORDING"
    REVIEW_PERMISSION_SETUP = "REVIEW_PERMISSION_SETUP"
    RESTORE_TEST_STATE = "RESTORE_TEST_STATE"
    CONFIRM_REAL_RESULT = "CONFIRM_REAL_RESULT"
    RETRY_CHECK = "RETRY_CHECK"
    OPEN_RESULT = "OPEN_RESULT"
    REPAIR_RUNTIME = "REPAIR_RUNTIME"
    CONFIGURE_MODEL = "CONFIGURE_MODEL"
    CONTACT_MAINTAINER = "CONTACT_MAINTAINER"


class _DiagnosisModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class ErrorDiagnosisContext(_DiagnosisModel):
    error_code: str = Field(min_length=1, max_length=96)
    runner_phase: RunnerFailurePhase | None = None
    cause_code: str | None = Field(default=None, min_length=1, max_length=96)
    cleanup_issue_codes: tuple[CleanupIssueCode, ...] = Field(default=(), max_length=8)
    lifecycle: RunLifecycle | None = None
    readiness_gap_codes: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("cleanup_issue_codes", "readiness_gap_codes")
    @classmethod
    def validate_unique(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if len(set(values)) != len(values):
            raise ValueError("diagnosis facts must be unique")
        return values


class ErrorDiagnosis(_DiagnosisModel):
    area: ErrorArea
    phase: ErrorPhase
    cause: str = Field(min_length=1, max_length=96)
    intervention: ErrorIntervention
    recovery_action: RecoveryAction
    route: DiagnosisRoute
    headline: str = Field(min_length=1, max_length=80)
    short_message: str = Field(min_length=1, max_length=240)
    cleanup_warnings: tuple[str, ...] = Field(default=(), max_length=8)


class _Presentation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    area: ErrorArea
    phase: ErrorPhase
    intervention: ErrorIntervention
    recovery_action: RecoveryAction
    route: DiagnosisRoute
    headline: str
    short_message: str


def _presentation(
    area: ErrorArea,
    phase: ErrorPhase,
    intervention: ErrorIntervention,
    recovery_action: RecoveryAction,
    route: DiagnosisRoute,
    headline: str,
    short_message: str,
) -> _Presentation:
    return _Presentation(
        area=area,
        phase=phase,
        intervention=intervention,
        recovery_action=recovery_action,
        route=route,
        headline=headline,
        short_message=short_message,
    )


_SELF_TARGET = _presentation(
    ErrorArea.APPLICATION,
    ErrorPhase.APPLICATION_CONNECTION,
    ErrorIntervention.USER_ACTION,
    RecoveryAction.CONFIRM_APPLICATION,
    "/application",
    "不能检查界鉴自身",
    "当前应用地址指向了本实例控制面。请返回应用接入页确认真正的被测应用地址。",
)
_SESSION_EXPIRED = _presentation(
    ErrorArea.IDENTITY,
    ErrorPhase.IDENTITY_PREPARATION,
    ErrorIntervention.USER_ACTION,
    RecoveryAction.RELOGIN,
    "/preparation",
    "登录状态已经失效",
    "测试账号会话已过期。请重新登录后再继续录制或检查。",
)
_OBSERVER_INCOMPLETE = _presentation(
    ErrorArea.OBSERVER,
    ErrorPhase.OBSERVER,
    ErrorIntervention.VERIFY_REAL_STATE,
    RecoveryAction.CONFIRM_REAL_RESULT,
    "/preparation",
    "无法确认真实结果",
    "可信观察证据不完整，界鉴不能据此判定安全。请检查观察方式并确认目标的真实状态。",
)

_EXACT_PRESENTATIONS: dict[str, _Presentation] = {
    ErrorCode.SELF_TARGET_FORBIDDEN.value: _SELF_TARGET,
    ErrorCode.RECORD_SESSION_EXPIRED.value: _SESSION_EXPIRED,
    ErrorCode.OBSERVER_INCOMPLETE.value: _OBSERVER_INCOMPLETE,
    "REQUIRED_OBSERVER_INCOMPLETE": _OBSERVER_INCOMPLETE,
    ErrorCode.PROJECT_ARCHIVE_CONFLICT.value: _presentation(
        ErrorArea.APPLICATION,
        ErrorPhase.APPLICATION_MAINTENANCE,
        ErrorIntervention.USER_ACTION,
        RecoveryAction.FINISH_ACTIVE_TASKS,
        "/workspace",
        "当前应用仍有任务在进行",
        "请先结束当前检查、录制或后台任务，确认它们停止后再移除应用。",
    ),
    ErrorCode.IDENTITY_PREPARATION_FAILED.value: _presentation(
        ErrorArea.IDENTITY,
        ErrorPhase.IDENTITY_PREPARATION,
        ErrorIntervention.USER_ACTION,
        RecoveryAction.RELOGIN,
        "/preparation",
        "测试账号没有准备好",
        "界鉴未能建立可用的测试身份。请检查账号登录状态后重试。",
    ),
    ErrorCode.PREPARE_RECOVERY_FAILED.value: _presentation(
        ErrorArea.RECOVERY,
        ErrorPhase.PREPARE_RECOVERY,
        ErrorIntervention.USER_ACTION,
        RecoveryAction.RESTORE_TEST_STATE,
        "/preparation",
        "检查前无法恢复测试现场",
        "为避免从不可信起点执行，界鉴已经停止。请核对恢复步骤和测试资源当前状态。",
    ),
    ErrorCode.TARGET_EXECUTION_FAILED.value: _presentation(
        ErrorArea.TARGET,
        ErrorPhase.TARGET,
        ErrorIntervention.RETRY,
        RecoveryAction.RETRY_CHECK,
        "/validation",
        "业务操作执行失败",
        "目标应用没有完成本次业务操作。请先确认应用可用，再重试当前检查。",
    ),
    ErrorCode.SETUP_STEP_FAILED.value: _presentation(
        ErrorArea.PERMISSION_PREPARATION,
        ErrorPhase.PERMISSION_PREPARATION,
        ErrorIntervention.REVIEW_CONFIGURATION,
        RecoveryAction.REVIEW_PERMISSION_SETUP,
        "/preparation",
        "测试资源准备失败",
        "界鉴未能建立本次权限实验需要的测试资源，请检查业务操作的准备步骤。",
    ),
    ErrorCode.VALUE_EXTRACTION_FAILED.value: _presentation(
        ErrorArea.RECORDING,
        ErrorPhase.RECORDING,
        ErrorIntervention.REVIEW_CONFIGURATION,
        RecoveryAction.REVIEW_RECORDING,
        "/preparation",
        "录制数据已不匹配应用",
        "录制流程无法从当前响应提取所需数据，请重新确认或录制这个业务操作。",
    ),
}

_CLEANUP_WARNINGS: dict[CleanupIssueCode, str] = {
    CleanupIssueCode.POST_CASE_RECOVERY_FAILED: "业务检查结束后，测试现场没有完全恢复。",
    CleanupIssueCode.IDENTITY_CLOSE_FAILED: "测试账号会话没有完全关闭。",
    CleanupIssueCode.RUNTIME_CLOSE_FAILED: "隔离执行环境没有完全关闭。",
    CleanupIssueCode.PROCESS_TREE_CLEANUP_FAILED: "执行子进程没有完全清理。",
}


def diagnose_error(context: ErrorDiagnosisContext) -> ErrorDiagnosis:
    """只依据结构化事实分类；cleanup 始终作为主错误之外的附加信息。"""

    code = context.error_code
    presentation = _EXACT_PRESENTATIONS.get(code)
    if presentation is None:
        presentation = _from_phase(context.runner_phase) or _from_code_family(code)
    if presentation.area is ErrorArea.UNKNOWN and context.readiness_gap_codes:
        presentation = _from_readiness_gaps(context.readiness_gap_codes)
    if presentation.area is ErrorArea.UNKNOWN and context.lifecycle is RunLifecycle.CANCELLED:
        presentation = _presentation(
            ErrorArea.RUNNER,
            ErrorPhase.RUNNER,
            ErrorIntervention.RETRY,
            RecoveryAction.RETRY_CHECK,
            "/validation",
            "本次检查已取消",
            "检查没有形成安全结论；确认应用和测试现场可用后，可以重新开始。",
        )
    warnings = tuple(_CLEANUP_WARNINGS[item] for item in context.cleanup_issue_codes)
    return ErrorDiagnosis(
        area=presentation.area,
        phase=presentation.phase,
        cause=context.cause_code or code,
        intervention=presentation.intervention,
        recovery_action=presentation.recovery_action,
        route=presentation.route,
        headline=presentation.headline,
        short_message=presentation.short_message,
        cleanup_warnings=warnings,
    )


def _from_phase(phase: RunnerFailurePhase | None) -> _Presentation | None:
    if phase is None:
        return None
    if phase is RunnerFailurePhase.PREPARE_RECOVERY:
        return _EXACT_PRESENTATIONS[ErrorCode.PREPARE_RECOVERY_FAILED.value]
    if phase is RunnerFailurePhase.IDENTITY_PREPARATION:
        return _EXACT_PRESENTATIONS[ErrorCode.IDENTITY_PREPARATION_FAILED.value]
    if phase is RunnerFailurePhase.SETUP:
        return _EXACT_PRESENTATIONS[ErrorCode.SETUP_STEP_FAILED.value]
    if phase is RunnerFailurePhase.TARGET:
        return _EXACT_PRESENTATIONS[ErrorCode.TARGET_EXECUTION_FAILED.value]
    if phase in {
        RunnerFailurePhase.BASELINE,
        RunnerFailurePhase.BEFORE,
        RunnerFailurePhase.AFTER,
        RunnerFailurePhase.EVENTUAL,
    }:
        return _OBSERVER_INCOMPLETE
    if phase is RunnerFailurePhase.POST_CASE_RECOVERY:
        return _presentation(
            ErrorArea.RECOVERY,
            ErrorPhase.POST_CASE_RECOVERY,
            ErrorIntervention.USER_ACTION,
            RecoveryAction.RESTORE_TEST_STATE,
            "/preparation",
            "检查后无法恢复测试现场",
            "真实操作已经结束，但测试现场未恢复。请先确认并恢复真实状态，再继续检查。",
        )
    return _presentation(
        ErrorArea.RUNNER,
        ErrorPhase.RUNNER,
        ErrorIntervention.REPAIR_RUNTIME,
        RecoveryAction.REPAIR_RUNTIME,
        "/settings/system",
        "隔离执行没有正常完成",
        "界鉴的隔离执行环境没有正常完成本次任务，请检查运行环境后重试。",
    )


def _from_code_family(code: str) -> _Presentation:
    if code.startswith(("APPLICATION_", "TARGET_UNREACHABLE", "SCOPE_")):
        return _presentation(
            ErrorArea.APPLICATION,
            ErrorPhase.APPLICATION_CONNECTION,
            ErrorIntervention.USER_ACTION,
            RecoveryAction.CONFIRM_APPLICATION,
            "/application",
            "无法连接被测应用",
            "请检查应用地址和运行状态，然后重新确认连接。",
        )
    if code.startswith(("TEST_IDENTITY_", "SECRET_MISSING")):
        return _EXACT_PRESENTATIONS[ErrorCode.IDENTITY_PREPARATION_FAILED.value]
    if code.startswith("RECORD_"):
        return _presentation(
            ErrorArea.RECORDING,
            ErrorPhase.RECORDING,
            ErrorIntervention.USER_ACTION,
            RecoveryAction.REVIEW_RECORDING,
            "/preparation",
            "业务操作录制没有完成",
            "请返回业务流程页检查录制状态，并按页面提示重新完成操作。",
        )
    if code.startswith(("CONTRACT_", "EXECUTION_PROFILE_", "COVERAGE_")):
        return _presentation(
            ErrorArea.PERMISSION_PREPARATION,
            ErrorPhase.PERMISSION_PREPARATION,
            ErrorIntervention.REVIEW_CONFIGURATION,
            RecoveryAction.REVIEW_PERMISSION_SETUP,
            "/preparation",
            "权限检查条件尚未准备好",
            "请返回权限规则页处理当前缺口，再开始检查。",
        )
    if code.startswith(("STORAGE_", "ARTIFACT_", "REPORT_")):
        return _presentation(
            ErrorArea.STORAGE,
            ErrorPhase.STORAGE,
            ErrorIntervention.CONTACT_MAINTAINER,
            RecoveryAction.CONTACT_MAINTAINER,
            "/settings/system",
            "本地数据处理失败",
            "界鉴无法安全读取或保存本地运行数据，请保留现场并检查运行环境。",
        )
    if code.lower().startswith("llm_") or code.startswith("LLM_"):
        return _presentation(
            ErrorArea.MODEL,
            ErrorPhase.MODEL,
            ErrorIntervention.CONFIGURE_MODEL,
            RecoveryAction.CONFIGURE_MODEL,
            "/settings/models",
            "AI 辅助暂时不可用",
            "确定性检查能力不受影响。可检查模型服务配置，或关闭 AI 辅助后继续。",
        )
    if code.startswith(("RUNNER_", "PROCESS_TREE_", "RUNTIME_", "JOB_")):
        return _presentation(
            ErrorArea.RUNNER,
            ErrorPhase.RUNNER,
            ErrorIntervention.REPAIR_RUNTIME,
            RecoveryAction.REPAIR_RUNTIME,
            "/settings/system",
            "隔离执行环境异常",
            "请检查界鉴运行环境，再重试当前检查。",
        )
    return _presentation(
        ErrorArea.UNKNOWN,
        ErrorPhase.UNKNOWN,
        ErrorIntervention.CONTACT_MAINTAINER,
        RecoveryAction.CONTACT_MAINTAINER,
        "/settings/system",
        "本次任务没有正常完成",
        "请保留当前错误代码和运行现场，以便进一步诊断。",
    )


def _from_readiness_gaps(gaps: tuple[str, ...]) -> _Presentation:
    if any(item.startswith(("TEST_IDENTITY_", "MISSING_SUBJECT")) for item in gaps):
        return _EXACT_PRESENTATIONS[ErrorCode.IDENTITY_PREPARATION_FAILED.value]
    if any(
        item.startswith(("ACTION_", "TEST_RESOURCE_", "OBSERVATION_", "RECOVERY_", "SECURITY_EFFECT_", "MISSING_RESOURCE", "MISSING_OBSERVER"))
        for item in gaps
    ):
        return _presentation(
            ErrorArea.RECORDING,
            ErrorPhase.RECORDING,
            ErrorIntervention.REVIEW_CONFIGURATION,
            RecoveryAction.REVIEW_RECORDING,
            "/preparation",
            "业务操作准备尚未闭合",
            "请先补齐录制、测试资源、可信观察和安全恢复中的当前缺口。",
        )
    return _presentation(
        ErrorArea.PERMISSION_PREPARATION,
        ErrorPhase.PERMISSION_PREPARATION,
        ErrorIntervention.REVIEW_CONFIGURATION,
        RecoveryAction.REVIEW_PERMISSION_SETUP,
        "/preparation",
        "权限检查条件尚未准备好",
        "请返回权限规则页处理当前覆盖缺口，再开始检查。",
    )


__all__ = [
    "ErrorArea",
    "ErrorDiagnosis",
    "ErrorDiagnosisContext",
    "ErrorIntervention",
    "ErrorPhase",
    "RecoveryAction",
    "diagnose_error",
]
