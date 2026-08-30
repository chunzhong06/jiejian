# 验证官方 Sample 的“验证修复”只编排 RepairContract、代码变化与既有检查链。

from __future__ import annotations

from types import SimpleNamespace

from product.backend.core.repair import RepairContractReference
from product.backend.workflows.official_sample import (
    OfficialExperienceMode,
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
        self.switches: list[tuple[str, str]] = []

    def switch_behavior(self, _experience_id, *, authorization_order, blob_observation):
        self.switches.append((authorization_order, blob_observation))


class _SourceChanges:
    def __init__(self) -> None:
        self.calls = []

    def submit(self, project_id, **values):
        self.calls.append((project_id, values))
        return SimpleNamespace(change_id="chg_" + "4" * 32), None, None


def test_verify_fixed_creates_authoritative_repair_change_before_existing_check() -> None:
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
        repair_contracts=repairs,
        source_changes=source_changes,
    )
    experience._current = _Experience(
        runtime=runtime,
        mode=OfficialExperienceMode.GUIDED,
        project_id=PROJECT_ID,
    )

    view = experience.switch_behavior(
        authorization_order="AUTHORIZE_BEFORE_ENQUEUE",
        blob_observation="AVAILABLE",
        verification_run_id=RUN_ID,
    )

    assert manager.switches == [("AUTHORIZE_BEFORE_ENQUEUE", "AVAILABLE")]
    assert source_changes.calls == [
        (
            PROJECT_ID,
            {
                "reason": "按已发布权限问题验证修复后的官方示例行为",
                "submitted_by": "Official Sample",
                "repair_reference": REFERENCE,
            },
        )
    ]
    assert view.repair_change_id == "chg_" + "4" * 32
