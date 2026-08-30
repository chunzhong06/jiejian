# =============================================================================
# 源码变化事实仓储
#
# 定位
#   受控源码快照、Agent 变更声明、真实 diff 与权限影响评估的 SQLite 聚合。
#
# 职责
#   幂等保存不可变快照｜按一次 change 聚合保存路径变化和逐 Intent 影响｜稳定回读最近事实。
#
# 边界
#   不保存源码正文、文本 diff、Git 凭据或每文件/每 Intent 独立行；Repository 不提交事务。
#
# 调用链
#   SourceChangeService → SourceChangeRepository → SQLAlchemy / SQLite
# =============================================================================

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.source_changes import (
    ChangeImpactAssessment,
    ChangeManifest,
    IntentChangeImpact,
    SourceChangeSet,
    SourceFileFingerprint,
    SourceRevisionSnapshot,
)
from product.backend.infra.storage.base import (
    Base,
    _canonical_json,
    _flush,
    _scalar,
    ensure_storage_payload_safe,
)


class SourceRevisionSnapshotRow(Base):
    __tablename__ = "source_revision_snapshots"
    __table_args__ = (
        CheckConstraint("length(snapshot_id) = 36", name="snapshot_id_length"),
        CheckConstraint("length(source_fingerprint) = 64", name="fingerprint_length"),
        CheckConstraint(
            "understanding_revision BETWEEN 0 AND 1000000",
            name="understanding_revision_range",
        ),
        CheckConstraint("length(files_json) BETWEEN 2 AND 1048576", name="files_json_length"),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        UniqueConstraint(
            "project_id",
            "source_fingerprint",
            name="uq_source_revision_project_fingerprint",
        ),
        Index("ix_source_revision_project_created", "project_id", "created_at_us"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    understanding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    files_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ChangeManifestRow(Base):
    __tablename__ = "change_manifests"
    __table_args__ = (
        CheckConstraint("length(change_id) = 36", name="change_id_length"),
        CheckConstraint("length(reason) BETWEEN 1 AND 512", name="reason_length"),
        CheckConstraint(
            "length(claimed_paths_json) BETWEEN 2 AND 131072",
            name="claimed_paths_json_length",
        ),
        CheckConstraint("length(submitted_by) BETWEEN 1 AND 128", name="submitted_by_length"),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_change_manifests_project_created", "project_id", "created_at_us"),
    )

    change_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    claimed_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SourceChangeSetRow(Base):
    __tablename__ = "source_change_sets"
    __table_args__ = (
        CheckConstraint("status IN ('COMPARABLE', 'NO_BASELINE')", name="status_value"),
        CheckConstraint("length(change_fingerprint) = 64", name="fingerprint_length"),
        CheckConstraint("length(added_paths_json) BETWEEN 2 AND 524288", name="added_json_length"),
        CheckConstraint(
            "length(modified_paths_json) BETWEEN 2 AND 524288",
            name="modified_json_length",
        ),
        CheckConstraint(
            "length(removed_paths_json) BETWEEN 2 AND 524288",
            name="removed_json_length",
        ),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
    )

    change_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_manifests.change_id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    previous_snapshot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_revision_snapshots.snapshot_id", ondelete="RESTRICT")
    )
    current_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("source_revision_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    added_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    modified_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    removed_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    change_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ChangeImpactAssessmentRow(Base):
    __tablename__ = "change_impact_assessments"
    __table_args__ = (
        CheckConstraint("length(change_fingerprint) = 64", name="change_fingerprint_length"),
        CheckConstraint("length(reason_codes_json) BETWEEN 2 AND 8192", name="reasons_json_length"),
        CheckConstraint("length(impacts_json) BETWEEN 2 AND 2097152", name="impacts_json_length"),
        CheckConstraint("length(impact_fingerprint) = 64", name="impact_fingerprint_length"),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_change_impacts_project_created", "project_id", "created_at_us"),
    )

    change_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_manifests.change_id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    change_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    impacts_json: Mapped[str] = mapped_column(Text, nullable=False)
    impact_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SourceChangeRepository:
    """一个 change 只保存一行声明、一行真实 diff 和一行影响评估。"""

    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add_snapshot(self, snapshot: SourceRevisionSnapshot) -> None:
        values = snapshot.model_dump(mode="json", exclude={"files"})
        values["files_json"] = _canonical_json(
            [item.model_dump(mode="json") for item in snapshot.files]
        )
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(SourceRevisionSnapshotRow(**values))
        _flush(self._session)

    def snapshot_for_fingerprint(
        self,
        project_id: str,
        fingerprint: str,
    ) -> SourceRevisionSnapshot | None:
        row = _scalar(
            self._session,
            select(SourceRevisionSnapshotRow).where(
                SourceRevisionSnapshotRow.project_id == project_id,
                SourceRevisionSnapshotRow.source_fingerprint == fingerprint,
            ),
        )
        return None if row is None else self._snapshot(row)

    def snapshot(self, snapshot_id: str) -> SourceRevisionSnapshot | None:
        row = _scalar(
            self._session,
            select(SourceRevisionSnapshotRow).where(
                SourceRevisionSnapshotRow.snapshot_id == snapshot_id,
            ),
        )
        return None if row is None else self._snapshot(row)

    def add_change(
        self,
        manifest: ChangeManifest,
        change_set: SourceChangeSet,
        assessment: ChangeImpactAssessment,
    ) -> None:
        if not (
            manifest.change_id == change_set.change_id == assessment.change_id
            and manifest.project_id == change_set.project_id == assessment.project_id
            and change_set.change_fingerprint == assessment.change_fingerprint
        ):
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "代码变化聚合身份不一致")
        manifest_values = manifest.model_dump(mode="json", exclude={"claimed_paths"})
        manifest_values["claimed_paths_json"] = _canonical_json(list(manifest.claimed_paths))
        change_values = change_set.model_dump(
            mode="json",
            exclude={"added_paths", "modified_paths", "removed_paths"},
        )
        change_values["added_paths_json"] = _canonical_json(list(change_set.added_paths))
        change_values["modified_paths_json"] = _canonical_json(list(change_set.modified_paths))
        change_values["removed_paths_json"] = _canonical_json(list(change_set.removed_paths))
        assessment_values = assessment.model_dump(
            mode="json",
            exclude={"reason_codes", "impacts"},
        )
        assessment_values["reason_codes_json"] = _canonical_json(list(assessment.reason_codes))
        assessment_values["impacts_json"] = _canonical_json(
            [item.model_dump(mode="json") for item in assessment.impacts]
        )
        payload = (manifest_values, change_values, assessment_values)
        ensure_storage_payload_safe(payload, self._known_secrets)
        self._session.add(ChangeManifestRow(**manifest_values))
        # 三个聚合 Row 不建立 ORM relationship；先落主行，保持 SQLite 外键顺序。
        _flush(self._session)
        self._session.add(SourceChangeSetRow(**change_values))
        self._session.add(ChangeImpactAssessmentRow(**assessment_values))
        _flush(self._session)

    def manifest(self, change_id: str) -> ChangeManifest | None:
        row = _scalar(
            self._session,
            select(ChangeManifestRow).where(ChangeManifestRow.change_id == change_id),
        )
        return None if row is None else self._manifest(row)

    def change_set(self, change_id: str) -> SourceChangeSet | None:
        row = _scalar(
            self._session,
            select(SourceChangeSetRow).where(SourceChangeSetRow.change_id == change_id),
        )
        return None if row is None else self._change_set(row)

    def assessment(self, change_id: str) -> ChangeImpactAssessment | None:
        row = _scalar(
            self._session,
            select(ChangeImpactAssessmentRow).where(
                ChangeImpactAssessmentRow.change_id == change_id
            ),
        )
        return None if row is None else self._assessment(row)

    def latest_assessment(self, project_id: str) -> ChangeImpactAssessment | None:
        row = _scalar(
            self._session,
            select(ChangeImpactAssessmentRow)
            .where(ChangeImpactAssessmentRow.project_id == project_id)
            .order_by(
                ChangeImpactAssessmentRow.created_at_us.desc(),
                ChangeImpactAssessmentRow.change_id.desc(),
            )
            .limit(1),
        )
        return None if row is None else self._assessment(row)

    @staticmethod
    def _snapshot(row: SourceRevisionSnapshotRow) -> SourceRevisionSnapshot:
        try:
            files = tuple(
                SourceFileFingerprint.model_validate(item, strict=False)
                for item in json.loads(row.files_json)
            )
            return SourceRevisionSnapshot(
                snapshot_id=row.snapshot_id,
                project_id=row.project_id,
                source_fingerprint=row.source_fingerprint,
                understanding_revision=row.understanding_revision,
                files=files,
                created_at_us=row.created_at_us,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "源码版本快照数据损坏") from None

    @staticmethod
    def _manifest(row: ChangeManifestRow) -> ChangeManifest:
        try:
            return ChangeManifest(
                change_id=row.change_id,
                project_id=row.project_id,
                reason=row.reason,
                claimed_paths=tuple(json.loads(row.claimed_paths_json)),
                submitted_by=row.submitted_by,
                created_at_us=row.created_at_us,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "代码变化声明数据损坏") from None

    @staticmethod
    def _change_set(row: SourceChangeSetRow) -> SourceChangeSet:
        try:
            return SourceChangeSet(
                change_id=row.change_id,
                project_id=row.project_id,
                previous_snapshot_id=row.previous_snapshot_id,
                current_snapshot_id=row.current_snapshot_id,
                status=row.status,
                added_paths=tuple(json.loads(row.added_paths_json)),
                modified_paths=tuple(json.loads(row.modified_paths_json)),
                removed_paths=tuple(json.loads(row.removed_paths_json)),
                change_fingerprint=row.change_fingerprint,
                created_at_us=row.created_at_us,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "源码变化集合数据损坏") from None

    @staticmethod
    def _assessment(row: ChangeImpactAssessmentRow) -> ChangeImpactAssessment:
        try:
            impacts = tuple(
                IntentChangeImpact.model_validate(item, strict=False)
                for item in json.loads(row.impacts_json)
            )
            return ChangeImpactAssessment(
                change_id=row.change_id,
                project_id=row.project_id,
                change_fingerprint=row.change_fingerprint,
                complete=row.complete,
                reason_codes=tuple(json.loads(row.reason_codes_json)),
                impacts=impacts,
                impact_fingerprint=row.impact_fingerprint,
                created_at_us=row.created_at_us,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "权限变化影响数据损坏") from None


__all__ = [
    "ChangeImpactAssessmentRow",
    "ChangeManifestRow",
    "SourceChangeRepository",
    "SourceChangeSetRow",
    "SourceRevisionSnapshotRow",
]
