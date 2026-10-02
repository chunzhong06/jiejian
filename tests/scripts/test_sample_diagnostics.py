# 验证验收脚本的公开失败诊断。
from __future__ import annotations
import tests.acceptance.sample_test.harness.lifecycle as sample_harness_lifecycle
import tests.acceptance.sample_test.harness.state as sample_harness_state
import tests.acceptance.sample_test.reporting.diagnostics as sample_reporting_diagnostics
import json
from pathlib import Path
import pytest
from tests.acceptance.sample_test import official


def test_nested_gui_failure_has_scoped_location_without_private_body(tmp_path):
    from types import SimpleNamespace
    from tests.acceptance.sample_test.current_gui import CurrentGui

    class Pending:
        value = SimpleNamespace(status=503, text='token=never-publish-this')
        def __enter__(self): return self
        def __exit__(self, *args): return False

    page = SimpleNamespace(expect_response=lambda *args, **kwargs: Pending())
    gui = CurrentGui(page, SimpleNamespace(origin='http://127.0.0.1:8765'), tmp_path)
    try:
        gui._response('/api/example', lambda: None)
    except sample_harness_state.SampleTestError as error:
        sample_reporting_diagnostics._write_failure(tmp_path, error,
            sample_harness_state.HarnessState(), {}, control_closed=True,
            sample_closed=True, process_tree_closed=True)
    raw = (tmp_path/'failure.json').read_text(encoding='utf8')
    payload = json.loads(raw)
    assert payload['failure_code'] == 'GUI_ACTION_REJECTED'
    assert any(location.startswith('gui/session.py:') for location in payload['failure_location'])
    assert 'never-publish-this' not in raw

def test_failure_artifact_separates_primary_error_and_cleanup_facts(tmp_path: Path) -> None:
    driver = official
    audit = tmp_path / "audit"
    audit.mkdir()
    sample_reporting_diagnostics._write_failure(
        audit,
        sample_harness_state.SampleTestError("L5_RUN_RESULT_UNAVAILABLE"),
        sample_harness_state.HarnessState(
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
        sample_harness_lifecycle,
        "_wait_for",
        lambda *_args, **_kwargs: {
            "run": {"lifecycle": "FAILED"},
            "result_integrity": "INVALID",
        },
    )

    with pytest.raises(sample_harness_state.SampleTestError) as caught:
        driver._wait_for_published_result(object(), "run-public", "run-job-public")

    assert sample_reporting_diagnostics._failure_identity(caught.value) == (
        "L5_RUN_RESULT_UNAVAILABLE",
        "L5_RUN_RESULT_UNAVAILABLE: lifecycle=FAILED integrity=INVALID "
        "run_id=run-public run_job_id=run-job-public",
    )
