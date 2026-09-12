# 验证原题族的七态只读聚合，未关联 PASS 不能覆盖原问题，未发布复验不能完成修复。
from types import SimpleNamespace as N
import pytest

from product.backend.core.check_repair import repair_context, CurrentRepairVerification
from product.backend.workflows.checks.repair import build_current_repair_contract
from product.backend.workflows.projects.repair import CurrentProjectRepairService
from tests.backend.core.test_check_repair import package


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
    service = CurrentProjectRepairService(reader=N(list_for_project=lambda _: entries,
        package=lambda run, **kwargs: source if run == source.result.run_id else current),
        repairs=N(contracts=lambda _: (contract,), verification=lambda run: CurrentRepairVerification(
            repair_reference=contract.repair_fingerprint, source_run_id=contract.source_run_id, run_id=run, status=state, reason_codes=())),
        changes=N(latest_for_repair=lambda *args: change), boundaries=N(view=lambda _: boundary), pending_request_reader=lambda _: current.request)
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


def test_project_repair_invalid_publication_is_not_silently_no_task():
    from product.backend.core.errors import ErrorCode, JiejianError
    def unavailable(*args, **kwargs):
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "已发布包损坏")
    entry = N(result_integrity="INVALID", run=N(run_id="run_" + "1" * 32, created_at_us=1))
    service = CurrentProjectRepairService(reader=N(list_for_project=lambda _: (entry,), package=unavailable),
        repairs=None, changes=None, boundaries=N(view=lambda _: N(policy_epoch=1, permission_intents=())), pending_request_reader=None)
    with pytest.raises(JiejianError):
        service.evaluate("project")


def test_project_repair_multiple_original_families_preserve_priority():
    from product.protocols.execution_v3 import content_hash
    source = package()
    deny = next(item for item in source.result.case_results if item.verdict == "VULNERABLE")
    first = build_current_repair_contract(source, deny.case_id)
    changed_identity = first.deny.identity.model_copy(update={"resource_id": "other-resource"})
    values = first.model_dump(mode="json", exclude={"repair_fingerprint"})
    values["deny"] = first.deny.model_copy(update={"identity": changed_identity}).model_dump(mode="json")
    second = type(first).model_validate_json(__import__("json").dumps({**values, "repair_fingerprint": content_hash("CurrentRepairContract", values)}))
    entry = N(result_integrity="VALID", run=N(run_id=source.result.run_id, created_at_us=1))
    ready = N(manifest=N(change_id="chg_" + "8" * 32), revalidation=N(status="READY", can_execute=True))
    service = CurrentProjectRepairService(reader=N(list_for_project=lambda _: (entry,), package=lambda *args, **kwargs: source),
        repairs=N(contracts=lambda _: (first, second)), changes=N(latest_for_repair=lambda _, ref: ready if ref.repair_fingerprint == second.repair_fingerprint else None),
        boundaries=N(view=lambda _: N(policy_epoch=1, permission_intents=first.original_intents)), pending_request_reader=None)
    value = service.evaluate(source.request.project_id)
    assert value.status == "REPAIR_REQUIRED" and len(value.tasks) == 2
    assert [item.status for item in value.tasks] == ["REPAIR_REQUIRED", "READY_TO_VERIFY"]
    assert value.primary_task_reference == first.deny.identity.fingerprint()
