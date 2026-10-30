# 源码分析的读取预算与候选结果，不保存被读取的源码正文。
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from product.backend.domain.applications.models import ActionCandidate, RoleCandidate
from product.backend.domain.changes.models import SourceFileFingerprint


class AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class SourceAnalysisLimits(AnalysisModel):
    max_depth: int = Field(default=8, ge=0, le=12)
    max_entries: int = Field(default=4096, ge=1, le=8192)
    max_files: int = Field(default=256, ge=1, le=512)
    max_file_bytes: int = Field(default=524288, ge=1, le=1048576)
    max_total_bytes: int = Field(default=8388608, ge=1, le=16777216)
    max_roles: int = Field(default=256, ge=1, le=256)
    max_actions: int = Field(default=512, ge=1, le=512)


class ApplicationAnalysisResult(AnalysisModel):
    source_fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    files: tuple[SourceFileFingerprint, ...] = Field(default=(), max_length=512)
    role_candidates: tuple[RoleCandidate, ...] = Field(default=(), max_length=256)
    action_candidates: tuple[ActionCandidate, ...] = Field(default=(), max_length=512)
    files_read: int = Field(ge=0, le=512)
    total_bytes: int = Field(ge=0, le=16777216)
