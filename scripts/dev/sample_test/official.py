# 官方验收场景编排；运行资源、客户端与诊断由各自模块负责。
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from product.backend.infra.runtime.process.tree import process_tree_has_exited, release_process_tree, terminate_process_tree
import scripts.dev.sample_test.clients.http as sample_clients_http
import scripts.dev.sample_test.harness.lifecycle as sample_harness_lifecycle
import scripts.dev.sample_test.harness.receipt as sample_harness_receipt
import scripts.dev.sample_test.harness.state as sample_harness_state
import scripts.dev.sample_test.reporting.diagnostics as sample_reporting_diagnostics


def _phase(state: sample_harness_state.HarnessState, number: int) -> None:
    state.stage = number
    print(f"[{number}/{len(sample_harness_state.PHASE_TITLES)}] {sample_harness_state.PHASE_TITLES[number]}", flush=True)


def _wait_for_published_result(client, run_id, run_job_id):
    from scripts.dev.sample_test.current_api import wait_published
    return wait_published(client, run_id, run_job_id)


def _load_evidence(client, run_id):
    from scripts.dev.sample_test.current_api import read_result
    result = read_result(client, run_id)
    return result["evidence_index"], result["evidence"]


def _gui_complete(records, *, stop_after_setup=False):
    required = {"start", "human-approve", "prepare", "exit"}
    if not stop_after_setup:
        required |= {"submit-check", "problem-result", "limited-result", "fixed-result", "evidence-and-repair",
            "decisive-evidence", "execution-path", "history-search", "history-return", "mcp-connected",
            "mcp-level-read", "mcp-level-prepare", "mcp-level-execute", "mcp-change", "mcp-completion",
            "mcp-responsibility", "mcp-cleanup"}
    return required.issubset({item["event"] for item in records if item.get("status") == "PASSED"})


def run(
    root: Path,
    var_dir: Path,
    *,
    stop_after_setup: bool = False,
    verify_workspace_ui: bool = False,
) -> None:
    root = root.resolve()
    var_dir = var_dir.resolve()
    if any(var_dir.iterdir()):
        raise sample_harness_state.SampleTestError("sample-test 必须从全新的空运行目录开始")
    audit_dir = var_dir / "audit" / "sample-test"
    audit_dir.mkdir(parents=True)
    state = sample_harness_state.HarnessState(stage=1)
    if sample_harness_lifecycle._port_open(sample_harness_state.CONTROL_PORT):
        occupied = sample_harness_state.SampleTestError("L5_CONTROL_PORT_OCCUPIED")
        sample_reporting_diagnostics._write_failure(
            audit_dir,
            occupied,
            state,
            {
                "actions": [],
                "before": None,
                "after": None,
                "state_closed": True,
                "shutdown_requested": False,
            },
            control_closed=False,
            sample_closed=None,
            process_tree_closed=True,
        )
        raise occupied
    process: subprocess.Popen[bytes] | None = None
    log: object | None = None
    browser = None
    playwright = None
    sample_port: int | None = None
    source_runtime: sample_harness_receipt.SourceRuntime | None = None
    client = sample_clients_http.ApiClient(f"http://127.0.0.1:{sample_harness_state.CONTROL_PORT}")
    identities: dict[str, str] = {}
    project_id = ""
    primary_failure: Exception | None = None
    failure_cleanup: dict[str, object] = {}
    gui = None
    try:
        _phase(state, 1)
        process, log = sample_harness_lifecycle._start_product(root, var_dir)
        receipt_path = var_dir / "runtime" / "source" / "receipt.json"
        sample_harness_lifecycle._wait_source_prepare(
            receipt_path,
            process,
            timeout=600,
        )
        source_runtime = sample_harness_receipt._load_source_runtime(
            receipt_path,
            root,
            var_dir,
        )
        sample_harness_lifecycle._wait_product_ready(
            client,
            process,
            timeout=90,
        )
        state.product_ready = True
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(source_runtime.playwright_executable),
        )
        # 正式 GUI 同时覆盖减少动态效果；定位仍必须使用实际视口坐标，不能停在离屏测量位置。
        page = browser.new_page(viewport={"width": 2560, "height": 1440}, reduced_motion="reduce")
        client.bind_page(page)

        from scripts.dev.sample_test.current_api import prepare_current, project_run_ids, run_sequence
        from scripts.dev.sample_test.current_gui import CurrentGui
        gui = CurrentGui(page, client, audit_dir)
        def checkpoint(event, payload):
            if event == "limited-ready":
                _phase(state, 5)
            elif event == "fixed-ready":
                _phase(state, 6)
            gui.checkpoint(event, payload)
        _phase(state, 2)
        page.goto(client.origin, wait_until="networkidle")
        experience = gui.start()
        state.sample_started = True
        project_id = str(experience["project_id"])
        sample_port = int(str(experience["origin"]).rsplit(":", 1)[1])
        if not experience.get("active") or experience.get("scenario_version") != "VULNERABLE" or project_run_ids(client, project_id):
            raise sample_harness_state.SampleTestError("SAMPLE_NEW_INSTANCE_INVALID")
        _phase(state, 3)
        prepare_current(client, project_id, initial=True, gui=gui)
        prepared_identities = client.call("GET", f"/api/projects/{project_id}/test-identities")
        identities = {str(index): str(item["identity_id"]) for index, item in enumerate(prepared_identities)}
        if stop_after_setup:
            runs = []
        else:
            _phase(state, 4)
            runs = run_sequence(client, project_id, state, checkpoint=checkpoint, gui=gui)
        _phase(state, 7)
        page.goto(client.origin + "/#/tests", wait_until="networkidle")
        if not stop_after_setup:
            checkpoint("evidence-and-repair", {"project_id": project_id, "runs": runs})
            from scripts.dev.sample_test.current_mcp import run as run_mcp
            mcp_evidence = run_mcp(client, gui, project_id, runs, state)
        else:
            mcp_evidence = None
        _phase(state, 8)
        sample_harness_lifecycle._shutdown_owned_runtime(client, state, identities, browser, playwright, process, var_dir, sample_port, shutdown_action=gui.shutdown)
        browser = None
        playwright = None
        process = None
        state.product_ready = False
        gui_complete = _gui_complete(gui.records, stop_after_setup=stop_after_setup)
        sample_reporting_diagnostics._write_summary(audit_dir, {"schema_version": "1", "project_id": project_id,
            "scenario_versions": [] if stop_after_setup else ["VULNERABLE", "EVIDENCE_LIMITED", "FIXED"],
            "runs": [{"run_id": item["run_id"], "verdict": item["story"]["verdict"]} for item in runs],
            "mcp_evidence": mcp_evidence, "total_run_count": 0 if stop_after_setup else 4,
            "read_projections": ["ResultStory", "Evidence", "RunHistory", "ProjectRepair"],
            "gui_status": "PASSED" if gui_complete else "GUI_INTEGRATION_INCOMPLETE", "gui_checkpoints": gui.records,
            "control_port_closed": True, "sample_port_closed": True, "owned_process_tree_closed": True})
        if not gui_complete:
            raise sample_harness_state.SampleTestError("GUI_INTEGRATION_INCOMPLETE")
        print("默认官方示例验收完成。", flush=True)
    except Exception as error:
        primary_failure = error
        try:
            failure_cleanup = sample_harness_lifecycle._cleanup_after_failure(client, state, identities, gui=gui)
        except Exception as cleanup_error:
            failure_cleanup = {"cleanup_error": type(cleanup_error).__name__}
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
        process_tree_closed = process is None
        if process is not None:
            try:
                if process.poll() is None and failure_cleanup.get("shutdown_requested"):
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        pass
                if process.poll() is None:
                    terminate_process_tree(process, timeout=10)
                else:
                    release_process_tree(process, timeout=5)
                process_tree_closed = process_tree_has_exited(process)
            except Exception as cleanup_error:
                failure_cleanup["process_tree_cleanup_error"] = type(cleanup_error).__name__
                process_tree_closed = False
        if log is not None:
            log.close()
        if primary_failure is not None:
            try:
                sample_reporting_diagnostics._write_failure(
                    audit_dir,
                    primary_failure,
                    state,
                    failure_cleanup,
                    control_closed=not sample_harness_lifecycle._port_open(sample_harness_state.CONTROL_PORT),
                    sample_closed=None if sample_port is None else not sample_harness_lifecycle._port_open(sample_port),
                    process_tree_closed=process_tree_closed,
                )
            except Exception as artifact_error:
                print(
                    f"failure artifact write failed: {type(artifact_error).__name__}",
                    file=sys.stderr,
                    flush=True,
                )
    if primary_failure is not None:
        raise primary_failure
