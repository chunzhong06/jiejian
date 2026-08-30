# 验证代码变化只读 API 只返回有界相对路径摘要，不泄露正文或指纹。

from pathlib import Path

import pytest

from product.backend.workflows.source_changes import SourceChangeView
from tests.fixtures.control_plane import TestClient, create_app


pytestmark = pytest.mark.database


def test_source_change_read_api_returns_bounded_latest_view(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    project_id = "change-api-project"
    view = SourceChangeView(
        change_id="chg_" + "1" * 32,
        project_id=project_id,
        reason="完成权限实现修复",
        created_at_us=10,
        status="COMPARABLE",
        complete=True,
        actual_changed_path_count=2,
        added_count=1,
        modified_count=1,
        removed_count=0,
        claimed_paths=("product/agent.py",),
        added_paths=("product/new.py",),
        modified_paths=("product/agent.py",),
        directly_affected_count=1,
        mapping_review_required_count=0,
        no_direct_evidence_count=1,
        summary="发现 1 条权限要求与本次变化直接相关。",
    )
    app.state.context.source_changes.latest_view = lambda selected: (
        view if selected == project_id else None
    )
    app.state.context.source_changes.view = lambda change_id: view

    with TestClient(app) as client:
        latest = client.get(f"/api/projects/{project_id}/source-changes/latest")
        shown = client.get(
            f"/api/projects/{project_id}/source-changes/{view.change_id}"
        )

    assert latest.status_code == shown.status_code == 200
    assert latest.json()["data"] == shown.json()["data"]
    assert latest.json()["data"]["actual_changed_path_count"] == 2
    assert latest.json()["data"]["claimed_paths"] == ["product/agent.py"]
    assert latest.json()["data"]["added_paths"] == ["product/new.py"]
    assert latest.json()["data"]["modified_paths"] == ["product/agent.py"]
    encoded = latest.text
    assert "source_fingerprint" not in encoded
    assert "impact_fingerprint" not in encoded
    assert "source body" not in encoded
    assert "content_sha256" not in encoded
