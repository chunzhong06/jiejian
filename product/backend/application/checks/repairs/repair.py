# 从严格已发布包重建原题合同并派生 NEW Run 复验；不持久化第二套修复结论。
from __future__ import annotations

from product.backend.domain.checks.repair import CurrentRepairContract, CurrentRepairReference, RepairCaseRequirement, current_request_permissions, repair_case_identity, repair_evidence_standards, verify_current_repair
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.lifecycle import CaseVerdict, RunVerdict
from product.protocols.checks.execution_request import CaseRole, content_hash
from product.backend.application.checks.repairs.repair_presentation import build_repair_comparison


def build_current_repair_contract(package, source_case_id, *, breakpoint=None):
    """源包必须已通过 Reader；只收真实 BLOCK Case 与同题控制，历史 SAFE 回归可以为空。"""
    results = {item.case_id:item for item in package.result.case_results}
    cases = {case.case_id:(action,case) for action in package.request.actions for case in action.cases}
    try:
        action,case = cases[source_case_id]
        if package.result.verdict is not RunVerdict.BLOCK or results[source_case_id].verdict is not CaseVerdict.VULNERABLE:
            raise ValueError("source case is not a confirmed block")
        twin = next(item for item in action.twins if item.deny_case_id == source_case_id)
        def requirement(pair):
            parent,current = pair
            return RepairCaseRequirement(source_case_id=current.case_id,identity=repair_case_identity(parent,current,package.bundle),
                evidence_standard_fingerprints=repair_evidence_standards(parent,current,package.bundle),
                evidence_refs=results[current.case_id].evidence_ids)
        regressions = tuple(sorted((requirement(pair) for pair in cases.values()
            if CaseRole.ALLOW_REGRESSION in pair[1].roles and results[pair[1].case_id].verdict is CaseVerdict.SAFE),
            key=lambda item:item.identity.fingerprint()))
        values = dict(project_id=package.request.project_id,source_run_id=package.result.run_id,
            source_case_id=source_case_id,original_policy_epoch=package.request.policy_epoch,
            original_intents=current_request_permissions(package.request),deny=requirement((action,case)),
            selected_control=requirement(cases[twin.allow_case_id]),regressions=regressions,breakpoint=breakpoint)
        payload = {name: value.model_dump(mode="json") if hasattr(value,"model_dump") else
            [item.model_dump(mode="json") for item in value] if isinstance(value,tuple) else value
            for name,value in values.items()}
        return CurrentRepairContract(**values,repair_fingerprint=content_hash("CurrentRepairContract",payload))
    except (KeyError,ValueError,StopIteration):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,"原题修复要求无法从已发布事实重建") from None


class CurrentRepairService:
    def __init__(self, *, reader, change_context_reader, breakpoint_reader=None, breakpoints_reader=None, rule_targets_reader=None):
        self._reader = reader
        self._change_context_reader = change_context_reader
        self._rule_targets_reader = rule_targets_reader
        self._breakpoint_reader = breakpoint_reader or (lambda _run,_case:None)
        self._breakpoints_reader = breakpoints_reader

    def contracts(self, run_id):
        package = self._reader.package(run_id)
        return self.contracts_from_verified_package(package)

    def contracts_from_verified_package(self, package, *, breakpoints=None):
        """复用本请求严格读取的包；同轮全部原题共享一次断点投影。"""
        if breakpoints is None and self._breakpoints_reader is not None:
            breakpoints = self._breakpoints_reader(package)
        return tuple(build_current_repair_contract(package,item.case_id,
            breakpoint=breakpoints.get(item.case_id) if breakpoints is not None else
                self._breakpoint_reader(package.result.run_id,item.case_id)) for item in package.result.case_results
            if item.verdict is CaseVerdict.VULNERABLE)

    def resolve(self, project_id, reference: CurrentRepairReference):
        package = self._reader.package(reference.source_run_id)
        if package.request.project_id != project_id:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,"修复引用不属于当前项目")
        breakpoints = self._breakpoints_reader(package) if self._breakpoints_reader is not None else None
        contract = build_current_repair_contract(package,reference.source_case_id,
            breakpoint=breakpoints.get(reference.source_case_id) if breakpoints is not None else
                self._breakpoint_reader(reference.source_run_id,reference.source_case_id))
        if contract.repair_fingerprint != reference.repair_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,"原题修复引用已失效")
        return contract

    def verification(self, run_id):
        package = self._reader.package(run_id)
        return self.verification_from_verified_package(package)

    def verification_from_verified_package(self, package):
        """当前包来自严格reader；涉及另一源Run时仍独立核验其发布包。"""
        return self.review_from_verified_package(package)[0]

    def review_from_verified_package(self, package):
        """同一组已核验的原题与复验包同时提供结论和逐项对照，不从当前违规项反推原题。"""
        context = package.request.repair_context
        if context is None:
            return None, ()
        source = self._reader.package(context.source_run_id)
        matches = [item for item in self.contracts_from_verified_package(source) if item.repair_fingerprint == context.repair_reference]
        if len(matches) != 1:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,"原题修复引用无法核对")
        change = package.request.change_context
        expected = None if change is None else self._change_context_reader(package.request.project_id,change.change_id)
        verification = verify_current_repair(matches[0],request=package.request,bundle=package.bundle,
            result=package.result,evidence=package.evidence,expected_change_context=expected)
        return verification, build_repair_comparison(matches[0], source, package)

    def verification_for_contract(self, package, contract):
        change = package.request.change_context
        expected = None if change is None else self._change_context_reader(package.request.project_id, change.change_id)
        targets = () if change is None or self._rule_targets_reader is None else self._rule_targets_reader(
            package.request.project_id, change.change_id)
        # 目标集合进入冻结的 change_context 指纹，历史检查不能事后追加修复目标。
        return verify_current_repair(contract, request=package.request, bundle=package.bundle,
            result=package.result, evidence=package.evidence, expected_change_context=expected,
            linked_repair_references=tuple(item.repair for item in targets if item.repair is not None))
