# 验证官方 Sample 切换修复版只编排 RepairContract 与源码变化，不替代后续检查。

from __future__ import annotations

from types import SimpleNamespace

from product.backend.core.repair import RepairContractReference
from product.backend.workflows.official_sample import (
    OfficialScenarioVersion,
    OfficialSampleExperience,
    _Experience,
)


PROJECT_ID = "sample-repair"
RUN_ID = "run_" + "1" * 32
REFERENCE = RepairContractReference(
    source_run_id=RUN_ID,
    source_finding_id="finding_" + "2" * 32,
    repair_fingerprint="3" * 64,
)


class _Manager:
    def __init__(self, runtime) -> None:
        self.active = runtime
        self.installation = SimpleNamespace(
            available=True,
            display_name="协作空间",
            reason=None,
        )
        self.switches: list[tuple[str, str, str]] = []

    def switch_behavior(
        self,
        _experience_id,
        *,
        authorization_order,
        owner_observation,
        blob_observation,
    ):
        self.switches.append(
            (authorization_order, owner_observation, blob_observation)
        )


class _SourceChanges:
    def __init__(self) -> None:
        self.calls = []

    def submit(self, project_id, **values):
        self.calls.append((project_id, values))
        return SimpleNamespace(change_id="chg_" + "4" * 32), None, None


def test_fixed_version_creates_authoritative_repair_change_without_running_check() -> None:
    runtime = SimpleNamespace(experience_id="exp_" + "5" * 32, origin="http://127.0.0.1:1")
    manager = _Manager(runtime)
    source_changes = _SourceChanges()
    repairs = SimpleNamespace(
        for_run=lambda run_id: SimpleNamespace(
            project_id=PROJECT_ID,
            reference=REFERENCE,
        )
    )
    status = SimpleNamespace(
        readiness=SimpleNamespace(active_tasks=()),
        latest_result=SimpleNamespace(run_id=RUN_ID),
    )
    experience = OfficialSampleExperience(
        manager,
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(get=lambda _project_id: status),
        scenario_installer=SimpleNamespace(),
        action_safety_setup=SimpleNamespace(),
        permission_intents=SimpleNamespace(),
        project_preparation=SimpleNamespace(status=lambda _project_id: SimpleNamespace(ready=True)),
        repair_contracts=repairs,
        source_changes=source_changes,
    )
    experience._current = _Experience(
        runtime=runtime,
        project_id=PROJECT_ID,
        scenario_prepared=True,
    )

    view = experience.switch_version(
        version=OfficialScenarioVersion.FIXED,
        source_run_id=RUN_ID,
    )

    assert manager.switches == [
        ("AUTHORIZE_BEFORE_ENQUEUE", "AVAILABLE", "AVAILABLE")
    ]
    assert source_changes.calls == [
        (
            PROJECT_ID,
            {
                "reason": "Codex 按界鉴修复合同把权限判断移动到后台任务创建之前",
                "submitted_by": "MCP · Codex",
                "repair_reference": REFERENCE,
            },
        )
    ]
    assert view.repair_change_id == "chg_" + "4" * 32
    assert view.scenario_version is OfficialScenarioVersion.FIXED
