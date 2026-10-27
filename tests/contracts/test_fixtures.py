# 验证当前任务构造器与非法跨边界输入。
import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from product.backend.infrastructure.storage.execution.jobs import JobRecord
from tests.support.contracts import JOB_TARGET_FIELDS
from tests.support.builders.runtime.current_jobs import current_job, invalid_job_payload


@pytest.mark.parametrize("target,operation", [("run_id", "CHECK"), ("recording_id", "RECORDING"),
                                           ("runtime_load_id", "RUNTIME_LOAD"), ("preflight_id", "PROOF_PREFLIGHT"), ("reference_capture_id", "REFERENCE_CAPTURE")])
def test_current_jobs_are_valid_and_carry_all_target_fields(target, operation):
    job = current_job(target=target, operation_type=operation)
    assert all(hasattr(job, name) for name in JOB_TARGET_FIELDS)
    assert sum(getattr(job, name) is not None for name in JOB_TARGET_FIELDS) == 1


def test_invalid_wire_is_rejected_instead_of_bypassing_validation():
    with pytest.raises(ValidationError):
        JobRecord.model_validate(invalid_job_payload(run_id=None))
    with pytest.raises(ValidationError):
        current_job(target="preflight_id", operation_type="CHECK")


pytestmark = [pytest.mark.level2]
