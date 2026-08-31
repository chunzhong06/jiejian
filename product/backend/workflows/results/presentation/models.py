# 确定性结果投影的不可变只读 View。

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.lifecycle import RunLifecycle, RunVerdict
from product.backend.core.repair import (
    RepairRequirementView,
    RepairVerification,
    RepairVerificationStatus,
)
from product.backend.core.verification.breakpoints import (
    BreakpointPrecision,
    BreakpointType,
)
from product.backend.core.verification.continuity import AuthorizationContinuityState
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect
from product.backend.core.verification.trace import ExecutionTrace, TraceEventKind
from product.protocols.observer import ObserverType

class _PresentationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

class PresentedCaseVerdict(StrEnum):
    SAFE = "SAFE"
    VULNERABLE = "VULNERABLE"
    INCONCLUSIVE = "INCONCLUSIVE"

class ResultEvidenceSource(_PresentationModel):
    """把单个已发布观察来源投影为只读、可解释状态。"""

    observer_type: ObserverType
    label: str = Field(min_length=1, max_length=80)
    role: Literal["KEY", "SUPPORTING"]
    status: Literal["FOUND", "NOT_FOUND", "UNAVAILABLE"]
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=8192)

class ResultWitnessItem(_PresentationModel):
    kind: Literal[
        "PERMISSION_REQUIREMENT",
        "ACTUAL_IDENTITY",
        "PROTECTED_EFFECT",
        "AUTHORIZATION_CONTINUITY",
        "BREAKPOINT",
        "AMPLIFIERS",
        "CONFIRMED_IMPACT",
    ]
    label: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=240)
    event_id: str | None = Field(default=None, min_length=1, max_length=160)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=128)

class ResultConfirmedImpact(_PresentationModel):
    event_id: str = Field(min_length=1, max_length=160)
    parent_event_ids: tuple[str, ...] = Field(default=(), max_length=16)
    kind: TraceEventKind
    semantic_key: str = Field(min_length=1, max_length=64)
    effect_id: str | None = Field(default=None, min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=240)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=128)

class ResultDiagnosis(_PresentationModel):
    case_id: str = Field(min_length=1, max_length=160)
    action_id: str = Field(min_length=1, max_length=160)
    breakpoint_type: BreakpointType | None
    precision: BreakpointPrecision
    continuity_state: AuthorizationContinuityState
    first_violation_event_id: str | None = Field(default=None, min_length=1, max_length=160)
    range_start_event_id: str | None = Field(default=None, min_length=1, max_length=160)
    range_end_event_id: str | None = Field(default=None, min_length=1, max_length=160)
    amplifier_types: tuple[BreakpointType, ...] = Field(default=(), max_length=5)
    summary: str = Field(min_length=1, max_length=320)
    minimal_witness: tuple[ResultWitnessItem, ...] = Field(min_length=7, max_length=7)
    confirmed_impacts: tuple[ResultConfirmedImpact, ...] = Field(
        default=(),
        max_length=512,
    )
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_witness_order(self) -> ResultDiagnosis:
        if (
            self.breakpoint_type is None
            and self.precision is not BreakpointPrecision.VIOLATION_ONLY
        ):
            raise ValueError("unlocated diagnosis must use VIOLATION_ONLY precision")
        if self.precision is BreakpointPrecision.EXACT and (
            self.first_violation_event_id is None
            or self.range_start_event_id is not None
            or self.range_end_event_id is not None
        ):
            raise ValueError("exact diagnosis requires one violation event")
        if self.precision is BreakpointPrecision.RANGE and (
            self.first_violation_event_id is not None
            or self.range_start_event_id is None
            or self.range_end_event_id is None
        ):
            raise ValueError("range diagnosis requires only published boundaries")
        if self.precision is BreakpointPrecision.VIOLATION_ONLY and any(
            value is not None
            for value in (
                self.first_violation_event_id,
                self.range_start_event_id,
                self.range_end_event_id,
            )
        ):
            raise ValueError("violation-only diagnosis cannot claim a path location")
        if len(set(self.amplifier_types)) != len(self.amplifier_types) or (
            self.breakpoint_type is not None
            and self.breakpoint_type in self.amplifier_types
        ):
            raise ValueError("diagnosis primary and amplifier types must be separate")
        expected = (
            "PERMISSION_REQUIREMENT",
            "ACTUAL_IDENTITY",
            "PROTECTED_EFFECT",
            "AUTHORIZATION_CONTINUITY",
            "BREAKPOINT",
            "AMPLIFIERS",
            "CONFIRMED_IMPACT",
        )
        if tuple(item.kind for item in self.minimal_witness) != expected:
            raise ValueError("minimal witness order is fixed")
        if len({item.event_id for item in self.confirmed_impacts}) != len(
            self.confirmed_impacts
        ):
            raise ValueError("confirmed impacts must have unique event IDs")
        return self

class ResultClaimBoundary(_PresentationModel):
    """逐维陈述当前已发布事实能够支持的最强业务主张。"""

    surface_response_status: ExecutionOutcome
    business_effect_status: ObservedEffect
    actual_identity_status: Literal["CONFIRMED", "UNAVAILABLE"]
    breakpoint_precision: BreakpointPrecision | None = None
    repair_status: RepairVerificationStatus | None = None
    supported_statement: str = Field(min_length=1, max_length=480)
    unsupported_statements: tuple[str, ...] = Field(default=(), max_length=16)

class ResultEvidenceExplanation(_PresentationModel):
    """解释一条已发布事实能证明什么，并保留不能越过的证据边界。"""

    label: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=160)
    step: str = Field(min_length=1, max_length=160)
    proves: str = Field(min_length=1, max_length=480)
    does_not_prove: str = Field(min_length=1, max_length=480)
    relevance: str = Field(min_length=1, max_length=320)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=128)
    component: str | None = Field(default=None, min_length=1, max_length=160)
    observed_at_us: int | None = Field(default=None, ge=0)

class ResultPresentationIssue(_PresentationModel):
    finding_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    subject_group: str = Field(min_length=1, max_length=160)
    action_id: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=160)
    resource: str = Field(min_length=1, max_length=160)
    relation: str = Field(min_length=1, max_length=160)
    expectation: str = Field(min_length=1, max_length=240)
    surface_result: str = Field(min_length=1, max_length=240)
    actual_result: str = Field(min_length=1, max_length=240)
    conclusion: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=480)
    planned_identity_id: str = Field(min_length=1, max_length=64)
    planned_identity_label: str | None = Field(default=None, min_length=1, max_length=128)
    actual_identity_status: Literal["CONFIRMED", "UNAVAILABLE"] = "UNAVAILABLE"
    actual_identity_id: str | None = Field(default=None, min_length=1, max_length=160)
    actual_identity_label: str | None = Field(default=None, min_length=1, max_length=160)
    severity: Literal["unknown", "low", "medium", "high", "critical"]
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=8192)
    evidence_sources: tuple[ResultEvidenceSource, ...] = Field(
        default=(),
        max_length=256,
    )
    diagnosis: ResultDiagnosis | None = None
    claim_boundary: ResultClaimBoundary
    evidence_explanations: tuple[ResultEvidenceExplanation, ...] = Field(
        default=(),
        max_length=256,
    )
    verdict: PresentedCaseVerdict
    occurrence_status: str | None = Field(default=None, max_length=32)
    repair_requirement: RepairRequirementView | None = None

class ResultRelevantIntent(_PresentationModel):
    intent_id: str = Field(pattern=r"^pin_[0-9a-f]{32}$")
    revision: int = Field(ge=1)
    intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    display_label: str | None = Field(default=None, pattern=r"^P-[0-9]{3,4}$")
    expectation: Literal["ALLOW", "DENY"] | None = None
    business_statement: str | None = Field(default=None, min_length=1, max_length=640)

class ResultChangeVerification(_PresentationModel):
    """结果页需要的变化重验身份与权限范围，不暴露源码指纹。"""

    change_id: str = Field(pattern=r"^chg_[0-9a-f]{32}$")
    required_intents: tuple[ResultRelevantIntent, ...] = Field(
        default=(),
        max_length=4096,
    )

class ResultPresentation(_PresentationModel):
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=64)
    project_name: str = Field(min_length=1, max_length=128)
    run_lifecycle: RunLifecycle
    verdict: RunVerdict | None
    policy_epoch: int = Field(ge=0)
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    relevant_intents: tuple[ResultRelevantIntent, ...] = Field(
        default=(),
        max_length=4096,
    )
    change_verification: ResultChangeVerification | None = None
    repair_verification: RepairVerification | None = None
    headline: str = Field(min_length=1, max_length=160)
    scope_statement: str = Field(min_length=1, max_length=320)
    checked_count: int = Field(ge=0)
    safe_count: int = Field(ge=0)
    problem_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    uncovered_count: int = Field(ge=0)
    execution_problem: str | None = Field(default=None, max_length=320)
    execution_traces: tuple[ExecutionTrace, ...] = ()
    issues: tuple[ResultPresentationIssue, ...] = ()
    limitations: tuple[str, ...] = Field(default=(), max_length=128)
