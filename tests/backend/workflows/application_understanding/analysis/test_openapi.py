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


def test_openapi_role_extension_is_exact_and_does_not_read_official_samples(
    tmp_path: Path,
) -> None:
    (tmp_path / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "x-roles": ["member", "manager"],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    result = ApplicationUnderstandingAnalyzer().analyze("project-a", tmp_path)

    roles = {item.canonical_key: item for item in result.role_candidates}
    assert set(roles) == {"member", "manager"}
    assert all(
        roles[key].evidence[0].detector == "openapi-role-extension"
        for key in ("member", "manager")
    )


def test_openapi_role_labels_merge_other_sources_by_canonical_key(
    tmp_path: Path,
) -> None:
    (tmp_path / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "x-roles": {
                    "PROJECT_OWNER": "项目负责人",
                    "MEMBER": "普通成员",
                },
                "paths": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "roles.py").write_text(
        "from enum import StrEnum\n"
        "class AccountRole(StrEnum):\n"
        "    OWNER = 'PROJECT_OWNER'\n"
        "    MEMBER = 'MEMBER'\n",
        encoding="utf-8",
    )

    result = ApplicationUnderstandingAnalyzer().analyze("project-a", tmp_path)

    roles = {item.canonical_key: item for item in result.role_candidates}
    assert {key: item.display_name for key, item in roles.items()} == {
        "member": "普通成员",
        "project_owner": "项目负责人",
    }
    assert {
        evidence.detector
        for evidence in roles["project_owner"].evidence
    } == {"openapi-role-extension", "python-role-enum"}
    assert roles["project_owner"].confidence is CandidateConfidence.HIGH
