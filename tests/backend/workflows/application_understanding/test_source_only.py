# 验证离线源码整理保留授权与修订边界，且不探测地址或执行目标源码。
from pathlib import Path

import pytest

from product.backend.composition import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.application_understanding.endpoints import TargetEndpointDiscovery


pytestmark = pytest.mark.database


def test_source_only_analysis_never_probes_and_recovers_without_endpoint(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text(
        "raise RuntimeError('source must never execute')\nroles = ['owner']\n"
        "@app.get('/documents')\ndef list_documents(): pass\n", encoding="utf-8",
    )

    def reject_probe(*args, **kwargs):
        pytest.fail("离线整理不应发起地址探测")

    var_dir = tmp_path / "var"
    core = ApplicationCore(var_dir, environ={}, endpoint_discovery=TargetEndpointDiscovery(probe=reject_probe))
    try:
        connected = core.application_understanding.connect(source)
        project_id = connected.project.project_id
        assert core.workspace.get(project_id).primary_task.task_kind == "AUTHORIZE_SOURCE_ANALYSIS"
        with pytest.raises(JiejianError) as unauthorized:
            core.application_understanding.analyze_source(project_id, revision=0)
        assert unauthorized.value.code == ErrorCode.APPLICATION_ANALYSIS_NOT_AUTHORIZED.value
        authorized = core.application_understanding.authorize_source_analysis(project_id, revision=0)
        with pytest.raises(JiejianError):
            core.application_understanding.analyze_source(project_id, revision=0)
        analyzed = core.application_understanding.analyze_source(project_id, revision=authorized.revision)
        assert analyzed.confirmed_endpoint is None
        assert analyzed.role_candidates[0].canonical_key == "owner"
        assert analyzed.action_candidates[0].canonical_key == "GET /documents"
        workspace = core.workspace.get(project_id)
        assert workspace.connection.endpoint_status == "NEEDS_CONFIRMATION"
        assert workspace.primary_task.task_kind == "REVIEW_APPLICATION_CANDIDATES"
    finally:
        core.close()

    restarted = ApplicationCore(var_dir, environ={}, endpoint_discovery=TargetEndpointDiscovery(probe=reject_probe))
    try:
        recovered = restarted.application_understanding.get(project_id)
        assert recovered.source_fingerprint == analyzed.source_fingerprint
        assert recovered.confirmed_endpoint is None
        assert restarted.workspace.get(project_id).primary_task.task_kind == "REVIEW_APPLICATION_CANDIDATES"
    finally:
        restarted.close()
