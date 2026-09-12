# 当前项目修复状态只读聚合：消费已发布 Run/Case 与精确关联变化，不保留旧准备链依赖。
from __future__ import annotations

from typing import Literal
from pydantic import Field
from product.backend.core.lifecycle import RunVerdict

from product.backend.core.check_repair import CurrentRepairContract, CurrentRepairVerification
from product.backend.workflows.checks.repair_presentation import RepairComparisonRow, build_repair_comparison
from product.protocols.execution_v3 import Hash, LogicalId, WireModel

CurrentRepairStatus = Literal["REPAIR_REQUIRED","CHANGE_SUBMITTED","READY_TO_VERIFY","VERIFIED","NOT_VERIFIED","INCONCLUSIVE","STALE"]


class CurrentRepairTask(WireModel):
    task_reference: Hash
    contract: CurrentRepairContract
    status: CurrentRepairStatus
    change_id: LogicalId | None = None
    run_id: LogicalId | None = None
    verification: CurrentRepairVerification | None = None
    comparison: tuple[RepairComparisonRow, ...] = ()


class ProjectRepair(WireModel):
    project_id: LogicalId
    status: CurrentRepairStatus | None
    tasks: tuple[CurrentRepairTask,...] = Field(max_length=4096)
    primary_task_reference: Hash | None


class CurrentProjectRepairService:
    """按最早已发布问题建立原题族；关联的新检查更新投影，旧发布事实永不覆盖。"""
    def __init__(self, *, reader, repairs, changes, boundaries, pending_request_reader):
        self._reader,self._repairs,self._changes,self._boundaries = reader,repairs,changes,boundaries
        self._pending_request_reader = pending_request_reader

    def evaluate(self, project_id):
        from product.backend.workflows.changes.service import permission_refs
        boundary = self._boundaries.view(project_id)
        refs = permission_refs(boundary)
        history = sorted(self._reader.list_for_project(project_id),key=lambda item:(item.run.created_at_us,item.run.run_id))
        families,packages = {},{}
        for status in history:
            if status.result_integrity not in {"VALID", "INVALID"}:
                continue
            # 损坏的已发布包必须交由 Reader 拒绝，不能忽略后把既有问题投影为无任务。
            package = self._reader.package(status.run.run_id,project_id=project_id)
            packages[status.run.run_id] = package
            if package.result.verdict is RunVerdict.BLOCK:
                for contract in self._repairs.contracts(status.run.run_id):
                    families.setdefault(contract.deny.identity.fingerprint(),contract)
        tasks = []
        for family,contract in families.items():
            status,verification,run_id = "REPAIR_REQUIRED",None,None
            change = self._changes.latest_for_repair(project_id,contract.reference())
            change_id = None if change is None else change.manifest.change_id
            if boundary.policy_epoch != contract.original_policy_epoch or refs != contract.original_intents:
                status = "STALE"
            else:
                linked = []
                for entry in history:
                    if entry.run.run_id == contract.source_run_id:
                        continue
                    package = packages.get(entry.run.run_id)
                    request = package.request if package is not None else self._pending_request_reader(entry.run.run_id)
                    context = None if request is None else request.repair_context
                    if (context is not None and context.repair_reference==contract.repair_fingerprint
                        and context.source_run_id==contract.source_run_id and request.change_context is not None
                        and request.change_context.change_id==change_id):
                        linked.append((entry,package))
                if linked:
                    entry,package = linked[-1]
                    run_id = entry.run.run_id
                    verification = None if package is None else self._repairs.verification(run_id)
                    status = "INCONCLUSIVE" if verification is None else verification.status
                elif change is not None:
                    status = "READY_TO_VERIFY" if change.revalidation.status=="READY" and change.revalidation.can_execute else "CHANGE_SUBMITTED"
            tasks.append(CurrentRepairTask(task_reference=family,contract=contract,status=status,
                change_id=change_id,run_id=run_id,verification=verification))
        ranking = {name:index for index,name in enumerate(("STALE","NOT_VERIFIED","INCONCLUSIVE","REPAIR_REQUIRED","CHANGE_SUBMITTED","READY_TO_VERIFY","VERIFIED"))}
        tasks.sort(key=lambda item:(ranking[item.status],item.task_reference))
        # 七态与优先级已经确定；只向精确关联且已发布的新 Run 附加展示行。
        tasks = [item.model_copy(update={"comparison": build_repair_comparison(item.contract,
            packages[item.contract.source_run_id], packages.get(item.run_id))}) for item in tasks]
        return ProjectRepair(project_id=project_id,status=None if not tasks else tasks[0].status,
            tasks=tuple(tasks),primary_task_reference=None if not tasks else tasks[0].task_reference)
