# =============================================================================
# Contract 执行绑定
#
# 定位
#   项目治理版本转为新 Run 冻结 PermissionContract 的信任边界
#
# 职责
#   解析项目绑定｜要求版本处于 ACTIVE｜返回不可变执行快照
#
# 边界
#   不选择最近版本、不接受 DRAFT/REVIEW，也不修改治理对象或执行目标。
#
# 调用链
#   ExecutionWorkflow → resolve_execution_contract → PermissionContract
# =============================================================================

from __future__ import annotations

from typing import Any

from product.backend.core.lifecycle import ContractStatus
from product.backend.core.verification.permissions import PermissionContract
from product.backend.core.errors import ErrorCode, JiejianError
def resolve_execution_contract(
    record: Any,
    governed: Any,
) -> PermissionContract:
    """只接受项目绑定的精确 ACTIVE 版本，不提供文件契约回退。"""
    if record.governed_contract_id is None or record.governed_contract_version is None:
        raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "项目尚未绑定 ACTIVE 契约版本")
    if governed is None:
        raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "项目治理契约版本不存在")
    if (
        governed.project_id != record.project_id
        or governed.contract_id != record.governed_contract_id
        or governed.version != record.governed_contract_version
    ):
        raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "项目治理契约绑定不一致")
    if governed.status is not ContractStatus.ACTIVE:
        raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "项目治理契约不是 ACTIVE")
    return governed.snapshot
