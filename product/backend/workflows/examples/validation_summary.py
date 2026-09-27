# 读取 sample-test 发布的净化验证汇总；不接触 private oracle、单 Case 答案或产品 Verdict。

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from product.backend.infra.runtime.paths import RuntimePaths


_SUMMARY_FILE = "latest-validation-summary.json"
_MAX_SUMMARY_BYTES = 64 * 1024


class PublishedCompetitionValidationSummary(BaseModel):
    """已通过 sample-test 外层验收并净化后的可展示计数。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"]
    generated_at_us: int = Field(ge=1)
    suite: Literal["validation", "competition"]
    status: Literal["accepted"]
    repetitions: Literal[1, 3]
    case_count: int = Field(ge=1)
    case_run_count: int = Field(ge=1)
    application_count: int = Field(ge=1)
    mode_count: int = Field(ge=1)
    state_count: int = Field(ge=1)
    full_exact_match_count: int = Field(ge=0)
    full_wrong_pass_vulnerable: int = Field(ge=0)
    full_wrong_pass_evidence_gap: int = Field(ge=0)
    http_exact_match_count: int = Field(ge=0)
    http_wrong_pass_vulnerable: int = Field(ge=0)
    http_wrong_pass_evidence_gap: int = Field(ge=0)
    http_wrong_pass_per_matrix: int = Field(ge=0)
    source_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    source_dirty: bool | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> PublishedCompetitionValidationSummary:
        if self.case_run_count != self.case_count * self.repetitions:
            raise ValueError("case_run_count 与 Case 数和重复次数不一致")
        if self.full_exact_match_count > self.case_run_count:
            raise ValueError("完整方法匹配数超过运行数")
        if self.http_exact_match_count > self.case_run_count:
            raise ValueError("HTTP-only 匹配数超过运行数")
        http_wrong_pass = (
            self.http_wrong_pass_vulnerable + self.http_wrong_pass_evidence_gap
        )
        if http_wrong_pass != self.http_wrong_pass_per_matrix * self.repetitions:
            raise ValueError("HTTP-only wrong PASS 与每轮矩阵计数不一致")
        return self


class CompetitionValidationSummaryView(BaseModel):
    """展示模式的可用性包装；缺失或损坏汇总不会阻断正式产品。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    unavailable_reason: str | None
    summary: PublishedCompetitionValidationSummary | None

    @model_validator(mode="after")
    def validate_availability(self) -> CompetitionValidationSummaryView:
        if self.available != (self.summary is not None):
            raise ValueError("可用状态与汇总正文不一致")
        if self.available == (self.unavailable_reason is not None):
            raise ValueError("可用状态与缺失原因不一致")
        return self


class CompetitionValidationSummaryQuery:
    """只读取稳定发布位置；不扫描历史审计目录挑选有利结果。"""

    def __init__(self, var_dir: Path) -> None:
        self._path = RuntimePaths(var_dir).competition_audit / _SUMMARY_FILE

    def get(self) -> CompetitionValidationSummaryView:
        if not self._path.is_file():
            return CompetitionValidationSummaryView(
                available=False,
                unavailable_reason="尚未发布可展示的验证汇总",
                summary=None,
            )
        try:
            if self._path.stat().st_size > _MAX_SUMMARY_BYTES:
                raise ValueError("summary too large")
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            summary = PublishedCompetitionValidationSummary.model_validate(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError):
            return CompetitionValidationSummaryView(
                available=False,
                unavailable_reason="公开验证汇总不可读取，请重新运行正式验证",
                summary=None,
            )
        return CompetitionValidationSummaryView(
            available=True,
            unavailable_reason=None,
            summary=summary,
        )


__all__ = [
    "CompetitionValidationSummaryQuery",
    "CompetitionValidationSummaryView",
    "PublishedCompetitionValidationSummary",
]
