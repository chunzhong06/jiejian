# 验证默认验收GUI写入不会再被API机械步骤重复执行，未知回执仅定位本轮资源供清理。
from types import SimpleNamespace

import pytest

from scripts.dev.sample_test import current_api, official


def test_gui_run_submission_is_not_repeated_through_api(monkeypatch):
    calls, submitted = [], []

    class Client:
        def call(self, method, path, *args, **kwargs):
            calls.append((method, path))
            if "check-preview" in path:
                return {"can_execute": True, "action_count": 2, "case_count": 3, "plan_fingerprint": "frozen"}
            return []

    def submit(project, body, change):
        submitted.append((project, body, change))
        return {"run": {"run_id": "new-run"}, "job": {"job_id": "owned-job"}}

    monkeypatch.setattr(current_api, "wait_published", lambda *args: None)
    monkeypatch.setattr(current_api, "read_result", lambda *args: {"run_id": "new-run"})
    monkeypatch.setattr(current_api, "assert_current_result", lambda *args, **kwargs: None)
    state = official.HarnessState()
    result = current_api.run_current(Client(), "project", state, name="fixed", expected="PASS", change_id="exact-change", gui=SimpleNamespace(submit=submit))
    assert result == {"run_id": "new-run"}
    assert len(submitted) == 1 and submitted[0][2] == "exact-change"
    assert submitted[0][1]["expected_plan_fingerprint"] == "frozen"
    assert all(method == "GET" for method, _ in calls)
    assert state.active_run_id is None and state.active_run_job_id is None


def test_uncertain_gui_submission_reads_owned_run_and_never_resubmits():
    calls, count = [], 0

    class Client:
        def call(self, method, path, *args, **kwargs):
            nonlocal count
            calls.append((method, path))
            if "check-preview" in path:
                return {"can_execute": True, "action_count": 2, "case_count": 3, "plan_fingerprint": "frozen"}
            if path == "/api/runs/owned-run":
                return {"job": {"job_id": "owned-job"}}
            count += 1
            return [] if count == 1 else [{"run": {"run_id": "owned-run"}}]

    def submit(*args):
        raise TimeoutError("receipt unavailable")

    state = official.HarnessState()
    with pytest.raises(TimeoutError):
        current_api.run_current(Client(), "project", state, name="problem", expected="BLOCK", gui=SimpleNamespace(submit=submit))
    assert state.active_run_id == "owned-run" and state.active_run_job_id == "owned-job"
    assert all(method == "GET" for method, _ in calls)
