# 验证 OpenAPI 检测器只从明确结构提取业务动作候选。

from __future__ import annotations

import json
from pathlib import Path

from product.backend.core.application_understanding import CandidateConfidence
from product.backend.workflows.application_understanding.analysis.analyzer import (
    ApplicationUnderstandingAnalyzer,
)


def test_openapi_paths_produce_stable_action_candidates(tmp_path: Path) -> None:
    (tmp_path / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "x-roles": ["owner", "member"],
                "paths": {
                    "/documents/{document_id}": {
                        "patch": {
                            "operationId": "updateDocument",
                            "summary": "修改文档",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = ApplicationUnderstandingAnalyzer().analyze("project-a", tmp_path)
    actions = {item.canonical_key: item for item in result.action_candidates}
    roles = {item.canonical_key: item for item in result.role_candidates}

    assert set(roles) == {"member", "owner"}
    assert all(item.confidence is CandidateConfidence.HIGH for item in roles.values())
    assert actions["PATCH /documents/{document_id}"].confidence is CandidateConfidence.MEDIUM
    assert actions["PATCH /documents/{document_id}"].display_name == "修改文档"


def test_official_sample_exposes_explicit_permission_groups() -> None:
    root = Path(__file__).resolve().parents[5] / "samples" / "web"

    result = ApplicationUnderstandingAnalyzer().analyze("sample-project", root)

    assert {item.canonical_key for item in result.role_candidates} == {
        "attacker",
        "owner",
        "peer",
    }
    assert all(
        item.evidence[0].detector == "openapi-role-extension"
        for item in result.role_candidates
    )
