# 验证当前构造器和历史夹具的分界，捕获默认字段新增及无效 wire 混入。
import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from product.backend.infra.storage import JobRecord
from tests.contracts.current import JOB_TARGET_FIELDS
from tests.fixtures.runtime.current_jobs import current_job, invalid_job_payload


@pytest.mark.parametrize("target,operation", [("run_id", "CHECK"), ("recording_id", "RECORDING"),
                                           ("runtime_load_id", "RUNTIME_LOAD"), ("preflight_id", "PROOF_PREFLIGHT")])
def test_current_jobs_are_valid_and_carry_all_target_fields(target, operation):
    job = current_job(target=target, operation_type=operation)
    assert all(hasattr(job, name) for name in JOB_TARGET_FIELDS)
    assert sum(getattr(job, name) is not None for name in JOB_TARGET_FIELDS) == 1


def test_invalid_wire_is_rejected_instead_of_bypassing_validation():
    with pytest.raises(ValidationError):
        JobRecord.model_validate(invalid_job_payload(run_id=None))
    with pytest.raises(ValidationError):
        current_job(target="preflight_id", operation_type="CHECK")


def test_frozen_history_does_not_import_current_application_or_builders():
    path = Path(__file__).resolve().parents[1] / "fixtures/preparation/legacy_recording.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(name and (name.startswith("product.") or name.startswith("tests.fixtures.preparation.action_preparation")) for name in imports)
