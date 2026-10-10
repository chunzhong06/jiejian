# 验证测试系统自身的失败、泄密、范围与证据失效行为。
import json
from pathlib import Path

import pytest

from tests.support.verification.catalog import fingerprint, plan, test_dependencies as dependency_paths
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


def test_unknown_change_expands_but_shared_css_uses_browser_evidence():
    unknown = plan(ROOT, level="L2", areas=[], changed=["unknown-file.py"], l5=[])
    assert unknown["reasons"] and "storage" in unknown["areas"]
    shared = plan(ROOT, level="L2", areas=[], changed=["product/frontend/src/styles.css"], l5=[])
    ids = {t["id"] for t in shared["tasks"]}
    assert ids == {"build", "browser-core", "browser-process", "browser-materials", "browser-references", "browser-history"}


def test_local_ui_plan_does_not_trigger_full_backend_or_sample_test():
    result = plan(ROOT, level="L2", areas=[], changed=["product/frontend/src/features/system/RuntimePage.tsx"], l5=[])
    assert [task["id"] for task in result["tasks"]] == ["frontend"]
    assert all("features/system/" in p for p in result["tasks"][-1]["args"])


def test_proof_layout_plan_only_builds_and_checks_reference_pages():
    # 已有用户反馈明确指向证明页面；不应顺带启动账号、后端或整套组件回归。
    result = plan(ROOT, level="L1", areas=[], changed=["product/frontend/src/shared/styles/proof-details.css"], l5=[])
    assert [(task["command"], task["args"]) for task in result["tasks"]] == [
        ("prepare", []), ("verify", ["browser", "--ui", "references"])]


def test_explicit_ui_scope_and_full_regression_are_not_silently_narrowed():
    result = plan(ROOT, level="L2", areas=[], changed=[], l5=[], ui=["references"])
    assert [task["id"] for task in result["tasks"]] == ["build", "browser-references"]
    full = plan(ROOT, level="L4", areas=[], changed=[], l5=[], ui=["references"])
    assert {"browser-core","browser-history","frontend","contracts"} <= {t["id"] for t in full["tasks"]}
    with pytest.raises(ValueError, match="UNKNOWN_UI_SCOPE"):
        plan(ROOT, level="L2", areas=[], changed=[], l5=[], ui=["typo"])


@pytest.mark.parametrize('level', ['L1','L2'])
def test_named_test_runs_instead_of_only_collecting_or_expanding_every_sibling(level):
    result = plan(ROOT, level=level, areas=[], changed=["tests/scripts/test_portable.py"], l5=[])
    task = next(t for t in result["tasks"] if t["id"] == "backend-tooling")
    assert [p for p in task["args"] if p.endswith(".py")] == ["tests/scripts/test_portable.py"]


def test_ancestor_fixtures_and_their_imports_invalidate_existing_evidence(tmp_path):
    directory=tmp_path/'tests/runtime';directory.mkdir(parents=True)
    (directory/'test_job.py').write_text('def test_job(shared): pass',encoding='utf-8')
    (directory/'conftest.py').write_text('from tests.support import shared',encoding='utf-8')
    (tmp_path/'tests/support.py').write_text('shared = 1',encoding='utf-8')
    paths=dependency_paths(tmp_path, {'tests/runtime/test_job.py'})
    assert {'tests/runtime/conftest.py','tests/support.py'} <= paths
    before=fingerprint(tmp_path,list(paths))
    (directory/'conftest.py').write_text('from tests.support import shared\nshared = 2',encoding='utf-8')
    assert fingerprint(tmp_path,list(dependency_paths(tmp_path,{'tests/runtime/test_job.py'}))) != before


def test_explicit_scope_and_repo_relative_paths_required():
    with pytest.raises(ValueError, match="TEST_SCOPE_REQUIRED"):
        plan(ROOT, level="L2", areas=[], changed=[], l5=[])
    with pytest.raises(ValueError, match="OUTSIDE_REPOSITORY"):
        plan(ROOT, level="L2", areas=[], changed=["../other"], l5=[])


@pytest.mark.parametrize('area,task_id,prefixes', [
    ('frontend','frontend',('product/backend/api/','product/protocols/')),
    ('contracts','backend-contracts',('product/frontend/','tests/validation/')),
])
def test_evidence_includes_cross_boundary_consumers_and_oracles(monkeypatch, area, task_id, prefixes):
    from tests.support.verification import catalog as module
    observed = {}
    def capture(_root, paths):
        key = str(len(observed))
        observed[key] = paths
        return key
    monkeypatch.setattr(module, "fingerprint", capture)
    result = module.plan(ROOT, level="L2", areas=[area], changed=[], l5=[])
    task = next(t for t in result["tasks"] if t["id"] == task_id)
    paths = observed[task["fingerprint"]]
    assert all(any(p.startswith(prefix) for p in paths) for prefix in prefixes)
