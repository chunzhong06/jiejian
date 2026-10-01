# 验证当前 Sample 修复切换先核原题引用，只登记真实变化而不创建 Run。
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from product.backend.core.checks.repair import CurrentRepairReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.examples.environment import OfficialSampleExperience, OfficialScenarioVersion, _Experience


def test_fixed_version_validates_original_reference_before_mechanical_switch(tmp_path):
    calls = []
    runtime = SimpleNamespace(experience_id="exp_" + "5" * 32, origin="http://127.0.0.1:1", launch_manifest=SimpleNamespace(source_fingerprint="a" * 64))
    manager = SimpleNamespace(active=runtime, installation=SimpleNamespace(available=True, display_name="协作空间", reason=None),
        switch_behavior=lambda *args, **kwargs: calls.append(("switch", kwargs)) or runtime)
    reference = CurrentRepairReference(source_run_id="run_" + "1" * 32, source_case_id="case_" + "2" * 32, repair_fingerprint="3" * 64)
    def resolve(project, supplied):
        assert project == "sample-repair" and supplied == reference
        calls.append(("resolve", supplied))
    def submit(project, task_id, **values):
        calls.append(("submit", values))
        return SimpleNamespace(change_id="chg_" + "4" * 32)
    development = SimpleNamespace(receipt=lambda *_: None, active=lambda _: None,
        create=lambda *args, **kwargs: calls.append(("create", kwargs)) or SimpleNamespace(task_id="task", task_version=1, context_id="ctx"), deliver=submit)
    experience = OfficialSampleExperience(manager, understanding=SimpleNamespace(inspect_source_fingerprint=lambda _: "a" * 64), boundaries=None, identities=None, secret_store=None,
        registry=None, installer=None, bindings=None, preparation=None, changes=SimpleNamespace(submit=submit),
        repairs=SimpleNamespace(resolve=resolve), uow_factory=lambda: nullcontext(SimpleNamespace(environment_operations=SimpleNamespace(list=lambda limit: ([], False)), jobs=SimpleNamespace(list_for_project=lambda _: ()))),
        var_dir=tmp_path, archive_project=None, development=development)
    experience._recovery = SimpleNamespace(read=lambda: (None, None, None, None))
    experience._current = _Experience(runtime=runtime, project_id="sample-repair", scenario_prepared=True)
    with pytest.raises(JiejianError):
        experience.switch_version(version=OfficialScenarioVersion.FIXED)
    assert calls == []
    view = experience.switch_version(version=OfficialScenarioVersion.FIXED, repair_reference=reference)
    assert [name for name, _ in calls] == ["resolve", "create", "switch", "submit"]
    assert calls[2][1]["authorization_order"] == "AUTHORIZE_BEFORE_ENQUEUE"
    assert calls[3][1]["repair_reference"] == reference
    assert calls[3][1]["submitted_by"] == "预设演示 · 本机用户"
    assert view.repair_change_id == "chg_" + "4" * 32
    assert not view.scenario_prepared and view.pending_tasks == ("PREPARE_CURRENT_MATERIALS",)
