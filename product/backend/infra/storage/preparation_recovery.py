# 保存材料操作回执与有限界面草稿；写入和正式绑定共用调用者事务。
import json

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, Text, update
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import Base, _flush, ensure_storage_payload_safe


class PreparationReceiptRow(Base):
    __tablename__ = "preparation_receipts"
    operation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at_us: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[str] = mapped_column(Text)


class PreparationDraftRow(Base):
    __tablename__ = "preparation_drafts"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision"),)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[str] = mapped_column(Text)


class PreparationCandidateRecordingRow(Base):
    __tablename__ = "preparation_candidate_recordings"
    recording_id: Mapped[str] = mapped_column(String(36), ForeignKey("recordings.recording_id", ondelete="RESTRICT"), primary_key=True)


class PreparationRecoveryRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def mark_candidate_recording(self, recording_id):
        self._session.add(PreparationCandidateRecordingRow(recording_id=recording_id))
        _flush(self._session)

    def candidate_recording(self, recording_id):
        return self._session.get(PreparationCandidateRecordingRow, recording_id) is not None

    def receipt(self, operation_id):
        row = self._session.get(PreparationReceiptRow, operation_id)
        return None if row is None else json.loads(row.payload)

    def add_receipt(self, value):
        ensure_storage_payload_safe(value, self._secrets)
        self._session.add(PreparationReceiptRow(operation_id=value["operation_id"],
            project_id=value["project_id"], request_fingerprint=value["request_fingerprint"],
            created_at_us=value["created_at_us"], payload=json.dumps(value, ensure_ascii=False)))
        _flush(self._session)

    def draft(self, project_id):
        row = self._session.get(PreparationDraftRow, project_id)
        return None if row is None else json.loads(row.payload)

    def save_draft(self, project_id, draft):
        expected_revision = draft["revision"]
        value = {**draft, "revision": expected_revision + 1}
        ensure_storage_payload_safe(value, self._secrets)
        payload = json.dumps(value, ensure_ascii=False)
        if expected_revision == 0:
            self._session.add(PreparationDraftRow(project_id=project_id, revision=1, payload=payload))
            _flush(self._session)
        else:
            result = self._session.execute(update(PreparationDraftRow).where(
                PreparationDraftRow.project_id == project_id,
                PreparationDraftRow.revision == expected_revision).values(revision=expected_revision + 1, payload=payload))
            if result.rowcount != 1:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "另一个页面已保存准备位置，请重新读取后继续")
        return value
