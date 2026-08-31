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


def test_guided_experience_uses_the_single_official_sample_entry(tmp_path: Path) -> None:
    events: list[tuple[str, str]] = []

    class Control:
        def __init__(self, label: str) -> None:
            self.label = label

        def click(self) -> None:
            events.append(("click", self.label))

        def wait_for(self) -> None:
            events.append(("wait", self.label))

    class Response:
        status = 200
        url = "http://127.0.0.1:8765/api/experience/official-sample/start"

        class Request:
            method = "POST"

        request = Request()

    class Pending:
        value = Response()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    class Page:
        def goto(self, url: str, *, wait_until: str) -> None:
            events.append(("goto", f"{url}:{wait_until}"))

        def get_by_role(self, role: str, *, name: str) -> Control:
            assert role == "button"
            return Control(name)

        def get_by_text(self, text: str) -> Control:
            return Control(text)

        def expect_response(self, predicate, *, timeout: int) -> Pending:
            assert timeout == 30_000
            assert predicate(Response()) is True
            return Pending()

        def wait_for_url(self, url: str, *, timeout: int) -> None:
            assert (url, timeout) == ("**/#/application", 30_000)

        def get_by_label(self, label: str) -> Control:
            return Control(label)

        def screenshot(self, *, path: str, full_page: bool) -> None:
            assert Path(path) == tmp_path / "guided-application.png"
            assert full_page is True

    class Client:
        origin = "http://127.0.0.1:8765"

        @staticmethod
        def call(method: str, path: str):
            assert (method, path) == ("GET", "/api/experience/official-sample")
            return {
                "active": True,
                "experience_mode": "GUIDED",
                "project_id": "project-demo",
                "origin": "http://127.0.0.1:9000",
            }

    state = official.HarnessState(stage=2)
    result = official._start_guided_experience(Page(), Client(), tmp_path, state)

    assert result["project_id"] == "project-demo"
    assert state.sample_started is True
    assert ("click", "启动官方示例") in events
    assert ("click", "同意并启动") in events
    assert ("wait", "启动示例不会开始真实检查，也不会预先生成结论。") in events
    assert ("wait", "官方示例状态") in events


def test_fixed_case_submits_the_repair_change_through_the_formal_check_api() -> None:
    calls: list[tuple[str, str]] = []

    class Client:
        @staticmethod
        def call(method: str, path: str):
            calls.append((method, path))
            return {"repair_change_id": "chg_" + "4" * 32}

    body = official._check_submission_body(
        Client(),
        name="fixed",
        verification_run_id="run_vulnerable",
    )

    assert calls == [("GET", "/api/experience/official-sample")]
    assert body["change_id"] == "chg_" + "4" * 32
    assert str(body["idempotency_key"]).startswith("sample-fixed-")


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


def test_cli_equivalence_uses_result_and_history_while_evidence_stays_api_owned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    run_id = "run_current"
    evidence_index = [
        {"evidence_id": "evidence-a", "artifact_path": "artifacts/evidence/a.json"},
        {"evidence_id": "evidence-b", "artifact_path": "artifacts/evidence/b.json"},
    ]
    evidence_documents = {
        "evidence-a": {"evidence_id": "evidence-a", "requirement_bindings": ["owner"]},
        "evidence-b": {"evidence_id": "evidence-b", "requirement_bindings": ["blob"]},
    }

    class Client:
        calls: list[str] = []

        @classmethod
        def call(cls, method: str, path: str):
            assert method == "GET"
            cls.calls.append(path)
            if path == f"/api/runs/{run_id}/evidence":
                return evidence_index
            evidence_id = path.rsplit("/", 1)[-1]
            return evidence_documents[evidence_id]

    loaded_index, loaded_documents = driver._load_evidence(Client(), run_id)
    assert loaded_index == evidence_index
    assert loaded_documents == list(evidence_documents.values())
    assert loaded_index != loaded_documents
    assert Client.calls == [
        f"/api/runs/{run_id}/evidence",
        f"/api/runs/{run_id}/evidence/evidence-a",
        f"/api/runs/{run_id}/evidence/evidence-b",
    ]

    presentation = {"run_id": run_id, "verdict": "INCONCLUSIVE"}
    history = {"project_id": "project-current", "comparisons": []}
    def run_cli(_root, _var_dir, _environment, *arguments: str) -> str:
        if arguments[:2] == ("result", "show"):
            return "检查结果"
        if arguments[0] == "history":
            return "历史变化"
        if arguments[1:3] == ("result", "show"):
            return json.dumps({"data": presentation})
        return json.dumps({"data": history})

    monkeypatch.setattr(driver, "_run_cli", run_cli)
    run = {
        "run_id": run_id,
        "presentation": presentation,
        "evidence_index": loaded_index,
        "evidence": loaded_documents,
    }
    driver._assert_cli_equivalence(
        ROOT,
        tmp_path,
        "project-current",
        run,
        history,
        {},
    )

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


def test_failure_cleanup_uses_public_stop_cancel_and_shutdown_without_overwriting_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    state = driver.HarnessState(
        stage=4,
        recording_id="rec_0123456789abcdef0123456789abcdef",
        recording_job_id="job_0123456789abcdef0123456789abcdef",
        sample_started=True,
        product_ready=True,
    )

    class Client:
        def __init__(self) -> None:
            self.capture_phase = "CAPTURING"
            self.job_state = "RUNNING"
            self.actions: list[str] = []

        def call(self, method: str, path: str, body=None, **_kwargs):
            if method == "GET":
                return {
                    "capture_phase": self.capture_phase,
                    "recording": {"state": "RECORDING" if self.job_state == "RUNNING" else "CANCELLED"},
                    "job": {"state": self.job_state},
                }
            self.actions.append(path)
            if path.endswith("/capture/stop"):
                self.capture_phase = "FINISHED"
            elif path.endswith("/cancel"):
                self.job_state = "CANCELLED"
            return {"status": "NOT_PREPARED"}

    client = Client()
    monkeypatch.setattr(
        driver,
        "_wait_recording_job_terminal",
        lambda _client, _state, **_kwargs: driver._recording_snapshot(_client, _state),
    )
    primary = driver.WindowsL5Error("RECORDING_UI_NOT_READY")
    report = driver._cleanup_after_failure(client, state, {"project_owner": "identity-1"})

    assert client.actions == [
        f"/api/recordings/{state.recording_id}/capture/stop",
        f"/api/jobs/{state.recording_job_id}/cancel",
        "/api/test-identities/identity-1/reset",
        "/api/experience/official-sample/stop",
        "/api/system/shutdown",
    ]
    assert report["before"]["capture_phase"] == "CAPTURING"
    assert report["after"] == {
        "capture_phase": "FINISHED",
        "recording_state": "CANCELLED",
        "job_state": "CANCELLED",
    }
    assert driver._failure_identity(primary) == ("RECORDING_UI_NOT_READY", "RECORDING_UI_NOT_READY")


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


def test_recording_driver_failure_remains_the_primary_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    state = driver.HarnessState(stage=4)

    class Client:
        def __init__(self) -> None:
            self.capturing = False

        def call(self, method: str, path: str, body=None, **_kwargs):
            if path.endswith("/recordings"):
                return {
                    "recording": {"recording_id": "rec_0123456789abcdef0123456789abcdef"},
                    "job": {"job_id": "job_0123456789abcdef0123456789abcdef"},
                }
            if method == "GET":
                return {"capture_phase": "CAPTURING" if self.capturing else "AWAITING_CAPTURE"}
            if path.endswith("/capture/start"):
                self.capturing = True
                return {}
            raise AssertionError(path)

    class FailingDriver:
        def __init__(self, before, chromium):
            assert before == frozenset({10})
            assert chromium == Path(sys.executable)

        def wait_until_ready(self, *, timeout: float) -> None:
            assert timeout == 30

        def run_business_flow(self) -> None:
            raise driver.WindowsL5Error("RECORDING_UI_NOT_READY")

    monkeypatch.setattr(driver, "window_snapshot", lambda: frozenset({10}))
    monkeypatch.setattr(driver, "RecordingWindowDriver", FailingDriver)

    with pytest.raises(driver.WindowsL5Error, match="RECORDING_UI_NOT_READY"):
        driver._record_flow(
            Client(),
            "project-public",
            "action-public",
            "identity-public",
            Path(sys.executable),
            state,
        )
    assert state.recording_id == "rec_0123456789abcdef0123456789abcdef"
    assert state.recording_job_id == "job_0123456789abcdef0123456789abcdef"


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
        driver.WindowsL5Error("RECORDING_UI_NOT_READY"),
        driver.HarnessState(
            stage=6,
            recording_id="recording-public",
            recording_job_id="recording-job-public",
            active_run_id="run-public",
            active_run_job_id="run-job-public",
        ),
        {"actions": ["capture.stop", "job.cancel"], "after": {"job_state": "CANCELLED"}},
        control_closed=True,
        sample_closed=True,
        process_tree_closed=True,
    )

    failure = json.loads((audit / "failure.json").read_text(encoding="utf-8"))
    assert failure["failure_code"] == "RECORDING_UI_NOT_READY"
    assert failure["primary_failure"] == "RECORDING_UI_NOT_READY"
    assert failure["recording_job_id"] == "recording-job-public"
    assert failure["active_run_id"] == "run-public"
    assert failure["active_run_job_id"] == "run-job-public"
    assert "job_id" not in failure
    assert failure["cleanup"]["after"]["job_state"] == "CANCELLED"
    assert set(failure["resources"].values()) == {True}
    assert "password" not in json.dumps(failure).casefold()


def test_completed_recording_is_a_closed_cleanup_state() -> None:
    driver = official

    assert driver._recording_state_closed(
        {
            "capture_phase": "FINISHED",
            "recording_state": "COMPLETED",
            "job_state": "SUCCEEDED",
        }
    ) is True


def test_unavailable_run_result_has_stable_failure_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    monkeypatch.setattr(
        driver,
        "_wait_for",
        lambda *_args, **_kwargs: {
            "lifecycle": "FAILED",
            "result_integrity": "UNAVAILABLE",
        },
    )

    with pytest.raises(driver.SampleTestError) as caught:
        driver._wait_for_published_result(object(), "run-public", "run-job-public")

    assert driver._failure_identity(caught.value) == (
        "L5_RUN_RESULT_UNAVAILABLE",
        "L5_RUN_RESULT_UNAVAILABLE: lifecycle=FAILED integrity=UNAVAILABLE "
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
    reason="真实 Windows Recording 局部闭环只在明确授权的交互用户环境运行",
)
def test_real_recording_ui_automation_closes_before_full_l5() -> None:
    driver = official
    run_dir = _fresh_real_probe_dir()

    driver.run(ROOT, run_dir, stop_after_recording=True)

    summary = json.loads(
        (run_dir / "audit" / "sample-test" / "sample-test-summary.json").read_text(encoding="utf-8")
    )
    assert summary["recording_probe"] == "passed"
    assert summary["control_port_closed"] is True
    assert summary["sample_port_closed"] is True
    assert summary["owned_process_tree_closed"] is True


@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("JIEJIAN_RUN_WINDOWS_L5") != "1",
    reason="真实 Windows Recording 故障收口只在明确授权的交互用户环境运行",
)
def test_real_recording_driver_failure_keeps_primary_error_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    run_dir = _fresh_real_probe_dir()

    def fail_driver(_self) -> None:
        raise driver.WindowsL5Error("TEST_UI_DRIVER_FAILURE")

    monkeypatch.setattr(driver.RecordingWindowDriver, "run_business_flow", fail_driver)
    with pytest.raises(driver.WindowsL5Error, match="TEST_UI_DRIVER_FAILURE"):
        driver.run(ROOT, run_dir, stop_after_recording=True)

    failure = json.loads((run_dir / "audit" / "sample-test" / "failure.json").read_text(encoding="utf-8"))
    assert failure["failure_code"] == "TEST_UI_DRIVER_FAILURE"
    assert failure["cleanup"]["state_closed"] is True
    assert failure["cleanup"]["after"]["job_state"] in {"SUCCEEDED", "FAILED", "CANCELLED"}
    assert failure["cleanup"]["after"]["recording_state"] in {
        "PENDING_REVIEW",
        "FAILED",
        "CANCELLED",
        "SAFETY_STOPPED",
    }
    assert failure["resources"] == {
        "control_port_closed": True,
        "sample_port_closed": True,
        "owned_process_tree_closed": True,
    }
