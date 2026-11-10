# 从发布事实与交付关联重建问题历史；已验证后再次违规时保留历史并建立下一轮原题。
from __future__ import annotations

from typing import Literal
from pydantic import Field
from product.backend.domain.lifecycle import RunVerdict
from product.backend.domain.errors import ErrorCode,JiejianError

from product.backend.domain.checks.repair import CurrentRepairContract, CurrentRepairVerification, CurrentRepairReference, repair_context, repair_policy_matches
from product.backend.application.checks.repairs.repair_presentation import RepairComparisonRow, build_repair_comparison
from product.protocols.checks.execution_request import Hash, LogicalId, WireModel
from product.backend.application.reading import projection_read

CurrentRepairStatus = Literal["REPAIR_REQUIRED","CHANGE_SUBMITTED","READY_TO_VERIFY","VERIFIED","NOT_VERIFIED","INCONCLUSIVE","STALE"]


class RepairHistoryEvent(WireModel):
    kind: Literal["FOUND", "CHECKED", "VERIFIED", "RECURRED", "CONDITIONS_CHANGED", "CHECK_PENDING", "CHECK_INTERRUPTED"]
    run_id: LogicalId
    source_run_id: LogicalId
    created_at_us: int
    status: CurrentRepairStatus | None = None
    change_id: LogicalId | None = None
    reason_codes: tuple[str, ...] = ()


class CurrentRepairTask(WireModel):
    handling: Literal['SOURCE_CHANGE','EXTERNAL_OBSERVATION','UNAVAILABLE'] = 'UNAVAILABLE'
    task_reference: Hash
    contract: CurrentRepairContract
    status: CurrentRepairStatus
    change_id: LogicalId | None = None
    run_id: LogicalId | None = None
    verification: CurrentRepairVerification | None = None
    comparison: tuple[RepairComparisonRow, ...] = ()
    first_source_run_id: LogicalId | None = None
    last_verified_run_id: LogicalId | None = None
    recurrence_count: int = 0
    history: tuple[RepairHistoryEvent, ...] = ()


class ProjectRepair(WireModel):
    project_id: LogicalId
    status: CurrentRepairStatus | None
    tasks: tuple[CurrentRepairTask,...] = Field(max_length=4096)
    primary_task_reference: Hash | None


class ResolvedRepairTask(WireModel):
    project_id: LogicalId
    task: CurrentRepairTask
    historical: bool
    current_reference: CurrentRepairReference | None = None


class CurrentProjectRepairService:
    """从发布事实重建问题的连续历史；再次发生后以新原题开始下一轮修复。"""
    def __init__(self, *, reader, repairs, changes, boundaries, pending_request_reader):
        self._reader,self._repairs,self._changes,self._boundaries = reader,repairs,changes,boundaries
        self._pending_request_reader = pending_request_reader

    @projection_read
    def resolve(self, project_id, fingerprint, *, source_run_id=None, source_case_id=None):
        """历史入口钉住原合同；后续复发只提供显式入口，不替换用户正在阅读的原题。"""
        readings=self._reader.project_readings(project_id)
        view=self.evaluate(project_id,readings=readings)
        packages={status.run.run_id:package for status,package in readings if package is not None}
        def matches(contract):
            return contract.repair_fingerprint==fingerprint and (source_run_id is None or contract.source_run_id==source_run_id) and (source_case_id is None or contract.source_case_id==source_case_id)
        current=next((item for item in view.tasks if matches(item.contract)),None)
        if current is not None:return ResolvedRepairTask(project_id=project_id,task=current,historical=False)
        contracts=[contract for run,package in packages.items() if package.result.verdict is RunVerdict.BLOCK and (source_run_id is None or run==source_run_id)
                   for contract in self._repairs.contracts_from_verified_package(package) if matches(contract)]
        if len(contracts)!=1:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'指定原问题不存在或原始证据已不可读取')
        contract=contracts[0]
        family=next((item for item in view.tasks if item.task_reference==contract.deny.identity.fingerprint()),None)
        if family is None:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'指定原问题没有可核对的连续历史')
        events=[item for item in family.history if item.source_run_id==contract.source_run_id and item.status is not None]
        event=events[-1] if events else None
        checked=None if event is None or event.kind not in {'VERIFIED','CHECKED'} else packages.get(event.run_id)
        verification=None if checked is None or event.status=='REPAIR_REQUIRED' else self._repairs.verification_for_contract(checked,contract)
        task=family.model_copy(update=dict(contract=contract,handling=_handling(packages[contract.source_run_id]),
            status=verification.status if verification is not None else event.status if event is not None else 'REPAIR_REQUIRED',verification=verification,
            run_id=None if checked is None else event.run_id,change_id=None if event is None else event.change_id,
            last_verified_run_id=next((item.run_id for item in reversed(events) if item.kind=='VERIFIED'),None),
            comparison=build_repair_comparison(contract,packages[contract.source_run_id],checked,linked_reference=contract.reference())))
        return ResolvedRepairTask(project_id=project_id,task=task,historical=True,current_reference=family.contract.reference())

    @projection_read
    def evaluate(self, project_id, *, readings=None):
        from product.backend.application.changes.service import permission_refs
        boundary = self._boundaries.view(project_id)
        refs = permission_refs(boundary)
        readings = self._reader.project_readings(project_id) if readings is None else readings
        history = sorted((status for status,_ in readings),key=lambda item:(item.run.created_at_us,item.run.run_id))
        families,packages = {},{status.run.run_id:package for status,package in readings if package is not None}
        discoveries = {}
        for status in history:
            if status.result_integrity not in {"VALID", "INVALID"}:
                continue
            # 损坏的已发布包必须交由 Reader 拒绝，不能忽略后把既有问题投影为无任务。
            package = packages.get(status.run.run_id)
            if package is None:
                package = self._reader.package(status.run.run_id,project_id=project_id)
            packages[status.run.run_id] = package
            if package.result.verdict is RunVerdict.BLOCK:
                for contract in self._repairs.contracts_from_verified_package(package):
                    family = contract.deny.identity.fingerprint()
                    families.setdefault(family, contract)
                    discoveries[(family, status.run.run_id)] = contract
        if not families:
            return ProjectRepair(project_id=project_id, status=None, tasks=(), primary_task_reference=None)
        references_by_change = {}
        def references_for(change_id):
            if change_id not in references_by_change:
                references_by_change[change_id] = (self._changes.repair_references(project_id, change_id),
                    tuple(item.repair for item in self._changes.targets(project_id, change_id) if item.repair is not None))
            return references_by_change[change_id]
        by_reference = {contract.reference().model_dump_json(): family
            for (family, _), contract in discoveries.items()}
        contracts_by_reference = {contract.reference().model_dump_json(): contract
            for contract in discoveries.values()}
        family_history = {family: [] for family in families}
        discovery_runs = {run_id for _, run_id in discoveries}
        case_families = {}
        started = False
        for entry in history:
            package = packages.get(entry.run.run_id)
            if entry.run.run_id in discovery_runs:
                started = True
            if not started:
                continue
            case_families[entry.run.run_id] = set() if package is None else _case_families(package)
            affected = case_families[entry.run.run_id].intersection(families)
            request = package.request if package is not None else self._pending_request_reader(entry.run.run_id)
            change_context = None if request is None else request.change_context
            if change_context is not None:
                references, _ = references_for(change_context.change_id)
                affected.update(by_reference[reference.model_dump_json()] for reference in references
                    if reference.model_dump_json() in by_reference)
            for family in affected:
                family_history[family].append(entry)
        tasks = []
        for family, first in families.items():
            contract = first
            status, verification, run_id, linked_change = "REPAIR_REQUIRED", None, None, None
            events, recurrence_count, last_verified, resolved = [], 0, None, False
            for entry in family_history[family]:
                package = packages.get(entry.run.run_id)
                discovered = discoveries.get((family, entry.run.run_id))
                if discovered is not None:
                    if not events:
                        events.append(RepairHistoryEvent(kind="FOUND", run_id=entry.run.run_id,
                            source_run_id=contract.source_run_id, created_at_us=entry.run.created_at_us,
                            status="REPAIR_REQUIRED"))
                        continue
                    if resolved:
                        comparable = _same_conditions(contract, discovered)
                        recurrence_count += int(comparable)
                        contract = discovered
                        status, verification, run_id, linked_change = "REPAIR_REQUIRED", None, None, None
                        resolved = False
                        events.append(RepairHistoryEvent(kind="RECURRED" if comparable else "CONDITIONS_CHANGED",
                            run_id=entry.run.run_id, source_run_id=contract.source_run_id,
                            created_at_us=entry.run.created_at_us, status=status))
                        continue
                if not events or entry.run.run_id == contract.source_run_id:
                    continue
                request = package.request if package is not None else self._pending_request_reader(entry.run.run_id)
                change_context = None if request is None else request.change_context
                references, targets = ((), ()) if change_context is None else references_for(change_context.change_id)
                if change_context is not None and contract.reference() not in references:
                    # 同一未解决问题可能重复发现；接受明确关联的新原题，保留首次发现，
                    # 且必须证明判断标准与正常对照相同，不能按“最近一次通过”关闭旧问题。
                    for reference in references:
                        candidate = contracts_by_reference.get(reference.model_dump_json())
                        if (candidate is not None and by_reference[reference.model_dump_json()] == family
                            and _same_conditions(contract, candidate)
                            and (request.repair_context == repair_context(candidate) or reference in targets)):
                            contract = candidate
                            break
                linked = (change_context is not None and contract.reference() in references
                    and (request.repair_context == repair_context(contract) or contract.reference() in targets))
                # 外部原题明确关联冻结合同；其行为复验不依赖本地源码变更记录。
                linked = linked or (request is not None and request.external_recheck is not None
                    and request.repair_context == repair_context(contract))
                if linked:
                    if package is None:
                        lifecycle = entry.run.lifecycle
                        active = lifecycle in {"QUEUED", "RUNNING"}
                        events.append(RepairHistoryEvent(kind="CHECK_PENDING" if active else "CHECK_INTERRUPTED",
                            run_id=entry.run.run_id, source_run_id=contract.source_run_id,
                            created_at_us=entry.run.created_at_us, change_id=None if change_context is None else change_context.change_id))
                        continue
                    verification = self._repairs.verification_for_contract(package, contract)
                    status, run_id, linked_change = verification.status, entry.run.run_id, None if change_context is None else change_context.change_id
                    if status == "VERIFIED":
                        last_verified = run_id
                        resolved = True
                    events.append(RepairHistoryEvent(kind="VERIFIED" if status == "VERIFIED" else "CHECKED",
                        run_id=run_id, source_run_id=contract.source_run_id, created_at_us=entry.run.created_at_us,
                        status=status, change_id=linked_change, reason_codes=verification.reason_codes))
                elif discovered is not None:
                    status, verification, run_id, linked_change = "REPAIR_REQUIRED", None, None, None
                    events.append(RepairHistoryEvent(kind="CHECKED", run_id=entry.run.run_id,
                        source_run_id=contract.source_run_id, created_at_us=entry.run.created_at_us,
                        status="REPAIR_REQUIRED"))
                elif package is not None and family in case_families[entry.run.run_id]:
                    events.append(RepairHistoryEvent(kind="CHECKED", run_id=entry.run.run_id,
                        source_run_id=contract.source_run_id, created_at_us=entry.run.created_at_us,
                        reason_codes=("REPAIR_CONTEXT_NOT_LINKED",)))
            change = self._changes.latest_for_repair(project_id, contract.reference())
            change_id = None if change is None else change.manifest.change_id
            if not repair_policy_matches(contract,policy_epoch=boundary.policy_epoch,permissions=refs):
                status = "STALE"
            elif change is not None and change_id != linked_change:
                status = "READY_TO_VERIFY" if change.revalidation.status=="READY" and change.revalidation.can_execute else "CHANGE_SUBMITTED"
                run_id, verification = None, None
            tasks.append(CurrentRepairTask(task_reference=family,contract=contract,status=status,handling=_handling(packages[contract.source_run_id]),
                change_id=change_id,run_id=run_id,verification=verification,
                first_source_run_id=first.source_run_id,last_verified_run_id=last_verified,
                recurrence_count=recurrence_count,history=tuple(events)))
        ranking = {name:index for index,name in enumerate(("STALE","NOT_VERIFIED","INCONCLUSIVE","REPAIR_REQUIRED","CHANGE_SUBMITTED","READY_TO_VERIFY","VERIFIED"))}
        tasks.sort(key=lambda item:(ranking[item.status],item.task_reference))
        tasks = [item.model_copy(update={"comparison": build_repair_comparison(item.contract,
            packages[item.contract.source_run_id], packages.get(item.run_id),
            linked_reference=item.contract.reference() if item.run_id is not None else None)}) for item in tasks]
        return ProjectRepair(project_id=project_id,status=None if not tasks else tasks[0].status,
            tasks=tuple(tasks),primary_task_reference=None if not tasks else tasks[0].task_reference)


def _handling(package):
    if package.request.source_fingerprint is not None:return 'SOURCE_CHANGE'
    return 'EXTERNAL_OBSERVATION' if package.bundle.runtime.kind=='EXTERNAL_WEB' else 'UNAVAILABLE'


def _same_conditions(first, current):
    def normal_requirements(contract):
        return {(item.identity.fingerprint(), item.evidence_standard_fingerprints)
            for item in (contract.selected_control, *contract.regressions)}
    return (first.original_policy_epoch == current.original_policy_epoch
        and first.original_intents == current.original_intents
        and first.deny.evidence_standard_fingerprints == current.deny.evidence_standard_fingerprints
        and normal_requirements(first) == normal_requirements(current))


def _case_families(package):
    from product.backend.domain.checks.repair import repair_case_identity
    return {repair_case_identity(action, case, package.bundle).fingerprint()
        for action in package.request.actions for case in action.cases}
