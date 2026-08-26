# 验证应用理解分析编排的受限读取、预算与跳过规则。

from __future__ import annotations
import json
from pathlib import Path
import pytest
from product.backend.core.application_understanding import (
    CandidateConfidence,
    CandidateDecision,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.application_understanding.analysis import analyzer as analyzer_module
from product.backend.workflows.application_understanding.analysis.analyzer import (
    ApplicationUnderstandingAnalyzer,
    SourceAnalysisLimits,
)


def _write_understood_application(root: Path) -> None:
    (root / "app.py").write_text(
        """
from enum import StrEnum
import socket
import subprocess

class AccountRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"

@app.patch("/documents/{document_id}")
def update_document(document_id: str):
    subprocess.run(["never-executed"])
    socket.create_connection(("example.com", 80))
""".strip(),
        encoding="utf-8",
    )
    (root / "client.ts").write_text(
        "const roles = ['member', 'guest']\n"
        "api.patch('/documents/{document_id}', payload)\n"
        "axios.delete('/members/{id}')\n",
        encoding="utf-8",
    )
    (root / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "components": {
                    "securitySchemes": {
                        "oauth": {
                            "type": "oauth2",
                            "flows": {
                                "clientCredentials": {
                                    "tokenUrl": "/token",
                                    "scopes": {"admin": "管理范围"},
                                }
                            },
                        }
                    }
                },
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


def test_analyzer_builds_stable_candidates_without_executing_source(
    tmp_path: Path,
) -> None:
    _write_understood_application(tmp_path)

    analyzer = ApplicationUnderstandingAnalyzer()
    first = analyzer.analyze("project-a", tmp_path)
    second = analyzer.analyze("project-a", tmp_path)

    assert first == second
    assert [item.candidate_id for item in first.role_candidates] == [
        item.candidate_id for item in second.role_candidates
    ]
    roles = {item.canonical_key: item for item in first.role_candidates}
    assert roles["admin"].confidence is CandidateConfidence.HIGH
    assert roles["member"].confidence is CandidateConfidence.HIGH
    assert roles["guest"].confidence is CandidateConfidence.LOW
    assert roles["guest"].decision is CandidateDecision.PROPOSED

    actions = {item.canonical_key: item for item in first.action_candidates}
    assert actions["PATCH /documents/{document_id}"].confidence is CandidateConfidence.HIGH
    assert actions["PATCH /documents/{document_id}"].display_name == "修改文档"
    assert "DELETE /members/{id}" in actions
    for candidate in (*first.role_candidates, *first.action_candidates):
        assert candidate.decision is CandidateDecision.PROPOSED
        for evidence in candidate.evidence:
            assert not Path(evidence.relative_path).is_absolute()
            assert evidence.line_start >= 1
            assert len(evidence.content_sha256) == 64
            assert not hasattr(evidence, "source_text")


def test_analyzer_skips_sensitive_generated_deep_and_reparse_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "visible.py").write_text("roles = ['visible']", encoding="utf-8")
    (tmp_path / "secret_roles.py").write_text("roles = ['secret-admin']", encoding="utf-8")
    generated = tmp_path / "node_modules"
    generated.mkdir()
    (generated / "roles.py").write_text("roles = ['generated-admin']", encoding="utf-8")
    deep = tmp_path / "deep"
    deep.mkdir()
    (deep / "roles.py").write_text("roles = ['deep-admin']", encoding="utf-8")
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "roles.py").write_text("roles = ['linked-admin']", encoding="utf-8")

    original = analyzer_module.is_reparse_point
    monkeypatch.setattr(
        analyzer_module,
        "is_reparse_point",
        lambda path: path == linked or original(path),
    )
    result = ApplicationUnderstandingAnalyzer(
        limits=SourceAnalysisLimits(max_depth=0)
    ).analyze("project-a", tmp_path)

    assert [item.canonical_key for item in result.role_candidates] == ["visible"]
    assert result.files_read == 1

@pytest.mark.parametrize(
    ("limits", "files"),
    [
        (SourceAnalysisLimits(max_files=1), {"a.py": "roles=['a']", "b.py": "roles=['b']"}),
        (SourceAnalysisLimits(max_file_bytes=8), {"a.py": "roles=['too-large']"}),
        (SourceAnalysisLimits(max_total_bytes=12), {"a.py": "roles=['a']", "b.py": "roles=['b']"}),
    ],
)
def test_analyzer_enforces_file_and_byte_budgets(
    tmp_path: Path,
    limits: SourceAnalysisLimits,
    files: dict[str, str],
) -> None:
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    with pytest.raises(JiejianError) as raised:
        ApplicationUnderstandingAnalyzer(limits=limits).analyze("project-a", tmp_path)

    assert raised.value.code == ErrorCode.APPLICATION_ANALYSIS_BUDGET.value
