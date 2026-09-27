# 验证验收脚本的公开请求与业务事实合同。
from __future__ import annotations
import scripts.dev.sample_test.clients.http as sample_clients_http
import scripts.dev.sample_test.harness.lifecycle as sample_harness_lifecycle
import scripts.dev.sample_test.harness.receipt as sample_harness_receipt
import scripts.dev.sample_test.harness.state as sample_harness_state
import os
import sys
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from scripts.dev.sample_test import official
from scripts.dev.sample_test import windows as windows_module
from tests.scripts._support_sample_test import ROOT, _fresh_real_probe_dir

def test_driver_gui_checkpoint_never_claims_api_as_gui():
    from scripts.dev.sample_test.current_gui import CurrentGui
    gui = CurrentGui(None, None, None)
    with pytest.raises(sample_harness_state.SampleTestError, match="GUI_CHECKPOINT_UNKNOWN"):
        gui.checkpoint("start", {})
    assert gui.records == []

def test_start_waits_for_source_prepare_before_control_ready(
    tmp_path: Path,
) -> None:
    driver = official

    class ExitedProcess:
        @staticmethod
        def poll() -> int:
            return 40

    with pytest.raises(sample_harness_state.SampleTestError, match="START_CMD_EXITED_DURING_PREPARE:40"):
        sample_harness_lifecycle._wait_source_prepare(tmp_path / "receipt.json", ExitedProcess(), timeout=1)

    class PreparedProcess:
        @staticmethod
        def poll() -> int:
            return 44

    class Client:
        @staticmethod
        def readiness() -> dict[str, object]:
            return {}

    with pytest.raises(sample_harness_state.SampleTestError, match="START_CMD_EXITED_AFTER_PREPARE:44"):
        sample_harness_lifecycle._wait_product_ready(Client(), PreparedProcess(), timeout=1)

def test_current_driver_read_projection_binds_story_and_evidence():
    from scripts.dev.sample_test.current_api import read_result
    class Client:
        def call(self, method, path):
            assert method == "GET"
            if path.endswith("result-story"):
                return {"actions": [{"evidence_explanations": [{"evidence_refs": ["ev-one"]}]}]}
            if path.endswith("/evidence"):
                return [{"evidence_id": "ev-one"}]
            return {"run_id": "run-one", "evidence_id": "ev-one"}
    result = read_result(Client(), "run-one")
    assert result["evidence"][0]["evidence_id"] == "ev-one"
    assert result["run_id"] == "run-one"

def test_recording_ui_flow_uses_invoke_and_waits_for_revoked_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = windows_module
    events: list[tuple[str, str]] = []
    driver = windows.RecordingWindowDriver(frozenset(), Path(sys.executable))
    driver._window = object()
    monkeypatch.setattr(
        windows,
        "_invoke_button",
        lambda _window, title, **_kwargs: events.append(("invoke", title)),
    )
    monkeypatch.setattr(
        windows,
        "_wait_text",
        lambda _window, title, **_kwargs: events.append(("Text", title)),
    )
    monkeypatch.setattr(
        windows,
        "_wait_control",
        lambda _window, title, control_type, **_kwargs: events.append(
            (control_type, title)
        ),
    )

    driver.run_business_flow()

    assert events == [
        ("invoke", "进入项目"),
        ("invoke", "生成完整交付包"),
        ("Text", "完整项目交付包已生成。"),
        ("invoke", "撤销本次导出"),
        ("invoke", "确认撤销"),
        ("Text", "已撤销"),
        ("Button", "重新生成交付包"),
    ]

def test_recording_view_flow_invokes_project_and_waits_for_materials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = windows_module
    events: list[tuple[str, str]] = []
    driver = windows.RecordingWindowDriver(frozenset(), Path(sys.executable))
    driver._window = object()
    monkeypatch.setattr(
        windows,
        "_invoke_button",
        lambda _window, title, **_kwargs: events.append(("invoke", title)),
    )
    monkeypatch.setattr(
        windows,
        "_wait_text",
        lambda _window, title, **_kwargs: events.append(("Text", title)),
    )

    driver.run_view_flow()

    assert events == [
        ("invoke", "进入项目"),
        ("Text", "项目资料"),
    ]

def test_text_wait_accepts_repeated_state_without_relaxing_buttons() -> None:
    windows = windows_module
    criteria: list[dict[str, object]] = []

    class Control:
        @staticmethod
        def exists(timeout: float) -> bool:
            assert timeout == 0.1
            return True

        @staticmethod
        def wrapper_object() -> object:
            return object()

    class Window:
        @staticmethod
        def child_window(**kwargs):
            criteria.append(kwargs)
            return Control()

    windows._wait_text(Window(), "已撤销", timeout=0.1)
    assert criteria.pop() == {
        "title": "已撤销",
        "control_type": "Text",
        "found_index": 0,
    }

    windows._wait_control(Window(), "确认撤销", "Button", timeout=0.1)
    assert criteria.pop() == {"title": "确认撤销", "control_type": "Button"}

def test_failure_cleanup_uses_public_identity_sample_and_shutdown_endpoints() -> None:
    driver = official
    state = sample_harness_state.HarnessState(stage=4, sample_started=True, product_ready=True)

    class Client:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def call(self, method: str, path: str, body=None, **_kwargs):
            assert method == "POST"
            if path.endswith('/official-sample/stop'):
                from product.backend.api.routers.experience import OfficialSampleStopRequest
                OfficialSampleStopRequest.model_validate(body or {})
            self.actions.append(path)
            return {"status": "NOT_PREPARED"}

    client = Client()
    report = sample_harness_lifecycle._cleanup_after_failure(client, state, {"project_owner": "identity-1"})

    assert client.actions == [
        "/api/test-identities/identity-1/reset",
        "/api/experience/official-sample/stop",
        "/api/system/shutdown",
    ]
    assert report["state_closed"] is True
    assert report["shutdown_requested"] is True

def test_successful_shutdown_matches_stop_request_contract(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from product.backend.api.routers.experience import OfficialSampleStopRequest
    actions = []

    class Client:
        def call(self, method, path, body=None, **kwargs):
            if path.endswith('/official-sample/stop'):
                OfficialSampleStopRequest.model_validate(body or {})
            actions.append(path)
            return {}

    monkeypatch.setattr(sample_harness_lifecycle, 'process_tree_has_exited', lambda process: True)
    monkeypatch.setattr(sample_harness_lifecycle, 'release_process_tree', lambda *args, **kwargs: None)
    monkeypatch.setattr(sample_harness_lifecycle, '_port_open', lambda port: False)
    monkeypatch.setattr(sample_harness_lifecycle, '_runtime_locks_released', lambda path: True)
    state = sample_harness_state.HarnessState(sample_started=True)
    sample_harness_lifecycle._shutdown_owned_runtime(Client(), state, {}, SimpleNamespace(close=lambda: None),
        SimpleNamespace(stop=lambda: None), SimpleNamespace(wait=lambda **kwargs: None, returncode=0), tmp_path, 12345)
    assert actions == ['/api/experience/official-sample/stop', '/api/system/shutdown']
    assert not state.sample_started

@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("JIEJIAN_RUN_WINDOWS_L5") != "1",
    reason="真实源码启动探针只在明确授权的交互用户环境运行",
)
def test_real_start_reaches_workbench_and_shuts_down_safely() -> None:
    """用正式 start.cmd 验证最小产品启动链，不进入 Recording 或完整 L5。"""

    driver = official
    assert not sample_harness_lifecycle._port_open(sample_harness_state.CONTROL_PORT), "默认控制端口已被占用"
    run_dir = _fresh_real_probe_dir()
    process = None
    log = None
    playwright = None
    browser = None
    released = False
    try:
        process, log = sample_harness_lifecycle._start_product(ROOT, run_dir)
        receipt_path = run_dir / "runtime" / "source" / "receipt.json"
        sample_harness_lifecycle._wait_source_prepare(receipt_path, process, timeout=180)
        runtime = sample_harness_receipt._load_source_runtime(receipt_path, ROOT, run_dir)
        client = sample_clients_http.ApiClient(f"http://127.0.0.1:{sample_harness_state.CONTROL_PORT}")
        ready = sample_harness_lifecycle._wait_product_ready(client, process, timeout=90)
        assert ready["status"] == "ready"
        assert ready["worker"] == "running"

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(runtime.playwright_executable),
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(client.origin, wait_until="networkidle")
        assert page.get_by_role("heading", name="开始一次安全检查").is_visible()
        client.bind_page(page)
        client.call(
            "POST",
            "/api/system/shutdown",
            {"schema_version": "1"},
            accepted=(202,),
        )

        browser.close()
        browser = None
        playwright.stop()
        playwright = None
        assert process.wait(timeout=30) == 0
        assert driver.process_tree_has_exited(process)
        driver.release_process_tree(process, timeout=5)
        released = True
        assert not sample_harness_lifecycle._port_open(sample_harness_state.CONTROL_PORT)
        assert sample_harness_lifecycle._runtime_locks_released(run_dir)
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        if process is not None:
            if process.poll() is None:
                driver.terminate_process_tree(process, timeout=10)
            if not released:
                driver.release_process_tree(process, timeout=5)
        if log is not None:
            log.close()

def test_current_driver_rejects_changed_official_recipe_before_approval(tmp_path):
    from scripts.dev.sample_test.current_api import assert_official_proposal
    from tests.backend.workflows.business_boundaries._support_business_boundary_service import _core
    from product.backend.workflows.business_boundaries.official_recipe import official_boundary_recipe
    from product.backend.core.boundaries.entities import boundary_sha256
    core, project = _core(tmp_path)
    try:
        proposal = core.business_boundaries.create_proposal(project, official_boundary_recipe().proposal_command).proposal
        assert assert_official_proposal({"proposal": proposal.model_dump(mode="json")}, project) == proposal
        item = proposal.proposed_actors[0].model_copy(update={"description": "不属于冻结配方的描述"})
        changed = proposal.model_copy(update={"proposed_actors": (item, *proposal.proposed_actors[1:])})
        changed = changed.model_copy(update={"proposal_fingerprint": boundary_sha256(changed.fingerprint_payload())})
        with pytest.raises(sample_harness_state.SampleTestError, match="RECIPE_MISMATCH"):
            assert_official_proposal({"proposal": changed.model_dump(mode="json")}, project)
    finally:
        core.close()

def test_current_driver_rebind_accepts_only_unchanged_formal_permissions(tmp_path):
    from scripts.dev.sample_test.current_api import _assert_rebind
    from tests.backend.workflows.business_boundaries._support_business_boundary_service import _core, _maintenance_command
    from product.backend.workflows.business_boundaries.official_recipe import official_boundary_recipe
    core, project = _core(tmp_path)
    try:
        proposal = core.business_boundaries.create_proposal(project, official_boundary_recipe().proposal_command).proposal
        before = core.business_boundaries.approve(project, proposal.proposal_id, expected_fingerprint=proposal.proposal_fingerprint, reason="确认固定配方")
        draft = core.business_boundaries.maintenance_draft(project)
        rebind = core.business_boundaries.create_maintenance_proposal(project, _maintenance_command(draft)).proposal
        _assert_rebind(rebind, before.model_dump(mode="json"))
        wrong = rebind.proposed_permissions[0].model_copy(update={"write_mode": "APPEND_REVISION"})
        with pytest.raises(sample_harness_state.SampleTestError, match="PERMISSION_CHANGED"):
            _assert_rebind(rebind.model_copy(update={"proposed_permissions": (wrong, *rebind.proposed_permissions[1:])}), before.model_dump(mode="json"))
    finally:
        core.close()

def test_current_driver_sequence_uses_original_block_reference_and_distinct_runs(monkeypatch):
    from scripts.dev.sample_test import current_api as current
    order = []
    first = {"run_id": "run-first", "story": {"verdict": "BLOCK", "actions": [{"case_id": "case-original", "permission": {"expectation": "DENY"}, "breakpoint": {"breakpoint_type": "AUTHORIZATION_LATE"}}]}}
    limited = {"run_id": "run-limited", "story": {"verdict": "INCONCLUSIVE"}}
    fixed = {"run_id": "run-fixed", "story": {"verdict": "PASS", "repair_verification": {"status": "VERIFIED", "source_run_id": "run-first", "repair_reference": "a" * 64}}}
    baseline = {"run_id": "run-baseline", "story": {"verdict": "PASS"}}
    chronological = [baseline, first, limited, fixed]
    runs = [first, limited, baseline, fixed]
    def run(client, project, state, **kwargs):
        order.append((kwargs["name"], kwargs.get("change_id")))
        return chronological[len(order) - 1]
    switches = []
    def switch(client, project, version, **kwargs):
        switches.append((version, kwargs.get("reference")))
        return {"vulnerable_change_id": "chg-limited", "repair_change_id": "chg-fixed"}
    class Client:
        def call(self, method, path):
            if path.endswith("repair-contracts"):
                return [{"source_run_id": "run-first", "source_case_id": "case-original", "repair_fingerprint": "a" * 64}]
            return {"status": "VERIFIED"}
    monkeypatch.setattr(current, "_boundary", lambda *args: {"policy_epoch": 1, "permission_intents": []})
    monkeypatch.setattr(current, "run_current", run)
    monkeypatch.setattr(current, "switch_current", switch)
    monkeypatch.setattr(current, "prepare_current", lambda *args: None)
    monkeypatch.setattr(current, "project_run_ids", lambda *args: [item["run_id"] for item in runs])
    monkeypatch.setattr(current, "read_result", lambda _, run_id: next(item for item in runs if item["run_id"] == run_id))
    assert current.run_sequence(Client(), "project", sample_harness_state.HarnessState(), checkpoint=lambda *args: None) == runs
    assert order == [("baseline", None), ("problem", None), ("limited", "chg-limited"), ("fixed", "chg-fixed")]
    assert switches == [("VULNERABLE", None), ("EVIDENCE_LIMITED", None), ("FIXED", {"source_run_id": "run-first", "source_case_id": "case-original", "repair_fingerprint": "a" * 64})]

def test_current_driver_public_fact_checks_require_zip_role_and_normal_business():
    import copy
    from scripts.dev.sample_test.current_api import assert_current_result
    kinds = ("owner_api", "read_only_sqlite", "structured_audit_log", "async_task_status", "azure_queue_peek", "azure_blob_object")
    levels = ["VERDICT_REQUIRED" if kind == "azure_blob_object" else "DIAGNOSIS_REQUIRED" if kind == "structured_audit_log" else "SUPPORTING" for kind in kinds]
    denial = {"permission": {"expectation": "DENY"}, "evidence_explanations": [{"source_location": "observer/" + kind, "observed_fact": {"level": level}} for kind, level in zip(kinds, levels)]}
    normal = {"permission": {"expectation": "ALLOW"}}
    observation = {"proof_fingerprint": "proof", "phase": "AFTER", "state": "CONFIRMED", "complete": True, "reliable": True, "correlated": True, "authoritative": True}
    normal_document = {"case": {"permission": {"expectation": "ALLOW"}, "protected_effect_ids": ["effect"], "proof_requirements": [{"level": "VERDICT_REQUIRED", "proof_fingerprint": "proof"}]},
        "outcome": {"execution_outcome": "ACCEPTED", "actual_identity_status": "MATCH", "baseline_trusted": True, "recovery_verified": True, "run_correlated": True, "resource_correlated": True}, "observations": [observation]}
    denial_document = {"case": {"permission": {"expectation": "DENY"}, "protected_effect_ids": ["effect"]}, "observations": [{"observer_id": kind, "level": level} for kind, level in zip(kinds, levels)]}
    result = {"run_id": "run", "story": {"verdict": "PASS", "actions": [denial, normal, normal]}, "evidence": [denial_document, normal_document, copy.deepcopy(normal_document)]}
    assert_current_result(result, expected="PASS")
    result["evidence"][1]["outcome"]["execution_outcome"] = "UNKNOWN"
    with pytest.raises(sample_harness_state.SampleTestError, match="NORMAL_BUSINESS_UNTRUSTED"):
        assert_current_result(result, expected="PASS")
    result["evidence"][1]["outcome"]["execution_outcome"] = "ACCEPTED"
    result["story"]["actions"][0]["evidence_explanations"][0]["observed_fact"]["level"] = "VERDICT_REQUIRED"
    with pytest.raises(sample_harness_state.SampleTestError, match="SOURCE_RESPONSIBILITY"):
        assert_current_result(result, expected="PASS")

def test_failure_cleanup_cancels_exact_active_check_before_reset():
    calls = []
    class Client:
        def call(self, method, path, body=None, **kwargs):
            calls.append((method, path))
            return {"job": {"state": "CANCELLED"}}
    state = sample_harness_state.HarnessState(active_run_id="run-owned", active_run_job_id="job-owned", sample_started=True, product_ready=True)
    result = sample_harness_lifecycle._cleanup_after_failure(Client(), state, {"owner": "identity-owned"})
    assert calls == [("POST", "/api/jobs/job-owned/cancel"), ("GET", "/api/runs/run-owned"),
        ("POST", "/api/test-identities/identity-owned/reset"), ("POST", "/api/experience/official-sample/stop"), ("POST", "/api/system/shutdown")]
    assert result["state_closed"] and result["shutdown_requested"]
