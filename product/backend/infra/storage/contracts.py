# Storage 的 SQLAlchemy typed declarative 映射。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infra.storage.base import Base

class RequirementRow(Base):
    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint("schema_version = '1'", name="schema_version_value"),
        CheckConstraint(
            "source_type IN ('requirement_text', 'project_config', 'recording_flow', "
            "'static_analysis', 'llm')",
            name="source_type_value",
        ),
        CheckConstraint(
            "length(requirement_id) = 36 AND substr(requirement_id, 1, 4) = 'req_' "
            "AND substr(requirement_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="requirement_id_format",
        ),
        CheckConstraint("length(source_locator) BETWEEN 1 AND 1024", name="source_locator_length"),
        CheckConstraint(
            "length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="source_sha256_format",
        ),
        CheckConstraint("length(requirement_text) BETWEEN 1 AND 16384", name="text_length"),
        CheckConstraint("length(security_tags_json) BETWEEN 2 AND 8192", name="tags_json_length"),
        CheckConstraint("length(created_by) BETWEEN 1 AND 128", name="created_by_length"),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_requirements_project_created", "project_id", "created_at_us"),
    )

    requirement_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    security_tags_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
class ContractCandidateRow(Base):
    __tablename__ = "contract_candidates"
    __table_args__ = (
        CheckConstraint("schema_version = '1'", name="schema_version_value"),
        CheckConstraint(
            "source_type IN ('requirement_text', 'project_config', 'recording_flow', "
            "'static_analysis', 'llm')",
            name="source_type_value",
        ),
        CheckConstraint(
            "length(candidate_id) = 37 AND substr(candidate_id, 1, 5) = 'cand_' "
            "AND substr(candidate_id, 6) NOT GLOB '*[^0-9a-f]*'",
            name="candidate_id_format",
        ),
        CheckConstraint("length(source_locator) BETWEEN 1 AND 1024", name="source_locator_length"),
        CheckConstraint(
            "length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="source_sha256_format",
        ),
        CheckConstraint("length(rule_json) BETWEEN 2 AND 65536", name="rule_json_length"),
        CheckConstraint("length(requirement_ids_json) BETWEEN 2 AND 65536", name="requirement_ids_json_length"),
        CheckConstraint("length(created_by) BETWEEN 1 AND 128", name="created_by_length"),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_contract_candidates_project_created", "project_id", "created_at_us"),
    )

    candidate_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_json: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    llm_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
class ContractVersionRow(Base):
    __tablename__ = "contract_versions"
    __table_args__ = (
        CheckConstraint("schema_version = '1'", name="schema_version_value"),

        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "status IN ('DRAFT', 'REVIEW', 'ACTIVE', 'SUPERSEDED', 'REJECTED')",
            name="status_value",
        ),
        CheckConstraint("length(contract_id) BETWEEN 1 AND 128", name="contract_id_length"),
        CheckConstraint("length(snapshot_json) BETWEEN 2 AND 1048576", name="snapshot_json_length"),
        CheckConstraint("length(provenance_json) BETWEEN 2 AND 1048576", name="provenance_json_length"),
        CheckConstraint("length(audit_json) BETWEEN 2 AND 131072", name="audit_json_length"),
        CheckConstraint(
            "(version = 1 AND supersedes_version IS NULL) OR "
            "(version > 1 AND supersedes_version = version - 1)",
            name="supersedes_version_order",
        ),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="time_order",
        ),
        Index("ix_contract_versions_project_status", "project_id", "status", "updated_at_us"),
        Index(
            "uq_contract_versions_active",
            "project_id",
            "contract_id",
            unique=True,
            sqlite_where=sql_text("status = 'ACTIVE'"),
        ),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True
    )
    contract_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes_version: Mapped[int | None] = mapped_column(Integer)
    audit_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)

# 本聚合的 Repository 与持久化记录边界。

# =============================================================================
# Contract 聚合仓储
#
# 定位
#   Requirement、Candidate、ContractVersion 与项目绑定的持久化适配器
#
# 职责
#   映射治理记录｜保持版本与来源字段｜提供 Contract 聚合查询
#
# 调用链
#   Contract services → Contract repositories → Contract ORM rows
# =============================================================================

import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from product.backend.core.identifiers import EVIDENCE_ID_PATTERN, JOB_ID_PATTERN, PROJECT_ID_PATTERN, RECORDING_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN
from product.backend.core.contracts.models import ContractAuditEntry, ContractCandidate, ContractProvenance, ContractSourceType, ContractVersion, LLMGenerationMetadata, Requirement, SourceReference
from product.backend.core.lifecycle import JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.contracts.models import CandidateSuggestion
from product.backend.core.verification.permissions import PermissionContract, parse_permission_contract
from product.backend.core.recording import Recording, RecordingState, RecordingStateEvent, RecordingTerminalState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import STAGED_ARTIFACT_MAX_BYTES, FlowDraft, RecordingEventKind, RecordingEvent, RecordingHeader, StagedArtifact, canonical_flow_draft_json_bytes
from product.backend.infra.storage.evidence import EvidenceIndexRow
from product.backend.infra.storage.recordings import FlowDraftRevisionRow, RecordingRow
from product.backend.infra.storage.jobs import JobEventRow, JobRow
from product.backend.infra.storage.projects import ProjectRow
from product.backend.infra.storage.runs import RunRow
from product.backend.infra.storage.base import MetadataValue, StorageRecord, _METADATA_KEY, _SENSITIVE_METADATA_KEY, _canonical_json, _flush, _scalar, _scalars, ensure_storage_payload_safe

class RequirementRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, requirement: Requirement) -> None:
        ensure_storage_payload_safe(
            requirement.model_dump(mode="json"), self._known_secrets
        )
        self._session.add(
            RequirementRow(
                requirement_id=requirement.requirement_id,
                schema_version="1",
                project_id=requirement.project_id,
                source_type=requirement.source.source_type.value,
                source_locator=requirement.source.locator,
                source_sha256=requirement.source.content_sha256,
                requirement_text=requirement.text,
                security_tags_json=_canonical_json(requirement.security_tags),
                created_by=requirement.created_by,
                created_at_us=requirement.created_at_us,
            )
        )
        _flush(self._session)

    def get(self, requirement_id: str) -> Requirement | None:
        row = _scalar(
            self._session,
            select(RequirementRow).where(RequirementRow.requirement_id == requirement_id),
        )
        return None if row is None else self._record(row)

    def list_for_project(self, project_id: str) -> tuple[Requirement, ...]:
        rows = _scalars(
            self._session,
            select(RequirementRow)
            .where(RequirementRow.project_id == project_id)
            .order_by(RequirementRow.created_at_us, RequirementRow.requirement_id),
        )
        return tuple(self._record(row) for row in rows)

    @staticmethod
    def _record(row: RequirementRow) -> Requirement:
        return Requirement(
            requirement_id=row.requirement_id,
            project_id=row.project_id,
            source=SourceReference(
                source_type=ContractSourceType(row.source_type),
                locator=row.source_locator,
                content_sha256=row.source_sha256,
            ),
            text=row.requirement_text,
            security_tags=tuple(json.loads(row.security_tags_json)),
            created_by=row.created_by,
            created_at_us=row.created_at_us,
        )
class ContractCandidateRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, candidate: ContractCandidate) -> None:

        ensure_storage_payload_safe(candidate.model_dump(mode="json"), self._known_secrets)
        self._session.add(
            ContractCandidateRow(
                candidate_id=candidate.candidate_id,
                schema_version="1",
                project_id=candidate.project_id,
                source_type=candidate.source.source_type.value,
                source_locator=candidate.source.locator,
                source_sha256=candidate.source.content_sha256,
                rule_json=_canonical_json(candidate.suggestion.model_dump(mode="json")),
                requirement_ids_json=_canonical_json(candidate.requirement_ids),
                llm_metadata_json=(
                    _canonical_json(candidate.llm_metadata.model_dump(mode="json"))
                    if candidate.llm_metadata is not None
                    else None
                ),
                created_by=candidate.created_by,
                created_at_us=candidate.created_at_us,
            )
        )
        _flush(self._session)

    def get(self, candidate_id: str) -> ContractCandidate | None:
        row = _scalar(
            self._session,
            select(ContractCandidateRow).where(ContractCandidateRow.candidate_id == candidate_id),
        )
        return None if row is None else self._record(row)

    def list_for_project(self, project_id: str) -> tuple[ContractCandidate, ...]:
        rows = _scalars(
            self._session,
            select(ContractCandidateRow)
            .where(ContractCandidateRow.project_id == project_id)
            .order_by(ContractCandidateRow.created_at_us, ContractCandidateRow.candidate_id),
        )
        return tuple(self._record(row) for row in rows)

    @staticmethod
    def _record(row: ContractCandidateRow) -> ContractCandidate:
        return ContractCandidate(
            candidate_id=row.candidate_id,
            project_id=row.project_id,
            source=SourceReference(
                source_type=ContractSourceType(row.source_type),
                locator=row.source_locator,
                content_sha256=row.source_sha256,
            ),
            suggestion=CandidateSuggestion.model_validate_json(row.rule_json),
            requirement_ids=tuple(json.loads(row.requirement_ids_json)),
            created_by=row.created_by,
            created_at_us=row.created_at_us,
            llm_metadata=(
                LLMGenerationMetadata.model_validate_json(row.llm_metadata_json)
                if row.llm_metadata_json is not None
                else None
            ),
        )
class ContractVersionRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, contract: ContractVersion) -> None:
        ensure_storage_payload_safe(contract.model_dump(mode="json"), self._known_secrets)
        self._session.add(
            ContractVersionRow(
                project_id=contract.project_id,
                contract_id=contract.contract_id,
                version=contract.version,
                schema_version="1",
                status=contract.status.value,
                snapshot_json=_canonical_json(contract.snapshot.model_dump(mode="json")),
                provenance_json=_canonical_json(contract.provenance.model_dump(mode="json")),
                supersedes_version=contract.supersedes_version,
                audit_json=_canonical_json(
                    [entry.model_dump(mode="json") for entry in contract.audit]
                ),
                created_at_us=contract.created_at_us,
                updated_at_us=contract.updated_at_us,
            )
        )
        _flush(self._session)

    def get(self, project_id: str, contract_id: str, version: int) -> ContractVersion | None:
        row = _scalar(
            self._session,
            select(ContractVersionRow).where(
                ContractVersionRow.project_id == project_id,
                ContractVersionRow.contract_id == contract_id,
                ContractVersionRow.version == version,
            ),
        )
        return None if row is None else self._record(row)

    def get_active(self, project_id: str, contract_id: str) -> ContractVersion | None:
        row = _scalar(

            self._session,
            select(ContractVersionRow).where(
                ContractVersionRow.project_id == project_id,
                ContractVersionRow.contract_id == contract_id,
                ContractVersionRow.status == ContractStatus.ACTIVE.value,
            ),
        )
        return None if row is None else self._record(row)

    def list_for_contract(self, project_id: str, contract_id: str) -> tuple[ContractVersion, ...]:
        rows = _scalars(
            self._session,
            select(ContractVersionRow)
            .where(
                ContractVersionRow.project_id == project_id,
                ContractVersionRow.contract_id == contract_id,
            )
            .order_by(ContractVersionRow.version),
        )
        return tuple(self._record(row) for row in rows)

    def list_for_project(self, project_id: str) -> tuple[ContractVersion, ...]:
        rows = _scalars(
            self._session,
            select(ContractVersionRow)
            .where(ContractVersionRow.project_id == project_id)
            .order_by(ContractVersionRow.contract_id, ContractVersionRow.version),
        )
        return tuple(self._record(row) for row in rows)

    def replace(self, contract: ContractVersion) -> None:
        ensure_storage_payload_safe(contract.model_dump(mode="json"), self._known_secrets)
        row = _scalar(
            self._session,
            select(ContractVersionRow).where(
                ContractVersionRow.project_id == contract.project_id,
                ContractVersionRow.contract_id == contract.contract_id,
                ContractVersionRow.version == contract.version,
            ),
        )
        if row is None:
            raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
        current = self._record(row)
        allowed = {
            ContractStatus.DRAFT: {ContractStatus.REVIEW},
            ContractStatus.REVIEW: {ContractStatus.ACTIVE, ContractStatus.REJECTED},
            ContractStatus.ACTIVE: {ContractStatus.SUPERSEDED},
        }
        if contract.status not in allowed.get(current.status, set()):
            code = (
                ErrorCode.CONTRACT_IMMUTABLE
                if current.status in {ContractStatus.ACTIVE, ContractStatus.SUPERSEDED}
                else ErrorCode.STATE_INVALID_TRANSITION
            )
            raise JiejianError(code, "契约版本不能原地修改")
        if (
            contract.snapshot != current.snapshot
            or contract.provenance != current.provenance
            or contract.supersedes_version != current.supersedes_version
            or contract.created_at_us != current.created_at_us
            or contract.audit[:-1] != current.audit
        ):
            raise JiejianError(ErrorCode.CONTRACT_IMMUTABLE, "状态转换不能改写契约正文")
        row.status = contract.status.value
        row.snapshot_json = _canonical_json(contract.snapshot.model_dump(mode="json"))
        row.audit_json = _canonical_json(
            [entry.model_dump(mode="json") for entry in contract.audit]
        )
        row.updated_at_us = contract.updated_at_us
        _flush(self._session)

    @staticmethod
    def _record(row: ContractVersionRow) -> ContractVersion:
        return ContractVersion(
            project_id=row.project_id,
            contract_id=row.contract_id,
            version=row.version,
            status=ContractStatus(row.status),
            snapshot=parse_permission_contract(row.snapshot_json),
            provenance=ContractProvenance.model_validate_json(row.provenance_json),
            supersedes_version=row.supersedes_version,
            audit=tuple(
                ContractAuditEntry.model_validate_json(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                )
                for item in json.loads(row.audit_json)
            ),
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
        )
