# 验证当前 Sample 修复切换先核原题引用，只登记真实变化而不创建 Run。
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from product.backend.core.check_repair import CurrentRepairReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.official_sample import OfficialSampleExperience, OfficialScenarioVersion, _Experience


def test_fixed_version_validates_original_reference_before_mechanical_switch(tmp_path):
    calls = []
    runtime = SimpleNamespace(experience_id="exp_" + "5" * 32, origin="http://127.0.0.1:1")
    manager = SimpleNamespace(active=runtime, installation=SimpleNamespace(available=True, display_name="协作空间", reason=None),
        switch_behavior=lambda *args, **kwargs: calls.append(("switch", kwargs)))
    reference = CurrentRepairReference(source_run_id="run_" + "1" * 32, source_case_id="case_" + "2" * 32, repair_fingerprint="3" * 64)
    def resolve(project, supplied):
        assert project == "sample-repair" and supplied == reference
        calls.append(("resolve", supplied))
    def submit(project, **values):
        calls.append(("submit", values))
        return SimpleNamespace(manifest=SimpleNamespace(change_id="chg_" + "4" * 32))
    experience = OfficialSampleExperience(manager, understanding=None, boundaries=None, identities=None, secret_store=None,
        registry=None, installer=None, bindings=None, preparation=None, changes=SimpleNamespace(submit=submit),
        repairs=SimpleNamespace(resolve=resolve), uow_factory=lambda: nullcontext(SimpleNamespace(jobs=SimpleNamespace(list_for_project=lambda _: ()))),
        var_dir=tmp_path, archive_project=None)
    experience._current = _Experience(runtime=runtime, project_id="sample-repair", scenario_prepared=True)
    with pytest.raises(JiejianError):
        experience.switch_version(version=OfficialScenarioVersion.FIXED)
    assert calls == []
    view = experience.switch_version(version=OfficialScenarioVersion.FIXED, repair_reference=reference)
    assert [name for name, _ in calls] == ["resolve", "switch", "submit"]
    assert calls[1][1]["authorization_order"] == "AUTHORIZE_BEFORE_ENQUEUE"
    assert calls[2][1]["repair_reference"] == reference
    assert calls[2][1]["submitted_by"] == "LOCAL_GUI"
    assert view.repair_change_id == "chg_" + "4" * 32
    assert not view.scenario_prepared and view.pending_tasks == ("PREPARE_CURRENT_MATERIALS",)
