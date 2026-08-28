# 验证自动 L5 Harness 的真实启动、可信回执、Evidence 层级、UIA 边界与失败清理，不运行完整 sample-test。

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from playwright.sync_api import sync_playwright

from product.backend.infra.runtime.process.identity import python_environment_report


ROOT = Path(__file__).resolve().parents[2]
DRIVER_PATH = ROOT / "scripts" / "dev" / "sample_test.py"
WINDOWS_DRIVER_PATH = ROOT / "scripts" / "dev" / "sample_test_windows.py"
COMMON_IDENTITY_NAMES = {
    "JIEJIAN_PYTHON_EXECUTABLE",
    "JIEJIAN_PYTHON_ENVIRONMENT_PATH",
    "JIEJIAN_PYTHON_ENVIRONMENT_TYPE",
    "JIEJIAN_PROJECT_ROOT",
    "JIEJIAN_RUNTIME_FINGERPRINT",
    "JIEJIAN_RUNTIME_MODE",
    "JIEJIAN_VAR_DIR",
}


def _load_module(path: Path, name: str) -> ModuleType:
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_driver() -> ModuleType:
    return _load_module(DRIVER_PATH, "jiejian_sample_test_driver")


def _load_windows_driver() -> ModuleType:
    return _load_module(WINDOWS_DRIVER_PATH, "jiejian_sample_test_windows_driver")


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
    driver = _load_driver()
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
    driver = _load_driver()
    receipt_path, _var_dir, _frontend, _browser = _write_receipt(tmp_path)
    different = tmp_path / "different-var"
    different.mkdir()

    with pytest.raises(driver.SampleTestError, match="source receipt 与当前受控运行输入不一致"):
        driver._load_source_runtime(receipt_path, ROOT, different)


def test_start_product_invokes_root_start_cmd_and_owns_its_process_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _load_driver()
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


def test_start_waits_for_source_prepare_before_control_ready(
    tmp_path: Path,
) -> None:
    driver = _load_driver()

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


def test_cli_equivalence_compares_published_evidence_index_not_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _load_driver()
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
    cli_index = evidence_index

    def run_cli(_root, _var_dir, _environment, *arguments: str) -> str:
        if arguments[:2] == ("--human", "result"):
            return "已发布证据：2 项" if arguments[2] == "evidence" else "检查结果"
        if arguments[:2] == ("--human", "history"):
            return "历史变化"
        if arguments[1:3] == ("result", "show"):
            return json.dumps({"data": presentation})
        if arguments[1:3] == ("result", "evidence"):
            return json.dumps({"data": {"run_id": run_id, "evidence": cli_index}})
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

    cli_index = evidence_index[:1]
    with pytest.raises(
        driver.SampleTestError,
        match=f"L5_CLI_EVIDENCE_INDEX_MISMATCH: run_id={run_id}",
    ):
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
    windows = _load_windows_driver()
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
    windows = _load_windows_driver()
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
        ("invoke", "生成完整资料包"),
        ("Text", "完整项目资料包已生成。"),
        ("invoke", "撤销本次导出"),
        ("invoke", "确认撤销"),
        ("Text", "已撤销"),
        ("Button", "重新生成资料包"),
    ]


def test_text_wait_accepts_repeated_state_without_relaxing_buttons() -> None:
    windows = _load_windows_driver()
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
    driver = _load_driver()
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
    driver = _load_driver()
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
    driver = _load_driver()
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


def test_recording_review_merges_ui_action_with_following_network_step() -> None:
    driver = _load_driver()
    calls: list[tuple[str, str, dict[str, object]]] = []
    merged_draft = {
        "steps": [
            {"id": "step-000001", "method": "POST"},
            {"id": "step-000002", "method": "DELETE"},
        ]
    }

    class Client:
        def call(self, method: str, path: str, body: dict[str, object]):
            calls.append((method, path, body))
            return {"draft": merged_draft}

    draft = {
        "steps": [
            {"id": "step-000001", "method": "POST"},
            {"id": "step-000002", "method": None},
            {"id": "step-000003", "method": "DELETE"},
        ]
    }
    result = driver._merge_recording_ui_steps(Client(), "recording-public", draft)

    assert result is merged_draft
    assert calls == [
        (
            "POST",
            "/api/recordings/recording-public/review",
            {
                "schema_version": "1",
                "command": {
                    "schema_version": "1",
                    "operation": "MERGE_ADJACENT_STEPS",
                    "left_step_id": "step-000002",
                    "right_step_id": "step-000003",
                },
            },
        )
    ]


def test_runtime_lock_receipts_do_not_count_as_active_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _load_driver()
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
    driver = _load_driver()
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
    driver = _load_driver()

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
    driver = _load_driver()
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
    driver = _load_driver()
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

    driver = _load_driver()
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
    windows = _load_windows_driver()
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
    driver = _load_driver()
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
    driver = _load_driver()
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
