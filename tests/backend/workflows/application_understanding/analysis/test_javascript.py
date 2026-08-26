# 验证 JavaScript 检测器只从受限调用和字面量提取动作候选。

from __future__ import annotations

from pathlib import Path

from product.backend.core.application_understanding import CandidateConfidence
from product.backend.workflows.application_understanding.analysis.analyzer import (
    ApplicationUnderstandingAnalyzer,
)


def test_javascript_calls_produce_bounded_action_candidates(tmp_path: Path) -> None:
    (tmp_path / "client.ts").write_text(
        "const roles = ['member', 'guest']\n"
        "api.patch('/documents/{document_id}', payload)\n"
        "axios.delete('/members/{id}')\n",
        encoding="utf-8",
    )

    result = ApplicationUnderstandingAnalyzer().analyze("project-a", tmp_path)
    roles = {item.canonical_key: item for item in result.role_candidates}
    actions = {item.canonical_key: item for item in result.action_candidates}

    assert roles["member"].confidence is CandidateConfidence.LOW
    assert roles["guest"].confidence is CandidateConfidence.LOW
    assert "DELETE /members/{id}" in actions
