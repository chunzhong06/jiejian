# MCP 登记回执只表达已记录事实，不泄漏源码身份，也不把回执提升为修复结论。
from types import SimpleNamespace
from product.backend.api.mcp import _current_change_view


def test_receipt_preserves_reference_without_source_hashes_or_verdict():
    from product.backend.core.check_repair import CurrentRepairReference
    from product.backend.workflows.changes.service import SourceRevalidationInspection
    reference = CurrentRepairReference(source_run_id="run", source_case_id="case", repair_fingerprint="f" * 64)
    manifest = SimpleNamespace(project_id="p1", change_id="chg", reason="更新业务判断", submitted_by="MCP Agent",
        claimed_paths=("hint.py",), repair_reference=reference)
    value = SimpleNamespace(manifest=manifest,
        change_set=SimpleNamespace(status="NO_BASELINE", added_paths=(), modified_paths=(), removed_paths=(), source_fingerprint="a" * 64),
        revalidation=SourceRevalidationInspection(project_id="p1", change_id="chg", status="NO_BASELINE"),
        assessment=SimpleNamespace(payload=SimpleNamespace(action_impacts=())))
    result = _current_change_view(value)
    assert result["registration_status"] == "RECORDED"
    assert result["repair_reference"] == reference.model_dump(mode="json")
    assert result["comparison_status"] == "NO_BASELINE"
    assert "不确认修复成功" in result["receipt_boundary"]
    assert "verdict" not in result and "source_fingerprint" not in result and "snapshot_id" not in result


def test_repair_requirements_keep_selected_control_and_every_regression():
    from product.backend.api.mcp import _current_repair_view
    from product.backend.core.check_repair import CurrentRepairReference
    reference = CurrentRepairReference(source_run_id="run", source_case_id="deny", repair_fingerprint="f" * 64)
    def requirement(case):
        return SimpleNamespace(source_case_id=case, evidence_refs=("evidence",), identity=SimpleNamespace(
            action_id="action", protected_effect_ids=("effect",), permission={"expectation": "ALLOW"},
            resource_id="resource", resource_owner_test_identity_id="owner"))
    contract = SimpleNamespace(reference=lambda:reference, deny=requirement("deny"),
        selected_control=requirement("control"), regressions=(requirement("one"), requirement("two")))
    result = _current_repair_view(contract)
    assert [(item["role"],item["source_case_id"]) for item in result["must_preserve"]] == [
        ("SELECTED_ALLOW","control"),("REGRESSION","one"),("REGRESSION","two")]
    assert result["regression_count"] == 2
    assert "evidence_standard_fingerprints" not in str(result)
