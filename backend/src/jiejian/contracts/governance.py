# =============================================================================
# Contract 治理规则
#
# 定位
#   ContractVersion 状态转换和修订的纯领域规则
#
# 职责
#   限制合法状态迁移｜禁止修改 ACTIVE 版本｜生成新的修订版本
#
# 调用链
#   ContractGovernanceService → governance rules → ContractVersion / SecurityContract
# =============================================================================

from .models import (
    ContractAuditAction,
    ContractAuditEntry,
    ContractProvenance,
    ContractVersion,
)
from ..domain.lifecycle import ContractStatus
from ..verification.models import ContractRule, SecurityContract
from ..errors import ErrorCode, JiejianError


_CONTRACT_TRANSITIONS = {
    ContractStatus.DRAFT: {ContractStatus.REVIEW: ContractAuditAction.SUBMITTED},
    ContractStatus.REVIEW: {
        ContractStatus.ACTIVE: ContractAuditAction.ACTIVATED,
        ContractStatus.REJECTED: ContractAuditAction.REJECTED,
    },
    ContractStatus.ACTIVE: {
        ContractStatus.SUPERSEDED: ContractAuditAction.SUPERSEDED,
    },
}


def transition_contract_version(
    contract: ContractVersion,
    target: ContractStatus,
    *,
    actor: str,
    occurred_at_us: int,
) -> ContractVersion:
    action = _CONTRACT_TRANSITIONS.get(contract.status, {}).get(target)
    if action is None:
        raise JiejianError(
            ErrorCode.STATE_INVALID_TRANSITION,
            "非法契约版本状态转换",
            details={"source": contract.status.value, "target": target.value},
        )
    entry = ContractAuditEntry(action=action, actor=actor, occurred_at_us=occurred_at_us)
    return ContractVersion.model_validate(
        {
            **contract.model_dump(),
            "status": target,
            "snapshot": contract.snapshot.model_copy(update={"status": target}),
            "audit": (*contract.audit, entry),
            "updated_at_us": occurred_at_us,
        }
    )


def revise_contract_version(
    active: ContractVersion,
    *,
    rules: tuple[ContractRule, ...],
    provenance: ContractProvenance,
    actor: str,
    occurred_at_us: int,
) -> ContractVersion:
    if active.status is not ContractStatus.ACTIVE:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "只有 ACTIVE 契约可以修订")
    next_version = active.version + 1
    snapshot = SecurityContract(
        id=active.contract_id,
        version=next_version,
        status=ContractStatus.DRAFT,
        rules=rules,
    )
    return ContractVersion(
        project_id=active.project_id,
        contract_id=active.contract_id,
        version=next_version,
        status=ContractStatus.DRAFT,
        snapshot=snapshot,
        provenance=provenance,
        supersedes_version=active.version,
        audit=(
            ContractAuditEntry(
                action=ContractAuditAction.CREATED,
                actor=actor,
                occurred_at_us=occurred_at_us,
            ),
        ),
        created_at_us=occurred_at_us,
        updated_at_us=occurred_at_us,
    )

__all__ = ["revise_contract_version", "transition_contract_version"]
