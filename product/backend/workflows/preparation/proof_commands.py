# GUI与MCP共用的有限准备命令；GUI确认与Agent候选分开，不接受任意请求或可靠性开关。
from typing import Literal
from pydantic import Field
from product.protocols.runtime_identity import RuntimeModel
from product.protocols.proof_sources import AnyProofSourceConfig, SourceId, PreflightId, ScopeId, OperationId


class ProofOperation(RuntimeModel):
    operation_id: OperationId
    basis_id: str = Field(pattern=r'^pb_[0-9a-f]{64}$')


class SaveProofSource(ProofOperation):
    source_id: SourceId | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    config: AnyProofSourceConfig


class StartProofPreflight(ProofOperation):
    source_id: SourceId
    revision: int = Field(ge=1)


class GrantProofScope(StartProofPreflight):
    confirmed: Literal[True]


class AdoptProofSource(StartProofPreflight):
    preflight_id: PreflightId
    confirmed: Literal[True]


class CancelProofPreflight(RuntimeModel):
    operation_id: OperationId
    preflight_id: PreflightId


class RevokeProofScope(RuntimeModel):
    operation_id: OperationId
    scope_id: ScopeId
