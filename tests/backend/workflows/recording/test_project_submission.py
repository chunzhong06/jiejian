# 项目式录制提交测试：验证共享入口在访问项目事实前收紧有界输入。

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.recording.project_submission import ProjectRecordingService


def test_project_recording_rejects_unbounded_duration_before_side_effects() -> None:
    service = ProjectRecordingService(None, None, None, None)

    with pytest.raises(JiejianError) as captured:
        service.submit(
            "project_current",
            action_candidate_id="action_current",
            test_identity_id="tid_current",
            duration_seconds=0,
            idempotency_key="recording-current",
        )

    assert captured.value.code == ErrorCode.INPUT_INVALID.value
