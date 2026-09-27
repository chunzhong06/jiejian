# 验证验收脚本的运行身份与资源生命周期。
from __future__ import annotations
import scripts.dev.sample_test.harness.lifecycle as sample_harness_lifecycle
import scripts.dev.sample_test.harness.receipt as sample_harness_receipt
import scripts.dev.sample_test.harness.state as sample_harness_state
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
import pytest
from scripts.dev.sample_test import official
from tests.scripts._support_sample_test import ROOT, COMMON_IDENTITY_NAMES, _fresh_real_probe_dir, _write_receipt

def test_real_start_receipt_builds_complete_runtime_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    receipt_path, var_dir, frontend, browser = _write_receipt(tmp_path)
    for name in COMMON_IDENTITY_NAMES:
        monkeypatch.delenv(name, raising=False)

    runtime = sample_harness_receipt._load_source_runtime(receipt_path, ROOT, var_dir)

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

    with pytest.raises(sample_harness_state.SampleTestError, match="source receipt 与当前受控运行输入不一致"):
        sample_harness_receipt._load_source_runtime(receipt_path, ROOT, different)

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
    monkeypatch.setattr(sample_harness_lifecycle, "spawn_managed_process", spawn)
    var_dir = tmp_path / "var"
    var_dir.mkdir()
    process, log = sample_harness_lifecycle._start_product(ROOT, var_dir)
    log.close()

    assert process.pid == 123
    command = captured["command"]
    assert str(ROOT / "start.cmd") in command
    assert command[-4:] == ["-Mode", "Gui", "-VarDir", str(var_dir)]
    assert "product.backend.cli" not in command
    assert str(captured["kwargs"]["tree_name"]).startswith("jiejian-sample-test-")

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
                raise sample_harness_state.SampleTestError("POST runs 无法访问: TimeoutError")
            return {"run": {"run_id": "run-current"}, "job": {"job_id": "job-current"}}
    monkeypatch.setattr(current, "wait_published", lambda *args: None)
    monkeypatch.setattr(current, "assert_current_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(current, "read_result", lambda *args: {"story": {"verdict": "PASS", "actions": [
        {"permission": {"expectation": "ALLOW"}} for _ in range(3)]}, "evidence": [
        {"case": {"protected_effect_ids": ["effect"], "permission": {"expectation": "ALLOW"}}} for _ in range(3)]})
    current.run_current(Client(), "project", sample_harness_state.HarnessState(), name="fixed", expected="PASS", change_id="chg_exact")
    writes = [body for method, _, body in calls if method == "POST"]
    assert len(writes) == 2 and writes[0] == writes[1]
    assert writes[0]["schema_version"] == "2" and writes[0]["expected_plan_fingerprint"] == "a" * 64
    assert writes[0]["change_id"] == "chg_exact"
    assert calls[0][1].endswith("?change_id=chg_exact")
    assert calls[2][:2] == ("GET", "/api/projects/project/runs")

def test_occupied_default_port_writes_failure_without_touching_the_existing_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = official
    run_dir = tmp_path / "occupied-port"
    run_dir.mkdir()
    monkeypatch.setattr(sample_harness_lifecycle, "_port_open", lambda _port: True)
    monkeypatch.setattr(
        sample_harness_lifecycle,
        "_cleanup_after_failure",
        lambda *_args, **_kwargs: pytest.fail("端口预占用不得调用产品清理 API"),
    )

    with pytest.raises(sample_harness_state.SampleTestError, match="L5_CONTROL_PORT_OCCUPIED"):
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
        sample_harness_lifecycle,
        "lock_is_available",
        lambda path: observed.append(path) or True,
    )

    assert sample_harness_lifecycle._runtime_locks_released(tmp_path) is True
    assert observed == [serve_lock, worker_lock]

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
