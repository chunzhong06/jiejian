# 验证原题族的七态只读聚合，未关联 PASS 不能覆盖原问题，未发布复验不能完成修复。
from types import SimpleNamespace as N
import pytest

from product.backend.domain.checks.repair import repair_context, CurrentRepairVerification
from product.backend.application.checks.repairs.repair import build_current_repair_contract
from product.backend.application.projects.repair import CurrentProjectRepairService
from tests.support.builders.checks.repair import package


@pytest.mark.parametrize("state", [None, "REPAIR_REQUIRED", "CHANGE_SUBMITTED", "READY_TO_VERIFY", "VERIFIED", "NOT_VERIFIED", "INCONCLUSIVE", "STALE", "PENDING"])
def test_project_repair_projects_exact_linked_state(state):
    source = package()
    deny = next(item for item in source.result.case_results if item.verdict == "VULNERABLE")
    contract = build_current_repair_contract(source, deny.case_id)
    boundary = N(policy_epoch=2 if state == "STALE" else 1, permission_intents=contract.original_intents)
    entries = [] if state is None else [N(run=N(run_id=source.result.run_id, created_at_us=1), result_integrity="VALID")]
    current = package(forbidden=False, run_id="run_" + "2" * 32)
    change_id = "chg_" + "3" * 32
    linked = state in {"VERIFIED", "NOT_VERIFIED", "INCONCLUSIVE", "PENDING"}
    if linked:
        current.request = current.request.model_copy(update={"repair_context": repair_context(contract), "change_context": N(change_id=change_id)})
        entries.append(N(run=N(run_id=current.result.run_id, created_at_us=2), result_integrity="PENDING" if state == "PENDING" else "VALID"))
    change = None if state in {None, "REPAIR_REQUIRED", "STALE"} else N(manifest=N(change_id=change_id), revalidation=N(status="READY" if state == "READY_TO_VERIFY" else "MAPPING_REVIEW_REQUIRED", can_execute=state == "READY_TO_VERIFY"))
    service = CurrentProjectRepairService(reader=N(project_readings=lambda _: tuple((entry, None if entry.result_integrity == "PENDING" else source if entry.run.run_id == source.result.run_id else current) for entry in entries),
        package=lambda run, **kwargs: source if run == source.result.run_id else current),
        repairs=N(contracts_from_verified_package=lambda _: (contract,), verification_for_contract=lambda package, contract: CurrentRepairVerification(
            repair_reference=contract.repair_fingerprint, source_run_id=contract.source_run_id, run_id=current.result.run_id, status=state, reason_codes=())),
        changes=N(targets=lambda *_: (),latest_for_repair=lambda *args: change), boundaries=N(view=lambda _: boundary), pending_request_reader=lambda _: current.request)
    actual = service.evaluate(source.request.project_id)
    assert actual.status == ("INCONCLUSIVE" if state == "PENDING" else state)
    assert len(actual.tasks) == (0 if state is None else 1)
    if actual.tasks:
        rows = actual.tasks[0].comparison
        assert [row.role for row in rows] == ["DENY", "SELECTED_ALLOW", "REGRESSION"]
        assert all(row.match_status == ("MATCHED" if linked and state != "PENDING" else "NOT_AVAILABLE") for row in rows)
        assert actual.tasks[0].contract == contract
    if linked:
        assert actual.tasks[0].run_id == current.result.run_id


@pytest.mark.parametrize('mismatch', ['repair_reference', 'source_run_id', 'change_id'])
def test_unrelated_passing_run_cannot_verify_the_original_problem(mismatch):
    # 独立反例替代源码里必须写出某个布尔表达式的断言：错一项关联就不能修复原题。
    source = package()
    contract = build_current_repair_contract(source, next(item.case_id for item in source.result.case_results if item.verdict == 'VULNERABLE'))
    current = package(forbidden=False, run_id='run_'+'2'*32)
    change_id = 'chg_'+'3'*32
    context = repair_context(contract)
    if mismatch in {'repair_reference', 'source_run_id'}:
        context = context.model_copy(update={mismatch: 'f'*64 if mismatch == 'repair_reference' else 'run_'+'f'*32})
    current.request = current.request.model_copy(update={'repair_context':context, 'change_context':N(change_id='chg_'+'f'*32 if mismatch=='change_id' else change_id)})
    entries = [N(run=N(run_id=item.result.run_id,created_at_us=index),result_integrity='VALID') for index,item in enumerate((source,current))]
    service = CurrentProjectRepairService(reader=N(project_readings=lambda _:tuple((entry, source if entry.run.run_id == source.result.run_id else current) for entry in entries),package=lambda run,**kwargs:source if run==source.result.run_id else current),
        repairs=N(contracts_from_verified_package=lambda _:(contract,),verification_for_contract=lambda *_:pytest.fail('不相关检查不能进入原题验证')),
        changes=N(targets=lambda *_: (),latest_for_repair=lambda *args:N(manifest=N(change_id=change_id),revalidation=N(status='READY',can_execute=True))),
        boundaries=N(view=lambda _:N(policy_epoch=1,permission_intents=contract.original_intents)),pending_request_reader=lambda _:None)
    value = service.evaluate(source.request.project_id)
    assert value.status == 'READY_TO_VERIFY'
    assert value.tasks[0].run_id is None and value.tasks[0].verification is None


def test_project_repair_invalid_publication_is_not_silently_no_task():
    from product.backend.domain.errors import ErrorCode, JiejianError
    def unavailable(*args, **kwargs):
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "已发布包损坏")
    entry = N(result_integrity="INVALID", run=N(run_id="run_" + "1" * 32, created_at_us=1))
    service = CurrentProjectRepairService(reader=N(project_readings=lambda _: ((entry, None),), package=unavailable),
        repairs=None, changes=None, boundaries=N(view=lambda _: N(policy_epoch=1, permission_intents=())), pending_request_reader=None)
    with pytest.raises(JiejianError):
        service.evaluate("project")


def test_project_repair_multiple_original_families_preserve_priority():
    from product.protocols.checks.execution_request import content_hash
    source = package()
    deny = next(item for item in source.result.case_results if item.verdict == "VULNERABLE")
    first = build_current_repair_contract(source, deny.case_id)
    changed_identity = first.deny.identity.model_copy(update={"resource_id": "other-resource"})
    values = first.model_dump(mode="json", exclude={"repair_fingerprint"})
    values["deny"] = first.deny.model_copy(update={"identity": changed_identity}).model_dump(mode="json")
    second = type(first).model_validate_json(__import__("json").dumps({**values, "repair_fingerprint": content_hash("CurrentRepairContract", values)}))
    entry = N(result_integrity="VALID", run=N(run_id=source.result.run_id, created_at_us=1))
    ready = N(manifest=N(change_id="chg_" + "8" * 32), revalidation=N(status="READY", can_execute=True))
    service = CurrentProjectRepairService(reader=N(project_readings=lambda _: ((entry, source),), package=lambda *args, **kwargs: source),
        repairs=N(contracts_from_verified_package=lambda _: (first, second)), changes=N(targets=lambda *_: (),latest_for_repair=lambda _, ref: ready if ref.repair_fingerprint == second.repair_fingerprint else None),
        boundaries=N(view=lambda _: N(policy_epoch=1, permission_intents=first.original_intents)), pending_request_reader=None)
    value = service.evaluate(source.request.project_id)
    assert value.status == "REPAIR_REQUIRED" and len(value.tasks) == 2
    assert [item.status for item in value.tasks] == ["REPAIR_REQUIRED", "READY_TO_VERIFY"]
    assert value.primary_task_reference == first.deny.identity.fingerprint()

pytestmark = [pytest.mark.level3]
