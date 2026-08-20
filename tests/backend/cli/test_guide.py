from __future__ import annotations

import pytest

from product.backend.core.lifecycle import RunVerdict
from product.backend.workflows.context import ApplicationCore
from product.protocols import RunnerResultType


@pytest.mark.process
def test_guide_demo_uses_the_real_worker_runner_and_published_result(tmp_path) -> None:
    application = ApplicationCore(tmp_path / "var")
    try:
        status, result = application.run_demo("vulnerable")

        assert status.demo_data is True
        assert result.result_type is RunnerResultType.SUCCESS
        assert result.verdict is RunVerdict.BLOCK
        assert any(item.verdict.value == "VULNERABLE" for item in result.evidence)
        assert application.demo.status().status == "stopped"
    finally:
        application.close()
