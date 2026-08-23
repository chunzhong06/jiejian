# =============================================================================
# Target Runtime 内部端口
#
# 定位
#   通用安全编排与具体目标操作之间的进程内结构边界。
#
# 职责
#   冻结 Runtime/Case Session 生命周期｜约束通用快照视图｜传递目标观察与基线结果
#
# 边界
#   不包含 Web、HTTP、Cookie、身份秘密、Verdict、Finding、Report 或持久化实现。
#
# 调用链
#   Runner composition → TargetRuntimeRegistry → TargetRuntime / TargetCaseSession
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from product.backend.core.verification.differential import (
    DifferentialExperimentPlan,
)
from product.backend.core.verification.facts import (
    DisclosureProof,
    ExecutionFact,
)
from product.backend.core.verification.permission_coverage import (
    PermissionMutationCase,
    PermissionMutationPlan,
)
from product.backend.core.verification.permissions import (
    ActionDefinition,
    PermissionContract,
    SecurityEffectDefinition,
)
from product.protocols.observer import (
    Correlation,
    ObservationEnvelope,
    ObservationPhase,
    ObserverOutcome,
    ObserverSpec,
)
from product.protocols.execution import EffectBinding, ObserverRequirementBinding


@runtime_checkable
class ExecutionSnapshotView(Protocol):
    """仅暴露通用编排实际读取的冻结快照字段。"""

    project_id: str
    target_type: object
    contract: PermissionContract
    plan: PermissionMutationPlan
    differential_plan: DifferentialExperimentPlan
    observers: tuple[ObserverSpec, ...]
    effect_bindings: tuple[EffectBinding, ...]
    observer_bindings: tuple[ObserverRequirementBinding, ...]


@dataclass(frozen=True, slots=True)
class TargetRuntimeContext:
    """单次 attempt 注入 Runtime 的最小、无持久化上下文。"""

    environ: Mapping[str, str]
    staging: Path
    clock: Callable[[], int]
    cancellation_requested: Callable[[], bool]


@dataclass(frozen=True, slots=True)
class TargetBaselineResult:
    """通用编排可比较的目标基线摘要。"""

    valid: bool
    comparison_fingerprints: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.comparison_fingerprints)) != len(
            self.comparison_fingerprints
        ):
            raise ValueError("baseline comparison fingerprints must be unique")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("baseline reason codes must be unique")
        if self.valid and self.reason_codes:
            raise ValueError("valid baseline cannot contain failure reasons")
        if not self.valid and not self.reason_codes:
            raise ValueError("invalid baseline requires a stable reason")


@dataclass(frozen=True, slots=True)
class TargetObservationResult:
    """目标相关观察桥返回的标准 Envelope 与 Outcome。"""

    envelope: ObservationEnvelope
    outcome: ObserverOutcome


@runtime_checkable
class TargetCaseSession(Protocol):
    """一个 Case 独占的目标状态；TARGET 必须恰好执行一次。"""

    def prepare(self) -> None: ...

    def observe_target(
        self,
        spec: ObserverSpec,
        binding: ObserverRequirementBinding,
        correlation: Correlation,
        phase: ObservationPhase,
    ) -> TargetObservationResult | None: ...

    def evaluate_baseline(
        self,
        baseline_envelopes: tuple[ObservationEnvelope, ...],
        *,
        ignored_case_fields: tuple[str, ...] = (),
    ) -> TargetBaselineResult: ...

    def execute_target(self) -> ExecutionFact: ...

    def resolve_execution(
        self,
        observations: tuple[ObservationEnvelope, ...],
    ) -> ExecutionFact: ...

    def build_disclosure_proof(
        self,
        effect: SecurityEffectDefinition,
        resource_id: str,
        observations: tuple[ObservationEnvelope, ...],
    ) -> DisclosureProof | None: ...

    def cleanup(self) -> None: ...


@runtime_checkable
class TargetRuntime(Protocol):
    """单次 attempt 的目标资源所有者。"""

    def open_case(
        self,
        case: PermissionMutationCase,
        action: ActionDefinition,
    ) -> TargetCaseSession: ...

    def close(self) -> None: ...


@runtime_checkable
class TargetRuntimeFactory(Protocol):
    """按 bounded kind 创建一个 attempt 级 Runtime。"""

    kind: str

    def create(
        self,
        snapshot: ExecutionSnapshotView,
        context: TargetRuntimeContext,
    ) -> TargetRuntime: ...
