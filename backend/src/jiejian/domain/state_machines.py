"""所有阶段 0 生命周期转换的唯一领域入口。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, TypeAlias

from .lifecycle import (
    CaseLifecycle,
    CaseVerdict,
    Contract,
    ContractStatus,
    EntityModel,
    Job,
    JobState,
    Project,
    ProjectStatus,
    Run,
    RunLifecycle,
    RunVerdict,
    StateTransitionEvent,
    TestCase,
)
from ..errors import ErrorCode, JiejianError

DomainEntity: TypeAlias = Project | Contract | Run | TestCase | Job


@dataclass(frozen=True, slots=True)
class _Machine:
    field: str
    enum: type[Enum]
    transitions: Mapping[Enum, frozenset[Enum]]


_MACHINES: dict[type[EntityModel], _Machine] = {
    Project: _Machine(
        "status",
        ProjectStatus,
        {
            ProjectStatus.DRAFT: frozenset({ProjectStatus.READY}),
            ProjectStatus.READY: frozenset({ProjectStatus.ARCHIVED}),
        },
    ),
    Contract: _Machine(
        "status",
        ContractStatus,
        {
            ContractStatus.DRAFT: frozenset({ContractStatus.REVIEW}),
            ContractStatus.REVIEW: frozenset(
                {ContractStatus.ACTIVE, ContractStatus.REJECTED}
            ),
            ContractStatus.ACTIVE: frozenset({ContractStatus.SUPERSEDED}),
        },
    ),
    Run: _Machine(
        "lifecycle",
        RunLifecycle,
        {
            RunLifecycle.QUEUED: frozenset(
                {RunLifecycle.PREFLIGHT, RunLifecycle.CANCELLED}
            ),
            RunLifecycle.PREFLIGHT: frozenset(
                {
                    RunLifecycle.PLANNING,
                    RunLifecycle.FAILED,
                    RunLifecycle.CANCELLED,
                    RunLifecycle.SAFETY_STOPPED,
                }
            ),
            RunLifecycle.PLANNING: frozenset(
                {
                    RunLifecycle.EXECUTING,
                    RunLifecycle.FAILED,
                    RunLifecycle.CANCELLED,
                    RunLifecycle.SAFETY_STOPPED,
                }
            ),
            RunLifecycle.EXECUTING: frozenset(
                {
                    RunLifecycle.VERIFYING,
                    RunLifecycle.FAILED,
                    RunLifecycle.CANCELLED,
                    RunLifecycle.SAFETY_STOPPED,
                }
            ),
            RunLifecycle.VERIFYING: frozenset(
                {
                    RunLifecycle.REPORTING,
                    RunLifecycle.FAILED,
                    RunLifecycle.CANCELLED,
                    RunLifecycle.SAFETY_STOPPED,
                }
            ),
            RunLifecycle.REPORTING: frozenset(
                {RunLifecycle.COMPLETED, RunLifecycle.FAILED, RunLifecycle.CANCELLED}
            ),
        },
    ),
    TestCase: _Machine(
        "lifecycle",
        CaseLifecycle,
        {
            CaseLifecycle.PLANNED: frozenset(
                {CaseLifecycle.SNAPSHOTTED, CaseLifecycle.ERROR}
            ),
            CaseLifecycle.SNAPSHOTTED: frozenset(
                {CaseLifecycle.EXECUTED, CaseLifecycle.ERROR}
            ),
            CaseLifecycle.EXECUTED: frozenset(
                {CaseLifecycle.OBSERVED, CaseLifecycle.ERROR}
            ),
            CaseLifecycle.OBSERVED: frozenset(
                {CaseLifecycle.CLEANED, CaseLifecycle.ERROR}
            ),
            CaseLifecycle.CLEANED: frozenset(
                {CaseLifecycle.DONE, CaseLifecycle.ERROR}
            ),
        },
    ),
    Job: _Machine(
        "state",
        JobState,
        {
            JobState.PENDING: frozenset({JobState.RUNNING, JobState.CANCELLED}),
            JobState.RUNNING: frozenset(
                {
                    JobState.SUCCEEDED,
                    JobState.RETRY_WAIT,
                    JobState.FAILED,
                    JobState.CANCELLED,
                }
            ),
            JobState.RETRY_WAIT: frozenset({JobState.RUNNING, JobState.CANCELLED}),
        },
    ),
}


def _machine_for(entity: DomainEntity) -> _Machine:
    machine = _MACHINES.get(type(entity))
    if machine is None:
        raise JiejianError(
            ErrorCode.STATE_INVALID_ENTITY,
            "对象没有已注册的状态机",
            details={"entity_type": type(entity).__name__},
        )
    return machine


def _target_state(machine: _Machine, target: Enum | str) -> Enum:
    if isinstance(target, machine.enum):
        return target
    if isinstance(target, Enum):
        raise JiejianError(
            ErrorCode.STATE_INVALID_TARGET,
            "目标状态属于其他状态机",
            details={"target_type": type(target).__name__},
        )
    try:
        return machine.enum(str(target))
    except ValueError as exc:
        raise JiejianError(
            ErrorCode.STATE_INVALID_TARGET,
            "目标状态不存在",
            details={"target": str(target)},
        ) from exc


def _validate_precondition(entity: DomainEntity, target: Enum) -> None:
    if isinstance(entity, Contract) and target is ContractStatus.ACTIVE and not entity.rules:
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "空契约不能激活",
            details={"entity_id": str(entity.id)},
        )
    if isinstance(entity, Run) and target is RunLifecycle.COMPLETED and entity.verdict is None:
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "运行完成前必须设置独立门禁结论",
            details={"entity_id": str(entity.id)},
        )
    if isinstance(entity, TestCase) and target is CaseLifecycle.DONE and entity.verdict is None:
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "用例结束前必须设置独立用例结论",
            details={"entity_id": str(entity.id)},
        )


def transition_state(
    entity: DomainEntity,
    target: Enum | str,
    *,
    operator: str,
) -> DomainEntity:
    """验证并执行一次状态转换，同时追加不可变事件。"""

    if not operator.strip():
        raise JiejianError(ErrorCode.STATE_OPERATOR_REQUIRED, "状态转换必须记录操作者")

    machine = _machine_for(entity)
    resolved_target = _target_state(machine, target)
    current = getattr(entity, machine.field)
    if resolved_target not in machine.transitions.get(current, frozenset()):
        raise JiejianError(
            ErrorCode.STATE_INVALID_TRANSITION,
            "非法状态转换",
            details={
                "machine": type(entity).__name__,
                "source": current.value,
                "target": resolved_target.value,
            },
        )

    _validate_precondition(entity, resolved_target)
    event = StateTransitionEvent(
        entity_id=entity.id,
        machine=type(entity).__name__,
        source=current.value,
        target=resolved_target.value,
        operator=operator,
    )
    return entity.model_copy(
        update={machine.field: resolved_target, "events": (*entity.events, event)}
    )


def set_run_verdict(run: Run, verdict: RunVerdict | str) -> Run:
    if run.lifecycle not in {RunLifecycle.VERIFYING, RunLifecycle.REPORTING}:
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "只能在验证或报告阶段设置运行结论",
            details={"lifecycle": run.lifecycle.value},
        )
    try:
        resolved = verdict if isinstance(verdict, RunVerdict) else RunVerdict(verdict)
    except ValueError as exc:
        raise JiejianError(ErrorCode.STATE_INVALID_TARGET, "运行结论不存在") from exc
    return run.model_copy(update={"verdict": resolved})


def set_case_verdict(test_case: TestCase, verdict: CaseVerdict | str) -> TestCase:
    if test_case.lifecycle not in {CaseLifecycle.OBSERVED, CaseLifecycle.CLEANED}:
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "只能在已观察或已清理阶段设置用例结论",
            details={"lifecycle": test_case.lifecycle.value},
        )
    try:
        resolved = verdict if isinstance(verdict, CaseVerdict) else CaseVerdict(verdict)
    except ValueError as exc:
        raise JiejianError(ErrorCode.STATE_INVALID_TARGET, "用例结论不存在") from exc
    return test_case.model_copy(update={"verdict": resolved})


def update_contract_rules(
    contract: Contract, rules: tuple[str, ...] | list[str]
) -> Contract:
    if contract.status in {ContractStatus.ACTIVE, ContractStatus.SUPERSEDED}:
        raise JiejianError(
            ErrorCode.CONTRACT_IMMUTABLE,
            "已激活的契约版本不可原地修改",
            details={"contract_id": str(contract.id), "version": contract.version},
        )
    return Contract.model_validate(
        {**contract.model_dump(), "rules": tuple(rules)}
    )


def revise_contract(
    contract: Contract, rules: tuple[str, ...] | list[str]
) -> Contract:
    if contract.status is not ContractStatus.ACTIVE:
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "只有已激活契约可以派生修订版本",
            details={"status": contract.status.value},
        )
    return Contract(
        version=contract.version + 1,
        rules=tuple(rules),
        status=ContractStatus.DRAFT,
        supersedes_id=contract.id,
    )
