# 验证只读原题对照按冻结义务与身份匹配，不合并角色或创造安全结论。
from types import SimpleNamespace as N

import pytest

from product.backend.core.check_repair import repair_context
from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.backend.workflows.checks.repair import build_current_repair_contract
from product.backend.workflows.checks.repair_presentation import build_repair_comparison
from product.protocols.execution_v3 import ChangeContext
from tests.fixtures.check_execution import execution_pair


def source_package(*, safe=True, extra=0):
    def labels(payload):
        for index, identity in enumerate(payload["identities"]):
            identity["label"] = f"冻结账号 {index}"
        payload["actions"][0]["display_name"] = "读取归属对象"
        payload["actions"][0]["proofs"][0]["business_label"] = "冻结业务结果"
    request, bundle = execution_pair(configure=labels)
    action = request.actions[0]
    allow = next(case for case in action.cases if case.permission.expectation == "ALLOW")
    additional = tuple(allow.model_copy(update={"case_id": "case_" + str(index + 3) * 32,
        "resource_id": f"other-{index}"}) for index in range(extra))
    request = request.model_copy(update={"actions": (action.model_copy(update={"cases": (*action.cases, *additional)}),)})
    results = tuple(N(case_id=case.case_id, verdict=CaseVerdict.VULNERABLE if case.permission.expectation == "DENY"
        else CaseVerdict.SAFE if safe else CaseVerdict.INCONCLUSIVE, evidence_ids=("ev_" + str(index + 1) * 64,))
        for index, case in enumerate(request.actions[0].cases))
    return N(request=request, bundle=bundle, result=N(run_id="run_" + "1" * 32,
        verdict=RunVerdict.BLOCK, case_results=results))


def original_and_current(**kwargs):
    source = source_package(**kwargs)
    deny = next(item for item in source.result.case_results if item.verdict == CaseVerdict.VULNERABLE)
    contract = build_current_repair_contract(source, deny.case_id)
    change = ChangeContext(change_id="chg_" + "3" * 32, impact_fingerprint="4" * 64,
        required_intent_ids=tuple(ref.intent_id for ref in contract.original_intents))
    current = N(request=source.request.model_copy(update={"repair_context": repair_context(contract), "change_context": change}),
        bundle=source.bundle, result=N(run_id="run_" + "2" * 32, case_results=tuple(N(case_id=item.case_id,
            verdict=CaseVerdict.SAFE, evidence_ids=("ev_" + "e" * 64,)) for item in source.result.case_results)))
    return source, contract, current


@pytest.mark.parametrize("safe,extra,count", [(False, 0, 2), (True, 0, 3), (True, 2, 5)])
def test_comparison_preserves_every_role_and_frozen_labels(safe, extra, count):
    source, contract, current = original_and_current(safe=safe, extra=extra)
    before_bytes = contract.model_dump_json()
    rows = build_repair_comparison(contract, source)
    assert len(rows) == count
    assert [row.role for row in rows] == ["DENY", "SELECTED_ALLOW"] + ["REGRESSION"] * (count - 2)
    assert all(row.match_status == "NOT_AVAILABLE" and row.after_verdict is None for row in rows)
    assert rows[0].subject_label != rows[0].resource_owner_label
    assert all(row.action_label == "读取归属对象" and row.effect_labels == ("冻结业务结果",) for row in rows)
    if safe:
        assert rows[1].source_case_id in [row.source_case_id for row in rows[2:]]
    current.bundle = current.bundle.model_copy(update={"identities": tuple(item.model_copy(update={"label": "当前已改名"}) for item in current.bundle.identities)})
    matched = build_repair_comparison(contract, source, current)
    assert all(row.match_status == "MATCHED" and row.after_verdict is CaseVerdict.SAFE for row in matched)
    assert matched[0].subject_label == rows[0].subject_label
    assert matched[0].before_evidence_refs == rows[0].before_evidence_refs
    assert all(row.after_evidence_refs == ("ev_" + "e" * 64,) for row in matched)
    assert contract.model_dump_json() == before_bytes


@pytest.mark.parametrize("fault", ["none", "same_run", "project", "source_run", "fingerprint", "missing_change", "context_owner"])
def test_comparison_rejects_unavailable_or_unrelated_new_run(fault):
    source, contract, current = original_and_current()
    if fault == "none": current = None
    elif fault == "same_run": current.result.run_id = source.result.run_id
    elif fault == "project": current.request = current.request.model_copy(update={"project_id": "other"})
    elif fault == "missing_change": current.request = current.request.model_copy(update={"change_context": None})
    else:
        field, value = {"source_run": ("source_run_id", "run_" + "9" * 32),
            "fingerprint": ("repair_reference", "9" * 64), "context_owner": ("resource_id", "different")}[fault]
        current.request = current.request.model_copy(update={"repair_context": current.request.repair_context.model_copy(update={field: value})})
    rows = build_repair_comparison(contract, source, current)
    assert all(row.match_status == "NOT_AVAILABLE" and row.after_run_id is None and row.after_case_id is None
        and row.after_verdict is None and row.after_evidence_refs == () for row in rows)


@pytest.mark.parametrize("fault,expected", [("missing", "NOT_FOUND"), ("duplicate", "AMBIGUOUS"), ("no_result", "NOT_FOUND")])
def test_comparison_never_fills_safe_without_one_published_case(fault, expected):
    source, contract, current = original_and_current()
    action = current.request.actions[0]
    deny = next(item for item in action.cases if item.case_id == contract.source_case_id)
    if fault == "no_result": current.result.case_results = tuple(item for item in current.result.case_results if item.case_id != deny.case_id)
    else:
        cases = tuple(item for item in action.cases if item != deny) if fault == "missing" else (*action.cases, deny.model_copy(update={"case_id": "case_" + "f" * 32}))
        current.request = current.request.model_copy(update={"actions": (action.model_copy(update={"cases": cases}),)})
    row = build_repair_comparison(contract, source, current)[0]
    assert row.match_status == expected and row.after_run_id == current.result.run_id
    assert row.after_case_id is None and row.after_verdict is None and row.after_evidence_refs == ()


@pytest.mark.parametrize("missing", ["case", "result"])
def test_comparison_missing_source_fails_closed(missing):
    source, contract, _ = original_and_current()
    if missing == "result": source.result.case_results = ()
    else: source.request = source.request.model_copy(update={"actions": ()})
    with pytest.raises(JiejianError, match="STATE_PRECONDITION"):
        build_repair_comparison(contract, source)


def test_comparison_deduplicates_only_same_label_for_each_required_effect():
    source, contract, _ = original_and_current()
    config = source.bundle.actions[0]
    proof = config.proofs[0]
    source.bundle = source.bundle.model_copy(update={"actions": (config.model_copy(update={"proofs":
        (proof, proof, proof.model_copy(update={"business_label": "另一条冻结说明"}))}),)})
    assert build_repair_comparison(contract, source)[0].effect_labels == ("冻结业务结果", "另一条冻结说明")
