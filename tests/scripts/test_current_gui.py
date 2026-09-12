# 用显式页面/响应 stub 验证普通任务链的真实动作要求，不运行浏览器或产品。
from types import SimpleNamespace as N
from urllib.parse import urlencode

import pytest

from scripts.dev.sample_test.current_gui import CurrentGui
from scripts.dev.sample_test import current_api
from scripts.dev.sample_test.official import SampleTestError


class Node:
    def __init__(self, page, kind, name, scope=()):
        self.page, self.kind, self.name, self.scope = page, kind, name, scope
    def get_by_role(self, kind, *, name, **kwargs):
        return Node(self.page, kind, name, (*self.scope, self.name))
    def get_by_text(self, name, **kwargs):
        return Node(self.page, "text", name, (*self.scope, self.name))
    def locator(self, selector):
        return Node(self.page, "locator", selector, (*self.scope, self.name))
    @property
    def first(self):
        return self
    def wait_for(self, **kwargs):
        self.page.events.append(("wait", self.name, kwargs, self.scope))
    def fill(self, value):
        self.page.events.append(("fill", self.name, value))
    def get_attribute(self, name):
        assert name == "aria-current"
        return "true" if self.page.selected else "false"
    def click(self):
        self.page.events.append(("click", self.name))
        if self.name == "复验原题":
            self.page.url = self.page.origin + "/#/tests?" + urlencode({"change_id": self.page.target_change})
        for response in self.page.responses.get(self.name, []):
            for context in self.page.pending:
                if context.predicate(response): context.value = response


class ResponseWait:
    def __init__(self, page, predicate):
        self.page, self.predicate, self.value = page, predicate, None
    def __enter__(self):
        self.page.pending.append(self)
        return self
    def __exit__(self, kind, value, traceback):
        self.page.pending.remove(self)
        if kind is None: assert self.value is not None, "expected response was not caused by click"


class Page:
    origin = "http://127.0.0.1:8765"
    def __init__(self):
        self.events, self.pending, self.responses = [], [], {}
        self.url, self.target_change, self.selected = self.origin, "change-exact", True
    def goto(self, url, **kwargs):
        self.url = url
        self.events.append(("goto", url))
    def get_by_role(self, kind, *, name, **kwargs):
        self.events.append(("locate", kind, name, kwargs))
        return Node(self, kind, name)
    def get_by_text(self, name, **kwargs):
        return Node(self, "text", name)
    def locator(self, selector):
        return Node(self, "locator", selector)
    def expect_response(self, predicate, **kwargs):
        return ResponseWait(self, predicate)
    def wait_for_url(self, predicate):
        assert predicate(self.url), "wrong change route"
    def screenshot(self, **kwargs):
        self.events.append(("screenshot",))
    def reply(self, button, method, path, data, body=None, status=200):
        response = N(url=self.origin+path, status=status, request=N(method=method, post_data_json=body),
            json=lambda: {"data": data})
        self.responses.setdefault(button, []).append(response)


class Client:
    origin = Page.origin
    def __init__(self, values):
        self.values, self.calls = values, []
    def call(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        return self.values[path]


def context(tmp_path, *, task=None):
    page = Page()
    task = task or {"route": "/tests", "task_id": "task-exact", "task_kind": "PREPARE_TEST_IDENTITY", "can_execute": True}
    client = Client({"/api/experience/official-sample": {"active": True, "project_id": "project", "scenario_version": "VULNERABLE"},
        "/api/projects/project/workspace": {"project": {"project_id": "project"}, "primary_task": task},
        "/api/projects/project/preparation": {"project_id": "project", "preparation_complete": False},
        "/api/projects/project/check-preview": {"project_id": "project", "can_execute": False}})
    return CurrentGui(page, client, tmp_path), page, client


def test_normal_pages_propose_and_prepare_once_without_starting_check(tmp_path):
    gui, page, client = context(tmp_path)
    page.reply("启动问题版", "POST", "/api/experience/official-sample/start", {"active": True})
    page.reply("使用已提供的权限提案", "POST", "/api/experience/official-sample/boundary-proposal", {"proposal": {}})
    page.reply("使用已提供的测试材料", "POST", "/api/experience/official-sample/prepare", {"scenario_prepared": True})
    gui.start(); gui.propose(); gui.prepare()
    assert ("goto", page.origin+"/#/permissions") in page.events
    assert ("goto", page.origin+"/#/tests?task_id=task-exact") in page.events
    assert ("wait", "查看与维护权限", {}, ()) in page.events
    assert ("wait", "开始检查", {}, ()) in page.events
    clicks = [item[1] for item in page.events if item[0] == "click"]
    assert clicks == ["启动官方示例", "启动问题版", "使用已提供的权限提案", "使用已提供的测试材料"]
    assert all(method == "GET" for method, _, _ in client.calls)


@pytest.mark.parametrize("change", [{"route": "/permissions"}, {"task_kind": "RUN_CURRENT_CHECK"},
    {"task_kind": "SELECT_ALLOW_CONTROL"}, {"can_execute": False}, {"task_id": None}])
def test_prepare_does_not_guess_when_workspace_is_not_preparation(tmp_path, change):
    task = {"route": "/tests", "task_id": "task", "task_kind": "PREPARE_TEST_IDENTITY", "can_execute": True, **change}
    gui, page, client = context(tmp_path, task=task)
    with pytest.raises(SampleTestError, match="GUI_PREPARATION_TASK_UNAVAILABLE"):
        gui.prepare()
    assert not page.events and all(item[0] == "GET" for item in client.calls)


@pytest.mark.parametrize("version,label", [("EVIDENCE_LIMITED", "切换到证据受限版"), ("FIXED", "切换到修复版")])
def test_switch_uses_neutral_environment_controls_and_exact_original(tmp_path, version, label):
    gui, page, client = context(tmp_path)
    reference = {"source_run_id": "run-original", "source_case_id": "case-original", "repair_fingerprint": "fingerprint"} if version == "FIXED" else None
    client.values["/api/projects/project/repair"] = {"project_id": "project", "tasks": [{"status": "REPAIR_REQUIRED", "contract": reference}]}
    client.values["/api/runs/run-original"] = {"result_integrity": "VALID", "run": {"verdict": "BLOCK"}}
    page.reply("确认切换", "POST", "/api/experience/official-sample/version", {"scenario_version": version}, {"version": version, "repair_reference": reference})
    gui.switch(version, reference)
    assert [item[1] for item in page.events if item[0] == "click"] == ["官方环境 · 问题版", label, "确认切换"]
    assert all(method == "GET" for method, _, _ in client.calls)


def test_fixed_rejects_missing_original_before_any_click(tmp_path):
    gui, page, _ = context(tmp_path)
    with pytest.raises(SampleTestError, match="GUI_ORIGINAL_REPAIR_MISSING"):
        gui.switch("FIXED", None)
    assert not page.events


@pytest.mark.parametrize("wrong_route", [False, True])
def test_repair_submission_must_click_changes_action_before_runs_post(tmp_path, wrong_route):
    gui, page, client = context(tmp_path)
    client.values["/api/projects/project/repair"] = {"project_id": "project", "tasks": [
        {"status": "READY_TO_VERIFY", "change_id": "change-exact", "contract": {"repair_fingerprint": "original-exact"}}]}
    body = {"schema_version": "2", "expected_plan_fingerprint": "plan-exact", "change_id": "change-exact", "idempotency_key": "one-key"}
    page.reply("开始检查", "POST", "/api/projects/project/runs", {"run": {"run_id": "new"}}, body, status=202)
    if wrong_route:
        page.target_change = "other"
        with pytest.raises(AssertionError, match="wrong change route"):
            gui.submit("project", body, "change-exact")
        assert ("click", "开始检查") not in page.events
    else:
        gui.submit("project", body, "change-exact")
        assert ("goto", page.origin+"/#/changes?repair_reference=original-exact") in page.events
        assert [item[1] for item in page.events if item[0] == "click"] == ["复验原题", "开始检查"]
    assert all(method == "GET" for method, _, _ in client.calls)


def result_payload():
    source = {"source_label": "本轮冻结来源", "evidence_refs": ["ev-one", "ev-two"]}
    deny = {"case_id": "case-original", "display_name": "受保护动作", "permission": {"expectation": "DENY"},
        "fact_comparison": {"planned_identity": {"label": "操作账号"}}, "decisive_proof_chain": [source]}
    return {"run_id": "run-original", "story": {"judgement": "本轮已发布判断", "actions": [deny, {"permission": {"expectation": "ALLOW"}}]}}


@pytest.mark.parametrize("selected,operations", [(True, 1), (False, 2)])
def test_problem_decisive_evidence_is_opened_within_two_actions_and_gets_checked(tmp_path, selected, operations):
    gui, page, client = context(tmp_path)
    page.selected = selected
    for ref in ("ev-one", "ev-two"):
        page.reply("为什么这样判断？查看本轮冻结来源证据", "GET", f"/api/runs/run-original/evidence/{ref}", {"run_id": "run-original", "evidence_id": ref})
    gui.checkpoint("problem-result", result_payload())
    record = next(item for item in gui.records if item["event"] == "decisive-evidence")
    assert record["open_operations"] == operations and record["evidence_refs"] == ["ev-one", "ev-two"]
    questions = {item[1] for item in page.events if item[0] == "wait" and "已发布证据" in item[3]}
    assert {"在哪里看到", "看到什么", "因此支持什么", "不能单独证明什么"} <= questions
    assert ("click", ".ant-drawer-close") in page.events
    assert ("locate", "heading", "本轮已发布判断", {"level": 1, "exact": True}) in page.events
    assert client.calls == []


@pytest.mark.parametrize("fault", ["missing_source", "wrong_reference"])
def test_problem_evidence_failure_cannot_claim_checkpoint_passed(tmp_path, fault):
    gui, page, _ = context(tmp_path)
    payload = result_payload()
    if fault == "missing_source": payload["story"]["actions"][0]["decisive_proof_chain"] = []
    else:
        for ref in ("ev-one", "ev-two"):
            page.reply("为什么这样判断？查看本轮冻结来源证据", "GET", f"/api/runs/run-original/evidence/{ref}", {"run_id": "other", "evidence_id": ref})
    with pytest.raises(SampleTestError, match="GUI_DECISIVE_EVIDENCE"):
        gui.checkpoint("problem-result", payload)
    assert gui.records == []


@pytest.mark.parametrize("gui_mode", [True, False])
@pytest.mark.parametrize("stale", [True, False])
def test_prepare_rebinds_before_the_only_prepare_call(monkeypatch, gui_mode, stale):
    calls = []
    before = {"policy_epoch": 1, "permission_intents": [], "actor_bindings": [{"status": "CURRENT"}],
        "action_bindings": [{"status": "STALE" if stale else "CURRENT"}]}
    class Api:
        def call(self, method, path, body=None, **kwargs):
            if path.endswith("/runs"): return []
            if path.endswith("/business-boundaries"): return before
            if path.endswith("/maintenance-draft"): return {"boundary_state_fingerprint": "fp", "actors": [], "actions": [], "permissions": []}
            calls.append("maintenance" if path.endswith("maintenance-proposals") else "approve" if path.endswith("approve") else "prepare")
            return {"scenario_prepared": True}
    class Gui:
        def maintenance(self, project): calls.append("maintenance"); return {}
        def approve(self, project, proposal): calls.append("approve")
        def prepare(self): calls.append("prepare"); return {"scenario_prepared": True}
    monkeypatch.setattr(current_api, "_proposal", lambda *args: N(proposal_id="proposal", proposal_fingerprint="exact"))
    def check(proposal, boundary):
        assert boundary is before
        calls.append("assert-rebind")
    monkeypatch.setattr(current_api, "_assert_rebind", check)
    current_api.prepare_current(Api(), "project", gui=Gui() if gui_mode else None)
    assert calls == (["maintenance", "assert-rebind", "approve", "prepare"] if stale else ["prepare"])


def test_prepare_structured_pending_is_failure_not_a_second_probe(monkeypatch):
    writes = []
    class Api:
        def call(self, method, path, body=None, **kwargs):
            if path.endswith("/runs"): return []
            if path.endswith("/business-boundaries"): return {"policy_epoch": 1, "permission_intents": [], "actor_bindings": [], "action_bindings": []}
            if path.endswith("/preparation") or path.endswith("/check-preview"): return {"project_id": "project", "preparation_complete": False, "can_execute": False}
            writes.append(path)
            return {"scenario_prepared": False, "pending_tasks": ["HUMAN_IMPLEMENTATION_REBIND_REQUIRED"]}
    with pytest.raises(SampleTestError, match="SAMPLE_PREPARATION_INCOMPLETE"):
        current_api.prepare_current(Api(), "project")
    assert writes == ["/api/experience/official-sample/prepare"]


def test_ready_fixed_result_original_evidence_and_exit_keep_real_controls(tmp_path):
    gui, page, _ = context(tmp_path)
    for name in ("limited-ready", "fixed-ready"):
        gui.checkpoint(name, {"project_id": "project"})
    fixed = {"run_id": "fixed", "story": {"judgement": "本轮修复结果", "repair_verification": {"status": "VERIFIED"}}}
    gui.checkpoint("fixed-result", fixed)
    gui.checkpoint("evidence-and-repair", {"runs": [fixed]})
    page.reply("安全退出", "POST", "/api/system/shutdown", {"accepted": True})
    gui.shutdown()
    clicks = [item[1] for item in page.events if item[0] == "click"]
    assert "开始检查" not in clicks
    assert clicks == ["查看原问题", "为什么定位在这里？查看定位证据", ".ant-drawer-close",
        "设置与更多", "退出界鉴", "安全退出"]
    assert ("wait", "原问题已经通过复验，要求保留的合法能力未受影响", {}, ()) in page.events
    assert ("wait", "原题复验通过", {}, ()) in page.events
    assert [record["event"] for record in gui.records] == ["limited-ready", "fixed-ready", "fixed-result", "evidence-and-repair", "exit"]


def test_fixed_result_does_not_display_verified_title_without_backend_verification(tmp_path):
    gui, page, _ = context(tmp_path)
    with pytest.raises(SampleTestError, match="GUI_ORIGINAL_REPAIR_NOT_VERIFIED"):
        gui.checkpoint("fixed-result", {"run_id": "fixed", "story": {"judgement": "普通本轮结果", "repair_verification": {"status": "INCONCLUSIVE"}}})
    assert gui.records == []
    assert not any(item[0] == "wait" and item[1] == "原问题已经通过复验，要求保留的合法能力未受影响" for item in page.events)


def test_fixed_submission_requires_unique_original_task_before_any_click(tmp_path):
    gui, page, client = context(tmp_path)
    client.values["/api/projects/project/repair"] = {"project_id": "project", "tasks": []}
    with pytest.raises(SampleTestError, match="GUI_REPAIR_NOT_READY"):
        gui.submit("project", {"expected_plan_fingerprint": "plan"}, "change-exact", require_repair=True)
    assert page.events == []


@pytest.mark.parametrize("mismatch", [False, True])
def test_valid_materials_are_reused_without_reinstall_or_check_submission(tmp_path, mismatch):
    gui, page, client = context(tmp_path, task={"route": "/tests", "task_id": "old-result", "task_kind": "VIEW_CURRENT_RESULT", "can_execute": True})
    client.values["/api/projects/project/preparation"] = {"project_id": "other" if mismatch else "project", "preparation_complete": True}
    client.values["/api/projects/project/check-preview"] = {"project_id": "project", "can_execute": True}
    if mismatch:
        with pytest.raises(SampleTestError, match="GUI_PREPARATION_TASK_UNAVAILABLE"): gui.prepare()
        assert not page.events
    else:
        actual = gui.prepare()
        assert actual is client.values["/api/experience/official-sample"]
        assert "scenario_prepared" not in actual
        assert gui.records == [{"event": "prepare-reused", "status": "PASSED"}]
        assert ("wait", "开始检查", {}, ()) in page.events
        assert not any(e[0] == "click" for e in page.events)
    assert all(method == "GET" for method, _, _ in client.calls)


def test_prepare_accepts_public_readiness_without_rewriting_sample_marker():
    calls=[]
    class Api:
        def call(self, method, path, body=None, **kwargs):
            calls.append((method,path))
            if path.endswith("/runs"): return []
            if path.endswith("/business-boundaries"): return {"policy_epoch":1,"permission_intents":[],"actor_bindings":[],"action_bindings":[]}
            if path.endswith("/preparation"): return {"project_id":"project","preparation_complete":True}
            if path.endswith("/check-preview"): return {"project_id":"project","can_execute":True}
            raise AssertionError(path)
    actual={"project_id":"project","scenario_prepared":False}
    result=current_api.prepare_current(Api(),"project",gui=N(prepare=lambda:actual))
    assert result is actual and result["scenario_prepared"] is False
    assert all(method == "GET" for method, _ in calls)
