# =============================================================================
# 受控应用理解分析器
#
# 定位
#   用户显式授权之后、角色和业务动作进入人工确认之前的离线确定性分析边界
#
# 职责
#   有界读取源码｜复用 OpenAPI/FastAPI 静态规则｜生成稳定候选与结构证据
#
# 边界
#   不 import、eval、exec 或启动用户代码，不调用网络/子进程，不读取秘密和生成目录，也不保存源码正文。
#
# 调用链
#   ApplicationUnderstandingService → ApplicationUnderstandingAnalyzer → Core candidates
# =============================================================================

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
import yaml
from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import (
    ActionCandidate,
    ActionRiskHint,
    CandidateConfidence,
    CandidateEvidence,
    RoleCandidate,
    candidate_id,
    canonical_role_key,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.http_routes import HTTP_METHODS, safe_route_path
from product.backend.core.source_changes import SourceFileFingerprint
from product.backend.workflows.onboarding.discovery import (
    canonical_folder,
    is_reparse_point,
)


_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".next",
        ".nuxt",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "var",
        "venv",
    }
)
_SOURCE_SUFFIXES = frozenset({".py", ".js", ".jsx", ".ts", ".tsx"})
_OPENAPI_NAMES = frozenset(
    {
        "openapi.json",
        "openapi.yaml",
        "openapi.yml",
        "swagger.json",
        "swagger.yaml",
        "swagger.yml",
    }
)
_SENSITIVE_FILE = re.compile(
    r"(?:^\.env(?:\.|$)|credential|secret|private[_-]?key|\.pem$|\.key$)",
    re.IGNORECASE,
)
_ROLE_CONTEXT = re.compile(
    r"(?<![A-Za-z0-9])(?:role|roles|group|groups|access[_-]?levels?)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_ROLE_CLASS = re.compile(r"(?:role|group|access_?level)", re.IGNORECASE)
_ROLE_GUARD = re.compile(
    r"^(?:require|has|check|ensure|allow)_(?:role|group|access_level)$|"
    r"^(?:role|group|access_level)_guard$",
    re.IGNORECASE,
)
_JS_ROLE_STRUCTURE = re.compile(
    r"\b(?:const|let|var)\s+[A-Za-z0-9_$]*(?:role|group|access_?level)s?\b\s*=|"
    r"\b(?:require|has|check|ensure|allow)(?:Role|Group|AccessLevel)\s*\(",
    re.IGNORECASE,
)
_JS_STRING = re.compile(r"(['\"])([A-Za-z][A-Za-z0-9_.:-]{0,63})\1")
_JS_ROUTE = re.compile(
    r"\b(?:app|router)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*(['\"])(/[^'\"]*)\2",
    re.IGNORECASE,
)
_JS_REQUEST = re.compile(
    r"\b(?:axios|client|api|request)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*(['\"])(/[^'\"]*)\2",
    re.IGNORECASE,
)
_FETCH_REQUEST = re.compile(r"\bfetch\s*\(\s*(['\"])(/[^'\"]*)\1")
_CONFIDENCE_RANK = {
    CandidateConfidence.LOW: 0,
    CandidateConfidence.MEDIUM: 1,
    CandidateConfidence.HIGH: 2,
}
_METHOD_LABEL = {
    "GET": "查看",
    "POST": "创建或执行",
    "PUT": "替换",
    "PATCH": "修改",
    "DELETE": "删除",
}


class AnalysisModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class SourceAnalysisLimits(AnalysisModel):
    max_depth: int = Field(default=8, ge=0, le=12)
    max_entries: int = Field(default=4096, ge=1, le=8192)
    max_files: int = Field(default=256, ge=1, le=512)
    max_file_bytes: int = Field(default=524_288, ge=1, le=1_048_576)
    max_total_bytes: int = Field(default=8_388_608, ge=1, le=16_777_216)
    max_roles: int = Field(default=256, ge=1, le=256)
    max_actions: int = Field(default=512, ge=1, le=512)


class ApplicationAnalysisResult(AnalysisModel):
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: tuple[SourceFileFingerprint, ...] = Field(default=(), max_length=512)
    role_candidates: tuple[RoleCandidate, ...] = Field(default=(), max_length=256)
    action_candidates: tuple[ActionCandidate, ...] = Field(default=(), max_length=512)
    files_read: int = Field(ge=0, le=512)
    total_bytes: int = Field(ge=0, le=16_777_216)


class _Finding:
    def __init__(
        self,
        *,
        display_name: str,
        confidence: CandidateConfidence,
        risk_hint: ActionRiskHint | None = None,
    ) -> None:
        self.display_name = display_name
        self.confidence = confidence
        self.risk_hint = risk_hint
        self.evidence: list[CandidateEvidence] = []
        self.detectors: set[str] = set()
