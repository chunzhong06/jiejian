# 验证自动 L5 Harness 的真实启动、可信回执、Evidence 层级、UIA 边界与失败清理，不运行完整 sample-test。

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import sync_playwright

from product.backend.infra.runtime.process.identity import python_environment_report
from scripts.dev.sample_test import adapter as adapter_module
from scripts.dev.sample_test import driver as suite_driver
from scripts.dev.sample_test import official
from scripts.dev.sample_test import oracle as oracle_module
from scripts.dev.sample_test import registry as registry_module
from scripts.dev.sample_test import validation as validation_module
from scripts.dev.sample_test import windows as windows_module


ROOT = Path(__file__).resolve().parents[2]
COMMON_IDENTITY_NAMES = {
    "JIEJIAN_PYTHON_EXECUTABLE",
    "JIEJIAN_PYTHON_ENVIRONMENT_PATH",
    "JIEJIAN_PYTHON_ENVIRONMENT_TYPE",
    "JIEJIAN_PROJECT_ROOT",
    "JIEJIAN_RUNTIME_FINGERPRINT",
    "JIEJIAN_RUNTIME_MODE",
    "JIEJIAN_VAR_DIR",
}


def _fresh_real_probe_dir() -> Path:
    """把真实 Windows 探针证据保留在稳定 var 边界，避免 pytest 清理后丢失。"""

    run_dir = ROOT / "var" / "test" / "sample-test" / "probes" / uuid4().hex
    run_dir.mkdir(parents=True)
    print(f"L5 probe artifacts: {run_dir}", flush=True)
    return run_dir


def _write_receipt(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    report = python_environment_report()
    assert report["ok"] is True, report["issues"]
    var_dir = tmp_path / "prepared-var"
    var_dir.mkdir()
    frontend = var_dir / "runtime" / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    browser = tmp_path / "browser.exe"
    browser.write_bytes(b"controlled-browser-placeholder")
    browsers_path = tmp_path / "browsers"
    browsers_path.mkdir()
    receipt = {
        "schema_version": "1",
        "project_root": str(ROOT),
        "var_dir": str(var_dir),
        "runtime_mode": "development",
        "python": {
            "executable": str(Path(sys.executable).resolve()),
            "environment_path": str(Path(sys.prefix).resolve()),
            "environment_type": "conda",
            "runtime_fingerprint": report["runtime_fingerprint"],
        },
        "playwright": {
            "executable": str(browser),
            "browsers_path": str(browsers_path),
        },
        "frontend": {"dist": str(frontend)},
    }
    receipt_path = var_dir / "runtime" / "source" / "receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path, var_dir, frontend, browser


def test_real_start_receipt_builds_complete_runtime_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    receipt_path, var_dir, frontend, browser = _write_receipt(tmp_path)
    for name in COMMON_IDENTITY_NAMES:
        monkeypatch.delenv(name, raising=False)

    runtime = driver._load_source_runtime(receipt_path, ROOT, var_dir)

    assert COMMON_IDENTITY_NAMES.issubset(runtime.environment)
    assert runtime.environment["JIEJIAN_VAR_DIR"] == str(var_dir.resolve())
    assert runtime.playwright_executable == browser.resolve()
    assert runtime.frontend_dir == frontend.resolve()
    assert not any(name.endswith("PASSWORD") for name in runtime.environment)


def test_source_receipt_rejects_a_different_var_directory(tmp_path: Path) -> None:
    driver = official
    receipt_path, _var_dir, _frontend, _browser = _write_receipt(tmp_path)
    different = tmp_path / "different-var"
    different.mkdir()

    with pytest.raises(driver.SampleTestError, match="source receipt 与当前受控运行输入不一致"):
        driver._load_source_runtime(receipt_path, ROOT, different)


def test_start_product_invokes_root_start_cmd_and_owns_its_process_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    captured: dict[str, object] = {}

    class Process:
        pid = 123

    def spawn(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setenv("COMSPEC", sys.executable)
    monkeypatch.setattr(driver, "spawn_managed_process", spawn)
    var_dir = tmp_path / "var"
    var_dir.mkdir()
    process, log = driver._start_product(ROOT, var_dir)
    log.close()

    assert process.pid == 123
    command = captured["command"]
    assert str(ROOT / "start.cmd") in command
    assert command[-4:] == ["-Mode", "Gui", "-VarDir", str(var_dir)]
    assert "product.backend.cli" not in command
    assert str(captured["kwargs"]["tree_name"]).startswith("jiejian-sample-test-")


def test_driver_gui_checkpoint_never_claims_api_as_gui():
    from scripts.dev.sample_test.current_gui import CurrentGui
    gui = CurrentGui(None, None, None)
    with pytest.raises(official.SampleTestError, match="GUI_CHECKPOINT_UNKNOWN"):
        gui.checkpoint("start", {})
    assert gui.records == []


def test_current_driver_submits_frozen_full_plan_and_reuses_unknown_receipt_key(monkeypatch):
    from scripts.dev.sample_test import current_api as current
    calls = []
    responses = 0
    class Client:
        def call(self, method, path, body=None, **kwargs):
            nonlocal responses
            calls.append((method, path, body))
            if "check-preview" in path:
                return {"can_execute": True, "action_count": 2, "case_count": 3, "plan_fingerprint": "a" * 64}
            if method == "GET":
                return []
            responses += 1
            if responses == 1:
                raise official.SampleTestError("POST runs 无法访问: TimeoutError")
            return {"run": {"run_id": "run-current"}, "job": {"job_id": "job-current"}}
    monkeypatch.setattr(current, "wait_published", lambda *args: None)
    monkeypatch.setattr(current, "assert_current_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(current, "read_result", lambda *args: {"story": {"verdict": "PASS", "actions": [
        {"permission": {"expectation": "ALLOW"}} for _ in range(3)]}, "evidence": [
        {"case": {"protected_effect_ids": ["effect"], "permission": {"expectation": "ALLOW"}}} for _ in range(3)]})
    current.run_current(Client(), "project", official.HarnessState(), name="fixed", expected="PASS", change_id="chg_exact")
    writes = [body for method, _, body in calls if method == "POST"]
    assert len(writes) == 2 and writes[0] == writes[1]
    assert writes[0]["schema_version"] == "2" and writes[0]["expected_plan_fingerprint"] == "a" * 64
    assert writes[0]["change_id"] == "chg_exact"
    assert calls[0][1].endswith("?change_id=chg_exact")
    assert calls[2][:2] == ("GET", "/api/projects/project/runs")


def test_sample_test_suite_keeps_no_argument_semantics_on_official(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        suite_driver.official,
        "run",
        lambda root, var_dir: calls.append((root, var_dir)),
    )

    suite_driver.run_suite(ROOT, tmp_path, "official")

    assert calls == [(ROOT, tmp_path)]


def test_sample_test_argument_parser_accepts_the_single_public_suite_form(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []
    monkeypatch.setattr(
        suite_driver,
        "run_suite",
        lambda _root, _var_dir, suite: observed.append(suite),
    )
    for arguments, expected in (
        ((), "official"),
        (("--suite", "official"), "official"),
        (("--suite", "validation"), "validation"),
        (("--suite", "competition"), "competition"),
        (("--suite", "all"), "all"),
    ):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                str(Path(suite_driver.__file__)),
                "--root",
                str(ROOT),
                "--var-dir",
                str(tmp_path),
                *arguments,
            ],
        )
        assert suite_driver.main() == 0
    assert observed == [
        "official",
        "official",
        "validation",
        "competition",
        "all",
    ]


def test_validation_registry_has_stable_public_cases_and_allow_controls() -> None:
    registry = registry_module
    cases = registry.load_public_registry(ROOT)
    payload = registry.public_registry_payload(ROOT, cases)
    encoded = json.dumps(payload, ensure_ascii=False)

    assert len(cases) == 30
    assert len({item.case_id for item in cases}) == 30
    assert {item.application_id for item in cases} == {
        "collaboration-space",
        "tenant-records",
    }
    assert all(item.allow_control_identity for item in cases)
    assert all(item.protected_effects for item in cases)
    assert all(item.state_selector for item in cases)
    assert {
        (
            item.application_id,
            item.mode,
            str(item.state_selector["implementation"]),
            str(item.state_selector["observation"]),
        )
        for item in cases
    } == {
        (application, mode, implementation, observation)
        for application in ("collaboration-space", "tenant-records")
        for mode in (
            "object_tenant_check_missing",
            "new_entry_inheritance",
            "feature_authorization_bypass",
            "delegation_authority_expansion",
            "deny_async_consequence",
        )
        for implementation, observation in (
            ("MODE_FAULT_PRESENT", "AVAILABLE"),
            ("MODE_GUARD_ACTIVE", "AVAILABLE"),
            ("MODE_GUARD_ACTIVE", "UNAVAILABLE"),
        )
    }
    for forbidden in (
        "expected_verdict",
        "breakpoint_type",
        "maximum_precision",
        "golden_answer",
    ):
        assert forbidden not in encoded


def test_private_oracle_is_outside_every_authorized_source_root_and_product_input() -> None:
    registry = registry_module
    cases = registry.load_public_registry(ROOT)
    evaluator_module = oracle_module
    evaluator = evaluator_module.PrivateOracleEvaluator(ROOT, cases)
    public_payload = registry.public_registry_payload(ROOT, cases)

    for case in cases:
        with pytest.raises(ValueError):
            evaluator.path.resolve().relative_to(case.source_root.resolve())
        assert evaluator.path.name not in {
            path.name for path in case.source_root.rglob("*") if path.is_file()
        }
    product_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (ROOT / "product").rglob("*")
        if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".json"}
    )
    assert "private_oracle" not in product_text
    assert "expected_verdict" not in json.dumps(public_payload, ensure_ascii=False)


def test_validation_adapter_only_translates_public_trace_structure() -> None:
    registry = registry_module
    adapter = adapter_module
    case = registry.load_public_registry(ROOT)[0]
    identity_event = "validation-identity"
    delegation_event = "validation-delegation"
    trace = adapter._trace(
        case,
        records=(
            {
                "event_id": identity_event,
                "semantic_key": "server_identity_resolved",
                "sequence": 1,
                "kind": "IDENTITY",
                "subject_id": case.identity,
                "actor_id": "target-server",
            },
            {
                "event_id": delegation_event,
                "parent_event_id": identity_event,
                "semantic_key": "background_job_started",
                "sequence": 2,
                "kind": "DELEGATION",
                "subject_id": case.identity,
                "actor_id": "validation-worker",
            },
            {
                "event_id": "validation-effect",
                "parent_event_id": delegation_event,
                "delegated_from_event_id": delegation_event,
                "semantic_key": case.observation_config["trace_effect_key"],
                "sequence": 3,
                "kind": "FINAL_EFFECT",
                "subject_id": case.identity,
                "actor_id": "validation-worker",
            },
        ),
        case_id="case-validation-adapter",
        planned_subject_id=case.identity,
        role="deny",
        complete=True,
        evidence_ref="validation-adapter-evidence",
    )

    assert trace.events[0].actor_id == case.identity
    assert trace.events[1].actor_id == "validation-worker"
    assert trace.events[2].actor_id == "validation-worker"
    assert trace.events[2].effect_id == case.protected_effects[0]
    source = Path(adapter.__file__).read_text(encoding="utf-8")
    assert "core.verification.continuity" not in source
    assert "core.verification.breakpoints" not in source


def test_validation_representatives_run_both_real_apps_without_public_oracle_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validation = validation_module
    continuity_calls = 0
    breakpoint_calls = 0
    real_assess = validation.assess_authorization_continuity
    real_locator = validation.BreakpointLocator

    def tracked_assess(*args, **kwargs):
        nonlocal continuity_calls
        continuity_calls += 1
        return real_assess(*args, **kwargs)

    class TrackedBreakpointLocator:
        def locate(self, *args, **kwargs):
            nonlocal breakpoint_calls
            breakpoint_calls += 1
            return real_locator().locate(*args, **kwargs)

    monkeypatch.setattr(validation, "assess_authorization_continuity", tracked_assess)
    monkeypatch.setattr(validation, "BreakpointLocator", TrackedBreakpointLocator)
    summary = validation.run_validation_suite(
        ROOT,
        tmp_path,
        repetitions=1,
        representative_only=True,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "accepted"
    assert summary["case_count"] == 6
    assert continuity_calls == 6
    assert breakpoint_calls == 6
    assert summary["full_method_sources"] == {
        "case_verdict": (
            "product.backend.core.verification.permissions.evaluation."
            "evaluate_permission_case"
        ),
        "authorization_continuity": (
            "product.backend.core.verification.continuity."
            "assess_authorization_continuity"
        ),
        "breakpoint": (
            "product.backend.core.verification.breakpoints."
            "BreakpointLocator.locate"
        ),
    }
    assert summary["applications"] == ["collaboration-space", "tenant-records"]
    results = summary["results"]
    assert len(results) == 6
    assert {item["verdict"] for item in results} == {
        "BLOCK",
        "PASS",
        "INCONCLUSIVE",
    }
    assert all("expected" not in key and "golden" not in key for key in summary)
    assert "expected_verdict" not in encoded
    assert "golden_answer" not in encoded
    assert all(item["allow_control_valid"] for item in results if item["verdict"] != "INCONCLUSIVE")
    assert summary["method_metrics"]["full"]["wrong_pass_vulnerable"] == 0
    assert summary["method_metrics"]["full"]["wrong_pass_evidence_gap"] == 0
    assert summary["method_metrics"]["full"]["exact_match_count"] == 6
    assert summary["method_metrics"]["full"]["effect_decision_correct_count"] == 6
    assert (
        summary["method_metrics"]["full"]["continuity_or_orphan_correct_count"]
        == 6
    )
    assert summary["method_metrics"]["full"]["actual_identity_attributed_count"] == 6
    assert summary["method_metrics"]["full"]["allow_control_valid_count"] == 6
    assert summary["method_metrics"]["full"]["recovery_success_count"] == 6
    assert (
        summary["method_metrics"]["full"]["repair_verification_applicable_count"]
        == 2
    )
    assert (
        summary["method_metrics"]["full"]["repair_verification_success_count"]
        == 2
    )
    assert summary["method_metrics"]["http_only"]["exact_match_count"] == 4
    assert summary["method_metrics"]["http_only"]["wrong_pass_evidence_gap"] == 2
    assert summary["method_metrics"]["single_state"]["exact_match_count"] == 6
    assert (
        summary["method_metrics"]["authorization_regression"][
            "wrong_pass_evidence_gap"
        ]
        == 2
    )
    assert summary["repeat_consistency"]["inconsistent_case_count"] == 0
    assert (tmp_path / "runtime" / "validation").is_dir()

    presentation = validation.build_presentation_summary(summary)
    assert presentation["case_count"] == 6
    assert presentation["application_count"] == 2
    assert presentation["mode_count"] == 1
    assert presentation["state_count"] == 3
    assert presentation["full_exact_match_count"] == 6
    assert presentation["http_wrong_pass_per_matrix"] == 2
    assert "results" not in presentation
    assert "method_metrics" not in presentation
    published_path = tmp_path / "published" / "latest-validation-summary.json"
    suite_driver._publish_summary(published_path, summary)
    assert json.loads(published_path.read_text(encoding="utf-8")) == presentation


def test_start_waits_for_source_prepare_before_control_ready(
    tmp_path: Path,
) -> None:
    driver = official

    class ExitedProcess:
        @staticmethod
        def poll() -> int:
            return 40

    with pytest.raises(driver.SampleTestError, match="START_CMD_EXITED_DURING_PREPARE:40"):
        driver._wait_source_prepare(tmp_path / "receipt.json", ExitedProcess(), timeout=1)

    class PreparedProcess:
        @staticmethod
        def poll() -> int:
            return 44

    class Client:
        @staticmethod
        def readiness() -> dict[str, object]:
            return {}

    with pytest.raises(driver.SampleTestError, match="START_CMD_EXITED_AFTER_PREPARE:44"):
        driver._wait_product_ready(Client(), PreparedProcess(), timeout=1)


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

def test_recording_window_requires_a_unique_new_controlled_chromium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = windows_module
    chromium = Path(sys.executable).resolve()
    fact = windows.WindowFact(22, 100, "协作空间 · 校园数字展馆", chromium)

    class Control:
        def exists(self, timeout: float) -> bool:
            return True

    class Window:
        def child_window(self, **_kwargs):
            return Control()

    class Desktop:
        def window(self, *, handle: int):
            assert handle == 22
            return Window()

    monkeypatch.setattr(windows, "visible_top_level_windows", lambda: (fact,))
    monkeypatch.setattr(windows, "Desktop", lambda backend: Desktop())
    driver = windows.RecordingWindowDriver(frozenset({11}), chromium)
    driver.wait_until_ready(timeout=0.1)

    monkeypatch.setattr(
        windows,
        "visible_top_level_windows",
        lambda: (fact, windows.WindowFact(23, 101, fact.title, chromium)),
    )
    with pytest.raises(windows.WindowsL5Error, match="RECORDING_WINDOW_AMBIGUOUS"):
        windows.RecordingWindowDriver(frozenset({11}), chromium).wait_until_ready(timeout=0.1)


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
    state = driver.HarnessState(stage=4, sample_started=True, product_ready=True)

    class Client:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def call(self, method: str, path: str, body=None, **_kwargs):
            assert method == "POST"
            self.actions.append(path)
            return {"status": "NOT_PREPARED"}

    client = Client()
    report = driver._cleanup_after_failure(client, state, {"project_owner": "identity-1"})

    assert client.actions == [
        "/api/test-identities/identity-1/reset",
        "/api/experience/official-sample/stop",
        "/api/system/shutdown",
    ]
    assert report["state_closed"] is True
    assert report["shutdown_requested"] is True



def test_occupied_default_port_writes_failure_without_touching_the_existing_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    run_dir = tmp_path / "occupied-port"
    run_dir.mkdir()
    monkeypatch.setattr(driver, "_port_open", lambda _port: True)
    monkeypatch.setattr(
        driver,
        "_cleanup_after_failure",
        lambda *_args, **_kwargs: pytest.fail("端口预占用不得调用产品清理 API"),
    )

    with pytest.raises(driver.SampleTestError, match="L5_CONTROL_PORT_OCCUPIED"):
        driver.run(ROOT, run_dir)

    failure = json.loads((run_dir / "audit" / "sample-test" / "failure.json").read_text(encoding="utf-8"))
    assert failure["failure_code"] == "L5_CONTROL_PORT_OCCUPIED"
    assert failure["cleanup"]["actions"] == []
    assert failure["resources"]["control_port_closed"] is False


def test_runtime_lock_receipts_do_not_count_as_active_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    runtime = tmp_path / "runtime"
    serve_lock = runtime / "locks" / "serve.lock"
    worker_lock = runtime / "workers" / "job_recording.lock"
    serve_lock.parent.mkdir(parents=True)
    worker_lock.parent.mkdir(parents=True)
    serve_lock.write_text("serve receipt", encoding="utf-8")
    worker_lock.write_text("worker receipt", encoding="utf-8")
    observed: list[Path] = []

    monkeypatch.setattr(
        driver,
        "lock_is_available",
        lambda path: observed.append(path) or True,
    )

    assert driver._runtime_locks_released(tmp_path) is True
    assert observed == [serve_lock, worker_lock]


def test_failure_artifact_separates_primary_error_and_cleanup_facts(tmp_path: Path) -> None:
    driver = official
    audit = tmp_path / "audit"
    audit.mkdir()
    driver._write_failure(
        audit,
        driver.SampleTestError("L5_RUN_RESULT_UNAVAILABLE"),
        driver.HarnessState(
            stage=6,
            active_run_id="run-public",
            active_run_job_id="run-job-public",
        ),
        {"actions": ["official-sample.stop", "system.shutdown"], "state_closed": True},
        control_closed=True,
        sample_closed=True,
        process_tree_closed=True,
    )

    failure = json.loads((audit / "failure.json").read_text(encoding="utf-8"))
    assert failure["failure_code"] == "L5_RUN_RESULT_UNAVAILABLE"
    assert failure["primary_failure"] == "L5_RUN_RESULT_UNAVAILABLE"
    assert failure["active_run_id"] == "run-public"
    assert failure["active_run_job_id"] == "run-job-public"
    assert "recording_id" not in failure
    assert failure["cleanup"]["state_closed"] is True
    assert set(failure["resources"].values()) == {True}
    assert "password" not in json.dumps(failure).casefold()


def test_unavailable_run_result_has_stable_failure_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    monkeypatch.setattr(
        driver,
        "_wait_for",
        lambda *_args, **_kwargs: {
            "run": {"lifecycle": "FAILED"},
            "result_integrity": "INVALID",
        },
    )

    with pytest.raises(driver.SampleTestError) as caught:
        driver._wait_for_published_result(object(), "run-public", "run-job-public")

    assert driver._failure_identity(caught.value) == (
        "L5_RUN_RESULT_UNAVAILABLE",
        "L5_RUN_RESULT_UNAVAILABLE: lifecycle=FAILED integrity=INVALID "
        "run_id=run-public run_job_id=run-job-public",
    )


@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("JIEJIAN_RUN_WINDOWS_L5") != "1",
    reason="真实源码准备隔离只在明确授权的交互用户环境运行",
)
def test_real_source_prepare_reuses_shared_tools_across_two_fresh_runtimes() -> None:
    driver = official
    command_shell = os.environ.get("COMSPEC")
    assert command_shell and Path(command_shell).is_file()
    shared = (ROOT / "var" / "development").resolve()

    def prepare(run_dir: Path) -> tuple[dict[str, object], str]:
        log_path = run_dir / "logs" / "source-prepare.log"
        log_path.parent.mkdir(parents=True)
        with log_path.open("wb") as log:
            process = driver.spawn_managed_process(
                [command_shell, "/d", "/s", "/c", "call", str(ROOT / "start.cmd"), "-Mode", "Prepare", "-VarDir", str(run_dir)],
                cwd=ROOT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                tree_name=f"jiejian-source-prepare-probe-{uuid4().hex}",
            )
            try:
                return_code = process.wait(timeout=660)
                tree_closed = driver.process_tree_has_exited(process)
            except subprocess.TimeoutExpired:
                driver.terminate_process_tree(process, timeout=10)
                raise
            finally:
                if not driver.process_tree_has_exited(process):
                    driver.terminate_process_tree(process, timeout=10)
                driver.release_process_tree(process, timeout=5)
        output = log_path.read_text(encoding="utf-8", errors="replace")
        assert return_code == 0, output
        assert tree_closed, "start.cmd -Mode Prepare 返回后仍有本轮受控子进程"
        receipt = json.loads((run_dir / "runtime" / "source" / "receipt.json").read_text(encoding="utf-8"))
        return receipt, output

    run_a = _fresh_real_probe_dir()
    receipt_a, _ = prepare(run_a)
    shared_receipt_a = json.loads((shared / "frontend" / "builds" / json.loads((run_a / "runtime" / "build" / "frontend-receipt.json").read_text(encoding="utf-8"))["build_digest"] / "receipt.json").read_text(encoding="utf-8"))
    shared_files = tuple(
        path
        for path in (
            Path(receipt_a["uv"]["executable"]),
            Path(receipt_a["playwright"]["executable"]),
            Path(receipt_a["node"]["executable"]),
            Path(receipt_a["pnpm"]["executable"]),
            shared / "frontend" / "workspace" / ".jiejian-dependency-digest",
            shared / "frontend" / "builds" / shared_receipt_a["build_digest"] / "receipt.json",
        )
    )
    mtimes = {path: path.stat().st_mtime_ns for path in shared_files}

    run_b = _fresh_real_probe_dir()
    receipt_b, _ = prepare(run_b)
    frontend_a = json.loads((run_a / "runtime" / "build" / "frontend-receipt.json").read_text(encoding="utf-8"))
    frontend_b = json.loads((run_b / "runtime" / "build" / "frontend-receipt.json").read_text(encoding="utf-8"))

    for run_dir, receipt in ((run_a, receipt_a), (run_b, receipt_b)):
        assert Path(receipt["var_dir"]).resolve() == run_dir.resolve()
        assert Path(receipt["uv"]["executable"]).resolve().is_relative_to(shared / "tools" / "uv")
        assert Path(receipt["playwright"]["browsers_path"]).resolve() == shared / "tools" / "playwright"
        assert Path(receipt["playwright"]["executable"]).resolve().is_relative_to(shared / "tools" / "playwright")
        assert Path(receipt["node"]["executable"]).resolve().is_relative_to(shared / "tools" / "node")
        assert Path(receipt["pnpm"]["executable"]).resolve().is_relative_to(shared / "tools" / "pnpm")
        assert Path(receipt["frontend"]["dist"]).resolve() == (run_dir / "runtime" / "frontend").resolve()
        assert (run_dir / "data" / "jiejian.db").is_file()
        assert (run_dir / "runtime" / "frontend" / "index.html").is_file()
    assert frontend_a["dependency_digest"] == frontend_b["dependency_digest"]
    assert frontend_a["build_digest"] == frontend_b["build_digest"]
    assert receipt_b["frontend"]["build_state"] == "reused"
    assert receipt_b["frontend"]["dependencies"] == "共享依赖与 build 摘要命中，运行阶段无需 Node/pnpm"
    assert {path: path.stat().st_mtime_ns for path in shared_files} == mtimes


@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("JIEJIAN_RUN_WINDOWS_L5") != "1",
    reason="真实源码启动探针只在明确授权的交互用户环境运行",
)
def test_real_start_reaches_workbench_and_shuts_down_safely() -> None:
    """用正式 start.cmd 验证最小产品启动链，不进入 Recording 或完整 L5。"""

    driver = official
    assert not driver._port_open(driver.CONTROL_PORT), "默认控制端口已被占用"
    run_dir = _fresh_real_probe_dir()
    process = None
    log = None
    playwright = None
    browser = None
    released = False
    try:
        process, log = driver._start_product(ROOT, run_dir)
        receipt_path = run_dir / "runtime" / "source" / "receipt.json"
        driver._wait_source_prepare(receipt_path, process, timeout=180)
        runtime = driver._load_source_runtime(receipt_path, ROOT, run_dir)
        client = driver.ApiClient(f"http://127.0.0.1:{driver.CONTROL_PORT}")
        ready = driver._wait_product_ready(client, process, timeout=90)
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
        assert not driver._port_open(driver.CONTROL_PORT)
        assert driver._runtime_locks_released(run_dir)
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


@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("JIEJIAN_RUN_WINDOWS_L5") != "1",
    reason="真实 Windows UIA capability 只在明确授权的交互用户环境运行",
)
def test_real_uia_capability_invokes_html_button_and_reads_status(tmp_path: Path) -> None:
    windows = windows_module
    receipt = json.loads((ROOT / "var" / "runtime" / "source" / "receipt.json").read_text(encoding="utf-8"))
    chromium = Path(receipt["playwright"]["executable"]).resolve()
    browser_root = Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]).resolve()
    assert chromium.is_file()
    assert chromium.is_relative_to(browser_root)
    before = windows.window_snapshot()

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(tmp_path / "uia-profile"),
            headless=False,
            executable_path=str(chromium),
        )
        try:
            page = context.pages[0]
            page.set_content(
                """<!doctype html><html><head><title>JIEJIAN UIA Probe</title></head><body>
                <button type="button" onclick="document.getElementById('status').textContent='探针已完成'">执行探针</button>
                <div id="status" role="status" aria-live="polite">等待探针</div>
                </body></html>"""
            )
            deadline = time.monotonic() + 10
            candidates = []
            while time.monotonic() < deadline:
                candidates = [
                    item
                    for item in windows.visible_top_level_windows()
                    if item.handle not in before
                    and "JIEJIAN UIA Probe" in item.title
                    and str(item.image).casefold() == str(chromium).casefold()
                ]
                if len(candidates) == 1:
                    break
                time.sleep(0.2)
            assert len(candidates) == 1
            window = windows.Desktop(backend="uia").window(handle=candidates[0].handle)
            windows._invoke_button(window, "执行探针", timeout=5)
            windows._wait_control(window, "探针已完成", "Text", timeout=5)
            assert page.locator("#status").inner_text() == "探针已完成"
        finally:
            context.close()


@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("JIEJIAN_RUN_WINDOWS_L5") != "1",
    reason="真实官方样例准备只在明确授权的交互用户环境运行",
)
def test_real_official_scenario_setup_closes_before_full_l5() -> None:
    driver = official
    run_dir = _fresh_real_probe_dir()

    driver.run(ROOT, run_dir, stop_after_setup=True, verify_workspace_ui=True)

    summary = json.loads(
        (run_dir / "audit" / "sample-test" / "sample-test-summary.json").read_text(encoding="utf-8")
    )
    assert summary["scenario_setup_probe"] == "passed"
    assert summary["case_count"] == 3
    assert summary["differential_pair_count"] == 1
    assert summary["workspace_ui_probe"] == "passed"
    assert summary["control_port_closed"] is True
    assert summary["sample_port_closed"] is True
    assert summary["owned_process_tree_closed"] is True


def test_current_driver_rejects_changed_official_recipe_before_approval(tmp_path):
    from scripts.dev.sample_test.current_api import assert_official_proposal
    from tests.backend.workflows.business_boundaries.test_business_boundary_service import _core
    from product.backend.workflows.business_boundaries.official_recipe import official_boundary_recipe
    from product.backend.core.business_boundary import boundary_sha256
    core, project = _core(tmp_path)
    try:
        proposal = core.business_boundaries.create_proposal(project, official_boundary_recipe().proposal_command).proposal
        assert assert_official_proposal({"proposal": proposal.model_dump(mode="json")}, project) == proposal
        item = proposal.proposed_actors[0].model_copy(update={"description": "不属于冻结配方的描述"})
        changed = proposal.model_copy(update={"proposed_actors": (item, *proposal.proposed_actors[1:])})
        changed = changed.model_copy(update={"proposal_fingerprint": boundary_sha256(changed.fingerprint_payload())})
        with pytest.raises(official.SampleTestError, match="RECIPE_MISMATCH"):
            assert_official_proposal({"proposal": changed.model_dump(mode="json")}, project)
    finally:
        core.close()


def test_current_driver_rebind_accepts_only_unchanged_formal_permissions(tmp_path):
    from scripts.dev.sample_test.current_api import _assert_rebind
    from tests.backend.workflows.business_boundaries.test_business_boundary_service import _core, _maintenance_command
    from product.backend.workflows.business_boundaries.official_recipe import official_boundary_recipe
    core, project = _core(tmp_path)
    try:
        proposal = core.business_boundaries.create_proposal(project, official_boundary_recipe().proposal_command).proposal
        before = core.business_boundaries.approve(project, proposal.proposal_id, expected_fingerprint=proposal.proposal_fingerprint, reason="确认固定配方")
        draft = core.business_boundaries.maintenance_draft(project)
        rebind = core.business_boundaries.create_maintenance_proposal(project, _maintenance_command(draft)).proposal
        _assert_rebind(rebind, before.model_dump(mode="json"))
        wrong = rebind.proposed_permissions[0].model_copy(update={"write_mode": "APPEND_REVISION"})
        with pytest.raises(official.SampleTestError, match="PERMISSION_CHANGED"):
            _assert_rebind(rebind.model_copy(update={"proposed_permissions": (wrong, *rebind.proposed_permissions[1:])}), before.model_dump(mode="json"))
    finally:
        core.close()


def test_current_driver_sequence_uses_original_block_reference_and_distinct_runs(monkeypatch):
    from scripts.dev.sample_test import current_api as current
    order = []
    first = {"run_id": "run-first", "story": {"verdict": "BLOCK", "actions": [{"case_id": "case-original", "permission": {"expectation": "DENY"}, "breakpoint": {"breakpoint_type": "AUTHORIZATION_LATE"}}]}}
    limited = {"run_id": "run-limited", "story": {"verdict": "INCONCLUSIVE"}}
    fixed = {"run_id": "run-fixed", "story": {"verdict": "PASS", "repair_verification": {"status": "VERIFIED", "source_run_id": "run-first", "repair_reference": "a" * 64}}}
    runs = [first, limited, fixed]
    def run(client, project, state, **kwargs):
        order.append((kwargs["name"], kwargs.get("change_id")))
        return runs[len(order) - 1]
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
    assert current.run_sequence(Client(), "project", official.HarnessState(), checkpoint=lambda *args: None) == runs
    assert order == [("problem", None), ("limited", "chg-limited"), ("fixed", "chg-fixed")]
    assert switches == [("EVIDENCE_LIMITED", None), ("FIXED", {"source_run_id": "run-first", "source_case_id": "case-original", "repair_fingerprint": "a" * 64})]


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
    with pytest.raises(official.SampleTestError, match="NORMAL_BUSINESS_UNTRUSTED"):
        assert_current_result(result, expected="PASS")
    result["evidence"][1]["outcome"]["execution_outcome"] = "ACCEPTED"
    result["story"]["actions"][0]["evidence_explanations"][0]["observed_fact"]["level"] = "VERDICT_REQUIRED"
    with pytest.raises(official.SampleTestError, match="SOURCE_RESPONSIBILITY"):
        assert_current_result(result, expected="PASS")


def test_failure_cleanup_cancels_exact_active_check_before_reset():
    calls = []
    class Client:
        def call(self, method, path, body=None, **kwargs):
            calls.append((method, path))
            return {"job": {"state": "CANCELLED"}}
    state = official.HarnessState(active_run_id="run-owned", active_run_job_id="job-owned", sample_started=True, product_ready=True)
    result = official._cleanup_after_failure(Client(), state, {"owner": "identity-owned"})
    assert calls == [("POST", "/api/jobs/job-owned/cancel"), ("GET", "/api/runs/run-owned"),
        ("POST", "/api/test-identities/identity-owned/reset"), ("POST", "/api/experience/official-sample/stop"), ("POST", "/api/system/shutdown")]
    assert result["state_closed"] and result["shutdown_requested"]
