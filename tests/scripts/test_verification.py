# 验证测试系统自身的失败、泄密、范围与证据失效行为。
import json
from pathlib import Path

import pytest

from tests.support.verification.catalog import fingerprint, plan
from tests.support.verification.reporting import public_node, result_status, write_report
from tests.support.verification.runner import can_reuse

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("exit_code,collected,skipped,failures,expected", [
    (0, 1, 0, 0, "PASSED"), (0, 0, 0, 0, "EMPTY"), (5, 0, 0, 0, "EMPTY"),
    (0, 1, 1, 0, "INCOMPLETE"), (1, 2, 0, 1, "FAILED"), (2, 0, 0, 1, "FAILED"),
])
def test_no_cases_skips_and_collection_errors_are_not_green(exit_code, collected, skipped, failures, expected):
    assert result_status(exit_code=exit_code, collected=collected, skipped=skipped, failures=failures) == expected


def test_report_does_not_publish_parameter_values(tmp_path):
    secret = "not-a-real-token-but-must-stay-private"
    node = public_node(f"tests/example.py::test_boundary[{secret}]")
    write_report(tmp_path / "report.json", {"node": node})
    assert secret not in (tmp_path / "report.json").read_text()
    assert node.startswith("tests/example.py::test_boundary[case-")


def test_fingerprint_detects_dirty_new_and_deleted_inputs(tmp_path):
    path = tmp_path / "source.py"
    path.write_text("old")
    old = fingerprint(tmp_path, ["source.py"])
    path.write_text("new")
    assert fingerprint(tmp_path, ["source.py"]) != old
    path.unlink()
    assert fingerprint(tmp_path, ["source.py"]) != old


def test_reuse_requires_same_task_tree_environment_and_full_pass():
    task = {"id": "backend", "args": ["tests"], "fingerprint": "inputs"}
    current = {"fingerprint": "tree", "environment": {"python": "3.13"}}
    previous = {"plan": current, "steps": [{"task": task, "status": "PASSED"}]}
    assert can_reuse(previous, current, task)
    assert can_reuse(previous, {**current, "fingerprint": "docs-only-change"}, task)
    assert not can_reuse(previous, current, {**task, "fingerprint": "changed-inputs"})
    assert not can_reuse(previous, {**current, "environment": {}}, task)
    previous["steps"][0]["status"] = "INCOMPLETE"
    assert not can_reuse(previous, current, task)


def test_unknown_changed_file_expands_and_shared_styles_cover_all_frontend():
    unknown = plan(ROOT, level="L2", areas=[], changed=["unknown-file.py"], l5=[])
    assert unknown["reasons"] and "storage" in unknown["areas"]
    shared = plan(ROOT, level="L2", areas=[], changed=["product/frontend/src/styles.css"], l5=[])
    task = next(t for t in shared["tasks"] if t["id"] == "frontend")
    assert len(task["args"]) > 30


def test_local_ui_plan_does_not_trigger_full_backend_or_sample_test():
    result = plan(ROOT, level="L2", areas=[], changed=["product/frontend/src/features/system/RuntimePage.tsx"], l5=[])
    assert [task["id"] for task in result["tasks"]] == ["contracts", "frontend"]
    assert all("features/system/" in p for p in result["tasks"][-1]["args"])


def test_explicit_scope_and_repo_relative_paths_required():
    with pytest.raises(ValueError, match="TEST_SCOPE_REQUIRED"):
        plan(ROOT, level="L2", areas=[], changed=[], l5=[])
    with pytest.raises(ValueError, match="OUTSIDE_REPOSITORY"):
        plan(ROOT, level="L2", areas=[], changed=["../other"], l5=[])


def test_frontend_evidence_includes_api_and_protocol_consumers(monkeypatch):
    from tests.support.verification import catalog as module
    observed = {}
    def capture(_root, paths):
        key = str(len(observed))
        observed[key] = paths
        return key
    monkeypatch.setattr(module, "fingerprint", capture)
    result = module.plan(ROOT, level="L2", areas=["frontend"], changed=[], l5=[])
    task = next(t for t in result["tasks"] if t["id"] == "frontend")
    paths = observed[task["fingerprint"]]
    assert any(p.startswith("product/backend/api/") for p in paths)
    assert any(p.startswith("product/protocols/") for p in paths)
