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
        entries.append(N(run=N(run_id=current.result.run_id, created_at_us=2, lifecycle="RUNNING"), result_integrity="PENDING" if state == "PENDING" else "VALID"))
    change = None if state in {None, "REPAIR_REQUIRED", "STALE"} else N(manifest=N(change_id=change_id), revalidation=N(status="READY" if state == "READY_TO_VERIFY" else "MAPPING_REVIEW_REQUIRED", can_execute=state == "READY_TO_VERIFY"))
    service = CurrentProjectRepairService(reader=N(project_readings=lambda _: tuple((entry, None if entry.result_integrity == "PENDING" else source if entry.run.run_id == source.result.run_id else current) for entry in entries),
        package=lambda run, **kwargs: source if run == source.result.run_id else current),
        repairs=N(contracts_from_verified_package=lambda _: (contract,), verification_for_contract=lambda package, contract: CurrentRepairVerification(
            repair_reference=contract.repair_fingerprint, source_run_id=contract.source_run_id, run_id=current.result.run_id, status=state, reason_codes=())),
        changes=N(repair_references=lambda _, identity: (contract.reference(),) if identity == change_id else (), targets=lambda *_: (),latest_for_repair=lambda *args: change), boundaries=N(view=lambda _: boundary), pending_request_reader=lambda _: current.request)
    actual = service.evaluate(source.request.project_id)
    assert actual.status == ("CHANGE_SUBMITTED" if state == "PENDING" else state)
    assert len(actual.tasks) == (0 if state is None else 1)
    if actual.tasks:
        rows = actual.tasks[0].comparison
        assert [row.role for row in rows] == ["DENY", "SELECTED_ALLOW", "REGRESSION"]
        assert all(row.match_status == ("MATCHED" if linked and state != "PENDING" else "NOT_AVAILABLE") for row in rows)
        assert actual.tasks[0].contract == contract
    if state == "PENDING":
        assert actual.tasks[0].history[-1].kind == "CHECK_PENDING"
    if linked and state != "PENDING":
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
        changes=N(repair_references=lambda _, identity: (contract.reference(),) if identity == change_id else (), targets=lambda *_: (),latest_for_repair=lambda *args:N(manifest=N(change_id=change_id),revalidation=N(status='READY',can_execute=True))),
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


def test_problem_history_keeps_failed_attempt_resolution_and_recurrence():
    from product.backend.domain.checks.repair import verify_current_repair
    from product.protocols.checks.execution_request import ChangeContext
    source, failed, fixed, ordinary, recurring = [package(forbidden=bad, run_id='run_' + str(index) * 32)
        for index, bad in enumerate((True, True, False, False, True), start=1)]
    contract = build_current_repair_contract(source, next(item.case_id for item in source.result.case_results if item.verdict == 'VULNERABLE'))
    refs = {}
    for index, item in enumerate((failed, fixed), start=1):
        change = ChangeContext(change_id='chg_' + str(index) * 32, impact_fingerprint=str(index) * 64,
            required_intent_ids=tuple(sorted(ref.intent_id for ref in contract.original_intents)))
        item.request = item.request.model_copy(update={'repair_context': repair_context(contract), 'change_context': change})
        refs[change.change_id] = (contract.reference(),)
    values = [source, failed, fixed, ordinary, recurring]
    service = CurrentProjectRepairService(reader=N(project_readings=lambda _: tuple(
        (N(run=N(run_id=item.result.run_id, created_at_us=index, lifecycle='COMPLETED'), result_integrity='VALID'), item)
        for index, item in enumerate(values)), package=lambda run, **_: next(item for item in values if item.result.run_id == run)),
        repairs=N(contracts_from_verified_package=lambda item: tuple(build_current_repair_contract(item, case.case_id)
            for case in item.result.case_results if case.verdict == 'VULNERABLE'),
            verification_for_contract=lambda item, original: verify_current_repair(original, request=item.request,
                bundle=item.bundle, result=item.result, evidence=item.evidence, expected_change_context=item.request.change_context)),
        changes=N(repair_references=lambda _, change: refs[change], targets=lambda *_: (), latest_for_repair=lambda *_: None),
        boundaries=N(view=lambda _: N(policy_epoch=1, permission_intents=contract.original_intents)), pending_request_reader=None)
    task = service.evaluate(source.request.project_id).tasks[0]
    assert task.status == 'REPAIR_REQUIRED'
    assert task.contract.source_run_id == recurring.result.run_id
    assert task.first_source_run_id == source.result.run_id
    assert task.last_verified_run_id == fixed.result.run_id and task.recurrence_count == 1
    assert [(item.kind, item.status) for item in task.history] == [
        ('FOUND', 'REPAIR_REQUIRED'), ('CHECKED', 'NOT_VERIFIED'), ('VERIFIED', 'VERIFIED'),
        ('CHECKED', None), ('RECURRED', 'REPAIR_REQUIRED')]
    historical = service.resolve(source.request.project_id, contract.repair_fingerprint,
        source_run_id=contract.source_run_id, source_case_id=contract.source_case_id)
    assert historical.historical and historical.task.contract == contract
    assert historical.task.status == 'VERIFIED' and historical.task.run_id == fixed.result.run_id
    assert historical.current_reference == task.contract.reference()
    # 同一业务问题复发之后，旧链接仍只读旧原题；错误元组不能借用当前题。
    from product.backend.domain.errors import JiejianError
    with pytest.raises(JiejianError):
        service.resolve(source.request.project_id, contract.repair_fingerprint,source_run_id=recurring.result.run_id)
    values.pop()
    task = service.evaluate(source.request.project_id).tasks[0]
    assert task.status == 'VERIFIED' and task.run_id == fixed.result.run_id


def test_explicit_repair_of_repeated_discovery_resolves_same_problem_and_keeps_first_origin():
    from product.backend.domain.checks.repair import verify_current_repair
    from product.protocols.checks.execution_request import ChangeContext
    first, repeated, fixed = [package(forbidden=bad, run_id='run_' + str(index) * 32)
        for index, bad in enumerate((True, True, False), start=1)]
    contracts = {item.result.run_id: build_current_repair_contract(item,
        next(case.case_id for case in item.result.case_results if case.verdict == 'VULNERABLE'))
        for item in (first, repeated)}
    original = contracts[repeated.result.run_id]
    change = ChangeContext(change_id='chg_'+'8'*32, impact_fingerprint='8'*64,
        required_intent_ids=tuple(sorted(item.intent_id for item in original.original_intents)))
    fixed.request = fixed.request.model_copy(update={'repair_context':repair_context(original),'change_context':change})
    values = (first, repeated, fixed)
    service = CurrentProjectRepairService(reader=N(project_readings=lambda _:tuple(
        (N(run=N(run_id=item.result.run_id,created_at_us=index,lifecycle='COMPLETED'),result_integrity='VALID'),item)
        for index,item in enumerate(values)),package=lambda run,**_:next(item for item in values if item.result.run_id==run)),
        repairs=N(contracts_from_verified_package=lambda item:(contracts[item.result.run_id],),
            verification_for_contract=lambda item,contract:verify_current_repair(contract,request=item.request,
                bundle=item.bundle,result=item.result,evidence=item.evidence,expected_change_context=item.request.change_context)),
        changes=N(repair_references=lambda *_:(original.reference(),),targets=lambda *_:(),latest_for_repair=lambda *_:None),
        boundaries=N(view=lambda _:N(policy_epoch=1,permission_intents=original.original_intents)),pending_request_reader=None)
    task=service.evaluate(first.request.project_id).tasks[0]
    assert task.status=='VERIFIED' and task.contract.source_run_id==repeated.result.run_id
    assert task.first_source_run_id==first.result.run_id and task.last_verified_run_id==fixed.result.run_id
    assert task.recurrence_count==0


def test_new_proof_conditions_do_not_claim_recurrence():
    from product.backend.application.projects.repair import _same_conditions
    source = package()
    original = build_current_repair_contract(source, next(item.case_id for item in source.result.case_results if item.verdict == 'VULNERABLE'))
    changed = original.model_copy(update={'deny': original.deny.model_copy(update={'evidence_standard_fingerprints': ('f' * 64,)})})
    assert not _same_conditions(original, changed)
    assert _same_conditions(original, original)

pytestmark = [pytest.mark.level3]


def test_multi_target_review_cannot_accept_one_success_for_the_batch():
    from types import SimpleNamespace as N
    from product.backend.application.checks.repairs.repair import CurrentRepairService
    from tests.support.builders.checks.repair import contract_and_new
    from product.backend.domain.checks.repair import CurrentRepairVerification
    from tests.support.builders.checks.repair import package
    source = package()
    original = build_current_repair_contract(source, next(item.case_id for item in source.result.case_results if item.verdict == 'VULNERABLE'))
    second_source = package(run_id='run_' + '3' * 32)
    second = build_current_repair_contract(second_source, next(item.case_id for item in second_source.result.case_results if item.verdict == 'VULNERABLE'))
    contract, current, context = contract_and_new()
    targets = tuple(N(repair=item.reference()) for item in (original, second))
    service = CurrentRepairService.__new__(CurrentRepairService)
    service._reader = N(package=lambda run, **_: source if run == original.source_run_id else second_source)
    service._rule_targets_reader = lambda *_: targets
    service.contracts_from_verified_package = lambda item: (original,) if item is source else (second,)
    service.verification_for_contract = lambda package, item: CurrentRepairVerification(repair_reference=item.repair_fingerprint,
        source_run_id=item.source_run_id,run_id=current.result.run_id,status='VERIFIED' if item is original else 'INCONCLUSIVE',reason_codes=())
    reviews = service.reviews_from_verified_package(current)
    assert [item.verification.status for item in reviews] == ['VERIFIED', 'INCONCLUSIVE']
    assert {item.reference for item in reviews} == {original.reference(), second.reference()}
    assert all(item.comparison[0].match_status == 'MATCHED' for item in reviews)


def test_original_handling_survives_later_source_association():
    source = package()
    source.request = source.request.model_copy(update={'source_fingerprint':None})
    source.bundle = source.bundle.model_copy(update={'runtime':source.bundle.runtime.model_copy(update={'kind':'EXTERNAL_WEB'})})
    current = package(forbidden=False,run_id='run_'+'2'*32)
    contract = build_current_repair_contract(source,next(item.case_id for item in source.result.case_results if item.verdict=='VULNERABLE'))
    readings=tuple((N(run=N(run_id=item.result.run_id,created_at_us=index),result_integrity='VALID'),item) for index,item in enumerate((source,current)))
    service=CurrentProjectRepairService(reader=N(project_readings=lambda _:readings),
        repairs=N(contracts_from_verified_package=lambda item:(contract,) if item is source else ()),
        changes=N(targets=lambda *_:(),latest_for_repair=lambda *_:None),
        boundaries=N(view=lambda _:N(policy_epoch=1,permission_intents=(*contract.original_intents,contract.original_intents[0].model_copy(update={'intent_id':'pin_'+'f'*32})))),pending_request_reader=None)
    value=service.resolve(source.request.project_id,contract.repair_fingerprint,source_run_id=contract.source_run_id,source_case_id=contract.source_case_id)
    assert not value.historical and value.task.handling=='EXTERNAL_OBSERVATION'
    assert value.task.contract==contract and value.task.verification is None
