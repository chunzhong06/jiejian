# 历史契约快照结果模型。持久化解析编排位于同目录的 service。

from enum import StrEnum

from pydantic import Field

from .models import AnalysisModel
from ..models import ContractVersion
from ...domain.identifiers import LONG_SLUG_ID_PATTERN, PROJECT_ID_PATTERN, RUN_ID_PATTERN
from ...verification.models import SecurityContract


class ContractHistorySource(StrEnum):
    GOVERNED_VERSION = "GOVERNED_VERSION"
    EXECUTION_REQUEST = "EXECUTION_REQUEST"


class ContractHistoryResolution(AnalysisModel):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    contract_id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    contract_version: int = Field(ge=1)
    source: ContractHistorySource
    contract: SecurityContract
    execution_job_id: str | None = None
    governed_version: ContractVersion | None = None
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

__all__ = ["ContractHistoryResolution", "ContractHistorySource"]
