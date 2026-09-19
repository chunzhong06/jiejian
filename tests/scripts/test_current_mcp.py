# 以显式 SDK/GUI/公开状态 stub 验证同实例 MCP 权限、回执和配对清理；不接触真实凭据或服务。
from types import SimpleNamespace as N

import pytest
from mcp import MCPError

from scripts.dev.sample_test import current_mcp as mcp
from scripts.dev.sample_test.official import HarnessState, SampleTestError


class Control:
    origin = "http://127.0.0.1:8765"
    def __init__(self, paired):
        self.paired, self.level, self.calls = paired, "READ", []
        self.runs, self.changes = ["problem", "limited", "fixed"], []
        self.active = False

    def call(self, method, path, body=None, **kwargs):
        self.calls.append((method, path))
        if path == "/api/mcp/access":
            return dict(paired=self.paired, accepting_connections=True, project_grants=[dict(project_id="project", level=self.level)])
        if path == "/api/mcp/access/reveal":
            assert method == "POST" and self.paired
            return dict(access_token="t" * 40)
        if path == "/api/mcp/access/forget":
            assert method == "POST"
            self.paired = False
            return dict(paired=False)
        if path == "/api/projects/project/runs":
            return [dict(run=dict(run_id=name, project_id="project", lifecycle="RUNNING" if self.active and name == "mcp-new" else "COMPLETED")) for name in self.runs]
        if path == "/api/projects/project/source-changes":
            return [dict(manifest=dict(project_id="project", change_id=name)) for name in self.changes]
        if path == "/api/projects/project/source-changes/change-mcp":
            return dict(manifest=dict(repair_reference=None))
        if path == "/api/runs/mcp-new":
            return dict(run=dict(project_id="project"), job=dict(job_id="job-mcp"))
        raise AssertionError((method, path))


class Gui:
    def __init__(self, control, fault):
        self.control, self.fault, self.events = control, fault, []

    def _mark(self, name): self.events.append(name)
    def mcp_pair(self):
        assert not self.control.paired
        self.events.append("pair-click")
        self.control.paired = True
        if self.fault == "pair_unknown": raise RuntimeError("secret response must not escape")
        return dict(access_token="t" * 40)
    def mcp_forget(self):
        self.events.append("forget-click")
        if self.fault == "forget_rejected":
            raise SampleTestError("GUI_ACTION_REJECTED: path=/api/mcp/access/forget status=503")
        if self.fault == "forget_unknown":
            self.control.paired = False
            raise RuntimeError("lost reply")
        if self.fault == "forget_before_write": raise RuntimeError("GUI unavailable")
        self.control.paired = False
    def mcp_level(self, project, level):
        assert project == "project"
        self.events.append("level-" + level)
        self.control.level = level
    def mcp_connected(self, name):
        assert name == mcp.CLIENT_NAME
        self.events.append("connected")
    def mcp_change(self, change):
        assert change["submitted_by"] == "MCP · " + mcp.CLIENT_NAME
        self.events.append("change-visible-manual-closed")
    def history_search(self, project, query):
        assert (project, query) == ("project", "problem")
        self.events.append("history-filter")
    def dismiss_completion(self): self.events.append("dismiss")
    def mcp_completion(self, result, query):
        assert (result["run_id"], query) == ("mcp-new", "problem")
        self.events.append("exact-completion-and-return")


def scenario(monkeypatch, *, paired=True, fault=None):
    control, state = Control(paired), HarnessState()
    gui, calls = Gui(control, fault), []
    originals = [dict(run_id=name, story=dict(verdict=verdict)) for name, verdict in zip(control.runs, ["BLOCK", "INCONCLUSIVE", "PASS"])]
    extra = dict(run_id="mcp-new", story=dict(verdict="PASS", change_context=dict(change_id="change-mcp"),
        actions=[dict(action_id="export"), dict(action_id="export"), dict(action_id="view")],
        repair_verification=dict(status="VERIFIED") if fault == "verified" else None))
    values = {item["run_id"]: item for item in originals + [extra]}
    def wait(client, run, job):
        assert (client, run, job) == (control, "mcp-new", "job-mcp")
        control.active = False
    monkeypatch.setattr(mcp.current_api, "wait_published", wait)
    monkeypatch.setattr(mcp.current_api, "read_result", lambda client, run: values[run])
    def verify(result, *, expected):
        assert result is extra and expected == "PASS"
        calls.append(("assert-full-result", {}))
    monkeypatch.setattr(mcp.current_api, "assert_current_result", verify)
    class Session:
        def __init__(self, origin, token): assert origin == control.origin and token == "t" * 40
        def __enter__(self): return self
        def __exit__(self, *args): calls.append(("closed", {}))
        def call(self, name, arguments):
            calls.append((name, arguments))
            assert arguments["project_id"] == "project"
            denied = name == "jiejian_change_submit" and control.level == "READ" or name == "jiejian_check_run" and control.level == "PREPARE"
            if denied:
                if fault == "denial_writes": control.changes.append("illegal")
                if fault == "wrong_denial": raise MCPError(-32042, "private", dict(error_code="MCP_AUTH_REQUIRED"))
                if fault != "no_denial": raise MCPError(-32043, "private", dict(error_code="MCP_PERMISSION_REQUIRED"))
                return N(is_error=False, structured_content={})
            if name in {"jiejian_project_show", "jiejian_check_status"}:
                return N(is_error=False, structured_content=dict(project_id="other" if fault == "foreign_read" else "project", action_count=2, case_count=3, can_execute=True))
            if name == "jiejian_change_submit":
                assert arguments == dict(project_id="project", reason=mcp.REASON, claimed_paths=[])
                control.changes.append("change-mcp")
                value = dict(project_id="project", change_id="change-mcp", reason=mcp.REASON, submitted_by="MCP · " + mcp.CLIENT_NAME,
                    claimed_paths=[], added_paths=[], modified_paths=["unexpected"] if fault == "changed_source" else [], removed_paths=[])
                return N(is_error=False, structured_content=value)
            assert name == "jiejian_check_run" and arguments == dict(project_id="project", idempotency_key=mcp.RUN_KEY, change_id="change-mcp")
            control.runs.append("mcp-new"); control.active = True
            if fault == "run_unknown": raise RuntimeError("Authorization secret must not escape")
            return N(is_error=False, structured_content=dict(project_id="foreign" if fault == "foreign_run" else "project",
                run_id="foreign-run" if fault == "foreign_run" else "mcp-new", job=dict(job_id="job-mcp")))
    return control, gui, state, originals, calls, Session


@pytest.mark.parametrize("paired", [True, False])
def test_fourth_ordinary_run_keeps_originals_and_pairing_ownership(monkeypatch, paired):
    control, gui, state, originals, calls, session = scenario(monkeypatch, paired=paired)
    result = mcp.run(control, gui, "project", originals, state, session_factory=session)
    assert result["total_run_count"] == 4 and result["scope"] == "ordinary-full-check"
    assert result["actual_changed_path_count"] == 0 and len(originals) == 3
    assert control.paired == paired and control.level == "READ" and not state.mcp_cleanup_pending
    assert state.active_run_id is None
    assert [name for name, _ in calls].count("jiejian_change_submit") == 2
    assert [name for name, _ in calls].count("jiejian_check_run") == 2
    assert gui.events == ([] if paired else ["pair-click"]) + ["level-READ", "connected", "level-PREPARE",
        "change-visible-manual-closed", "level-EXECUTE", "history-filter", "dismiss", "exact-completion-and-return",
        "mcp-responsibility", "level-READ"] + ([] if paired else ["forget-click"]) + ["mcp-cleanup"]
    assert all(path not in {"/api/mcp/access/pair", "/api/mcp/access/rotate", "/api/mcp/access/forget"} for _, path in control.calls)


@pytest.mark.parametrize("fault,code", [("foreign_read", "MCP_READ_PROJECT_MISMATCH"), ("no_denial", "MCP_EXPECTED_DENIAL_MISSING"),
    ("wrong_denial", "MCP_CALL_REJECTED"), ("denial_writes", "MCP_DENIAL_CREATED_STATE"), ("changed_source", "MCP_CHANGE_FACTS_MISMATCH"),
    ("verified", "MCP_ORDINARY_RUN_MARKED_VERIFIED"), ("run_unknown", "MCP_RECEIPT_UNKNOWN"), ("foreign_run", "MCP_RUN_RECEIPT_MISMATCH")])
def test_failures_stop_without_retry_and_do_not_accept_foreign_cleanup_ids(monkeypatch, fault, code):
    control, gui, state, originals, calls, session = scenario(monkeypatch, fault=fault)
    with pytest.raises(SampleTestError, match=code) as caught:
        mcp.run(control, gui, "project", originals, state, session_factory=session)
    assert "secret" not in str(caught.value) and "private" not in str(caught.value)
    assert len([args for name, args in calls if name == "jiejian_check_run" and args.get("change_id")]) <= 1
    assert control.paired
    if fault in {"run_unknown", "foreign_run"}:
        assert (state.active_run_id, state.active_run_job_id) == ("mcp-new", "job-mcp")
        with pytest.raises(SampleTestError, match="MCP_CLEANUP_ACTIVE_RUN"):
            mcp.cleanup(control, gui, state)
        control.active = False
    mcp.cleanup(control, gui, state)
    assert control.paired and control.level == "READ"
    assert "forget-click" not in gui.events


@pytest.mark.parametrize("fault", ["pair_unknown", "forget_unknown", "forget_before_write"])
def test_new_pairing_is_cleaned_after_unknown_receipt_without_repeat_pair(monkeypatch, fault):
    control, gui, state, originals, calls, session = scenario(monkeypatch, paired=False, fault=fault)
    if fault == "pair_unknown":
        with pytest.raises(SampleTestError, match="MCP_SCENARIO_FAILED"):
            mcp.run(control, gui, "project", originals, state, session_factory=session)
        mcp.cleanup(control, gui, state)
    else:
        mcp.run(control, gui, "project", originals, state, session_factory=session)
    assert not control.paired and not state.mcp_cleanup_pending
    assert gui.events.count("pair-click") == 1 and gui.events.count("forget-click") == 1
    assert control.calls.count(("POST", "/api/mcp/access/forget")) == int(fault == "forget_before_write")


@pytest.mark.parametrize("missing", ["execution-path", "history-search", "mcp-connected", "mcp-change", "mcp-completion", "mcp-cleanup"])
def test_official_requires_gui_records_and_setup_only_skips_mcp(missing):
    from scripts.dev.sample_test.official import _gui_complete
    names = {"start", "human-approve", "prepare", "exit", "submit-check", "problem-result", "limited-result", "fixed-result", "evidence-and-repair",
        "decisive-evidence", "execution-path", "history-search", "history-return", "mcp-connected", "mcp-level-read", "mcp-level-prepare", "mcp-level-execute",
        "mcp-change", "mcp-completion", "mcp-responsibility", "mcp-cleanup"}
    records = [dict(event=name, status="PASSED") for name in names]
    assert _gui_complete(records)
    assert not _gui_complete([item for item in records if item["event"] != missing])
    assert _gui_complete([dict(event=name, status="PASSED") for name in ("start", "human-approve", "prepare", "exit")], stop_after_setup=True)


def test_sdk_bridge_keeps_async_transport_off_sync_gui_thread(monkeypatch):
    import threading
    from contextlib import asynccontextmanager
    main = threading.get_ident()
    events = []
    @asynccontextmanager
    async def transport(origin, token):
        assert origin == Control.origin and token == "t" * 40
        events.append(("enter", threading.get_ident()))
        class Client:
            async def call_tool(self, name, arguments):
                assert name == "jiejian_project_show" and arguments == {"project_id": "project"}
                events.append(("call", threading.get_ident()))
                return "response"
        try: yield Client()
        finally: events.append(("exit", threading.get_ident()))
    monkeypatch.setattr(mcp, "_sdk_client", transport)
    bridge = mcp.SDKSession(Control.origin, "t" * 40)
    with bridge as session:
        assert session.call("jiejian_project_show", {"project_id": "project"}) == "response"
        assert bridge.token is None
    assert bridge.client is None and bridge.portal is None
    assert [kind for kind, _ in events] == ["enter", "call", "exit"]
    assert all(thread != main for _, thread in events)


def test_acknowledged_run_retains_cleanup_identity_if_followup_read_fails(monkeypatch):
    control, gui, state, originals, calls, session = scenario(monkeypatch)
    original = control.call
    def interrupted(method, path, *args, **kwargs):
        if path == "/api/runs/mcp-new": raise OSError("private read failure")
        return original(method, path, *args, **kwargs)
    control.call = interrupted
    with pytest.raises(SampleTestError, match="MCP_SCENARIO_FAILED:OSError"):
        mcp.run(control, gui, "project", originals, state, session_factory=session)
    assert (state.active_run_id, state.active_run_job_id) == ("mcp-new", "job-mcp")
    assert len([args for name, args in calls if name == "jiejian_check_run" and args.get("change_id")]) == 1


def test_unknown_run_receipt_remains_primary_when_recovery_read_also_fails(monkeypatch):
    control, gui, state, originals, calls, session = scenario(monkeypatch, fault="run_unknown")
    original = control.call
    def interrupted(method, path, *args, **kwargs):
        if path.endswith("/runs") and "mcp-new" in control.runs: raise ValueError("secondary read failure")
        return original(method, path, *args, **kwargs)
    control.call = interrupted
    with pytest.raises(SampleTestError, match="MCP_RECEIPT_UNKNOWN:RuntimeError") as caught:
        mcp.run(control, gui, "project", originals, state, session_factory=session)
    assert "secondary" not in str(caught.value)
    assert state.mcp_cleanup_pending
    assert len([args for name, args in calls if name == "jiejian_check_run" and args.get("change_id")]) == 1


def test_official_failure_cancels_before_mcp_pairing_cleanup(monkeypatch):
    from scripts.dev.sample_test.official import _cleanup_after_failure
    control, gui, state, _, _, _ = scenario(monkeypatch, paired=False)
    control.paired, control.active, control.level = True, True, "EXECUTE"
    control.runs.append("mcp-new")
    state.product_ready, state.mcp_cleanup_pending, state.mcp_created_pairing = True, True, True
    state.mcp_project_id, state.active_run_id, state.active_run_job_id = "project", "mcp-new", "job-mcp"
    original = control.call
    def lifecycle(method, path, *args, **kwargs):
        if path == "/api/jobs/job-mcp/cancel":
            control.calls.append((method, path)); control.active = False
            return {}
        if path == "/api/system/shutdown":
            control.calls.append((method, path)); return {}
        value = original(method, path, *args, **kwargs)
        if path == "/api/runs/mcp-new": value["job"]["state"] = "CANCELLED"
        return value
    control.call = lifecycle
    report = _cleanup_after_failure(control, state, {}, gui=gui)
    assert report["state_closed"] and report["actions"] == ["check.cancel", "mcp.cleanup", "system.shutdown"]
    assert not control.paired and control.level == "READ" and not state.mcp_cleanup_pending
    assert state.active_run_id is None


def test_confirmed_pairing_cleanup_rejection_never_retries_by_api_or_outer_cleanup(monkeypatch):
    control, gui, state, originals, _, session = scenario(monkeypatch, paired=False, fault="forget_rejected")
    with pytest.raises(SampleTestError, match="GUI_ACTION_REJECTED"):
        mcp.run(control, gui, "project", originals, state, session_factory=session)
    with pytest.raises(SampleTestError, match="MCP_PAIRING_CLEANUP_UNRESOLVED"):
        mcp.cleanup(control, gui, state)
    assert control.paired and state.mcp_cleanup_pending
    assert gui.events.count("forget-click") == 1
    assert ("POST", "/api/mcp/access/forget") not in control.calls
