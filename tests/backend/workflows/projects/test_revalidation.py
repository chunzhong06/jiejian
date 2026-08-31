# 验证项目重验状态严格由最新 SourceChange inspection、准备度与可信结果按固定顺序组合。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.workflows.projects.revalidation import (
    ProjectRevalidationService,
    ProjectRevalidationStatus,
)
from product.backend.workflows.source_changes import (
    SourceRevalidationInspection,
    SourceRevalidationInspectionStatus,
)


_CHANGE_ID = "chg_" + "1" * 32


class _SourceChanges:
    def __init__(self, status: SourceRevalidationInspectionStatus | None) -> None:
        self.status = status

    def latest(self, project_id: str):
        assert project_id == "app_demo"
        if self.status is None:
            return None
        return SimpleNamespace(change_id=_CHANGE_ID), object(), object()

    def inspect_revalidation(self, project_id: str, change_id: str):
        assert project_id == "app_demo"
        assert change_id == _CHANGE_ID
        assert self.status is not None
        return SourceRevalidationInspection(
            project_id=project_id,
            change_id=change_id,
            status=self.status,
            reason_codes=() if self.status is SourceRevalidationInspectionStatus.READY else (self.status.value,),
            impact_fingerprint="2" * 64,
            source_fingerprint="3" * 64,
            required_intent_ids=("pin_" + "4" * 32,),
        )


@pytest.mark.parametrize(
    ("inspection", "ready", "verified_change_id", "expected"),
    (
        (None, False, None, ProjectRevalidationStatus.NO_CHANGE),
        (
            SourceRevalidationInspectionStatus.MAPPING_REVIEW_REQUIRED,
            True,
            None,
            ProjectRevalidationStatus.REVIEW_REQUIRED,
        ),
        (
            SourceRevalidationInspectionStatus.NO_BASELINE,
            True,
            None,
            ProjectRevalidationStatus.STALE,
        ),
        (
            SourceRevalidationInspectionStatus.SOURCE_STALE,
            True,
            None,
            ProjectRevalidationStatus.STALE,
        ),
        (
            SourceRevalidationInspectionStatus.POLICY_STALE,
            True,
            None,
            ProjectRevalidationStatus.STALE,
        ),
        (
            SourceRevalidationInspectionStatus.READY,
            False,
            None,
            ProjectRevalidationStatus.PREPARATION_REQUIRED,
        ),
        (
            SourceRevalidationInspectionStatus.READY,
            True,
            None,
            ProjectRevalidationStatus.READY,
        ),
        (
            SourceRevalidationInspectionStatus.READY,
            False,
            _CHANGE_ID,
            ProjectRevalidationStatus.VERIFIED,
        ),
    ),
)
def test_revalidation_status_order(
    inspection: SourceRevalidationInspectionStatus | None,
    ready: bool,
    verified_change_id: str | None,
    expected: ProjectRevalidationStatus,
) -> None:
    service = ProjectRevalidationService(_SourceChanges(inspection))

    view = service.evaluate(
        "app_demo",
        preparation=SimpleNamespace(ready=ready),
        verified_run_id="run_1" if verified_change_id is not None else None,
        verified_change_id=verified_change_id,
    )

    assert view.status is expected
    if inspection is SourceRevalidationInspectionStatus.READY:
        assert view.required_intent_count == 1

