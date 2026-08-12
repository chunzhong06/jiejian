# =============================================================================
# Contract 执行绑定
#
# 定位
#   项目治理版本转为新 Run 冻结 SecurityContract 的信任边界
#
# 职责
#   解析项目绑定｜要求版本处于 ACTIVE｜返回不可变执行快照
#
# 调用链
#   ExecutionRequestService → resolve_execution_contract → Storage / SecurityContract
# =============================================================================

from __future__ import annotations

from collections.abc import Callable

from ..domain.lifecycle import ContractStatus
from ..verification.models import SecurityContract
from ..errors import ErrorCode, JiejianError
from ..storage import ProjectRecord, StorageUnitOfWork


def resolve_execution_contract(
    uow_factory: Callable[..., StorageUnitOfWork],
    record: ProjectRecord,
    fallback: SecurityContract,
) -> SecurityContract:
    """返回精确 ACTIVE 治理快照，绑定失效时不回退 YAML。"""

    if record.governed_contract_id is None:
        return fallback
    with uow_factory() as work:
        current = work.projects.get(record.project_id)
        if current is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
        if (
            current.governed_contract_id != record.governed_contract_id
            or current.governed_contract_version != record.governed_contract_version
        ):
            raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "项目治理绑定在解析期间发生变化")
        governed = work.contract_versions.get(
            record.project_id,
            record.governed_contract_id,
            record.governed_contract_version,
        )
    if governed is None:
        raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "项目治理契约版本不存在")
    if (
        governed.project_id != record.project_id
        or governed.contract_id != record.governed_contract_id
        or governed.version != record.governed_contract_version
    ):
        raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "项目治理契约绑定不一致")
    if governed.status is not ContractStatus.ACTIVE or governed.snapshot.status is not ContractStatus.ACTIVE:
        raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "项目治理契约不是 ACTIVE")
    return governed.snapshot
