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

from __future__ import annotations

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

from ...domain.identifiers import (
    EVIDENCE_ID_PATTERN,
    JOB_ID_PATTERN,
    PROJECT_ID_PATTERN,
    RECORDING_ID_PATTERN,
    RUN_ID_PATTERN,
    SHA256_PATTERN,
)
from ...contracts.models import (
    ContractAuditEntry,
    ContractCandidate,
    ContractProvenance,
    ContractSourceType,
    ContractVersion,
    LLMGenerationMetadata,
    Requirement,
    SourceReference,
)
from ...domain.lifecycle import JobState, ProjectStatus, RunLifecycle, RunVerdict
from ...domain.lifecycle import ContractStatus
from ...verification.models import ContractRule, SecurityContract
from ...recording.models import (
    Recording,
    RecordingState,
    RecordingStateEvent,
    RecordingTerminalState,
)
from ...errors import ErrorCode, JiejianError
from ...protocols import (
    STAGED_ARTIFACT_MAX_BYTES,
    FlowDraftV1,
    RecordingEventKind,
    RecordingEventV1,
    RecordingHeaderV1,
    StagedArtifactV1,
    canonical_flow_draft_json_bytes,
)
from ..models import (
    ContractCandidateRow,
    ContractVersionRow,
    EvidenceIndexRow,
    FlowDraftRevisionRow,
    JobEventRow,
    JobRow,
    ProjectRow,
    RequirementRow,
    RecordingRow,
    RunRow,
)
from .base import (
    MetadataValue,
    StorageRecord,
    _METADATA_KEY,
    _SENSITIVE_METADATA_KEY,
    _canonical_json,
    _flush,
    _scalar,
    _scalars,
    ensure_storage_payload_safe,
)

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
                schema_version=requirement.schema_version,
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
            schema_version=row.schema_version,
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
                schema_version=candidate.schema_version,
                project_id=candidate.project_id,
                source_type=candidate.source.source_type.value,
                source_locator=candidate.source.locator,
                source_sha256=candidate.source.content_sha256,
                rule_json=_canonical_json(candidate.rule.model_dump(mode="json")),
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
            schema_version=row.schema_version,
            candidate_id=row.candidate_id,
            project_id=row.project_id,
            source=SourceReference(
                source_type=ContractSourceType(row.source_type),
                locator=row.source_locator,
                content_sha256=row.source_sha256,
            ),
            rule=ContractRule.model_validate_json(row.rule_json),
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
                schema_version=contract.schema_version,
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
            contract.snapshot.rules != current.snapshot.rules
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
            schema_version=row.schema_version,
            project_id=row.project_id,
            contract_id=row.contract_id,
            version=row.version,
            status=ContractStatus(row.status),
            snapshot=SecurityContract.model_validate_json(row.snapshot_json),
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
