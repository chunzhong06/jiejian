# 补充材料的追加修订与幂等收据；不保存 Evidence，不参与执行或判定。
from __future__ import annotations

import json
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.infra.storage.base import Base, _canonical_json, _flush, ensure_storage_payload_safe


class SupplementalMaterialRevisionRow(Base):
    __tablename__ = "supplemental_material_revisions"
    __table_args__ = (
        ForeignKeyConstraint(["action_id", "action_revision"], ["business_action_revisions.action_id", "business_action_revisions.revision"], ondelete="RESTRICT"),
        CheckConstraint("revision >= 1 AND action_revision >= 1", name="revision_positive"),
        CheckConstraint("length(document_json) <= 65536 AND length(fingerprint) = 64", name="document_bound"),
        CheckConstraint("received_at_us >= 0 AND updated_at_us >= received_at_us", name="time_order"),
        Index("ix_supplemental_material_project_action", "project_id", "action_id", "updated_at_us"),
    )
    material_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"))
    action_id: Mapped[str] = mapped_column(String(36))
    action_revision: Mapped[int] = mapped_column(Integer)
    document_json: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    received_at_us: Mapped[int] = mapped_column(BigInteger)
    updated_at_us: Mapped[int] = mapped_column(BigInteger)
    withdrawn: Mapped[bool] = mapped_column(Boolean)


class SupplementalMaterialReceiptRow(Base):
    __tablename__ = "supplemental_material_receipts"
    __table_args__ = (
        ForeignKeyConstraint(["material_id", "revision"], ["supplemental_material_revisions.material_id", "supplemental_material_revisions.revision"], ondelete="RESTRICT"),
        CheckConstraint("length(content_fingerprint) = 64", name="fingerprint_length"),
    )
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    material_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)


class SupplementalMaterialRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def get(self, material_id, revision=None):
        query = select(SupplementalMaterialRevisionRow).where(SupplementalMaterialRevisionRow.material_id == material_id)
        if revision is not None:
            query = query.where(SupplementalMaterialRevisionRow.revision == revision)
        row = self._session.scalar(query.order_by(SupplementalMaterialRevisionRow.revision.desc()).limit(1))
        return None if row is None else self._view(row)

    def receipt(self, project_id, request_id):
        row = self._session.get(SupplementalMaterialReceiptRow, (project_id, request_id))
        return None if row is None else (row.content_fingerprint, self.get(row.material_id, row.revision))

    def add(self, value, *, request_id, content_fingerprint):
        ensure_storage_payload_safe(value, self._secrets)
        document = {key: value[key] for key in ("project_id", "action_id", "action_revision", "title", "source_label", "claimed_resource_label", "records")}
        document["schema_version"] = "1"
        self._session.add(SupplementalMaterialRevisionRow(**{key: value[key] for key in ("material_id", "revision", "project_id", "action_id", "action_revision", "fingerprint", "received_at_us", "updated_at_us", "withdrawn")}, document_json=_canonical_json(document)))
        _flush(self._session)
        self._session.add(SupplementalMaterialReceiptRow(project_id=value["project_id"], request_id=request_id,
            content_fingerprint=content_fingerprint, material_id=value["material_id"], revision=value["revision"]))
        _flush(self._session)

    def list(self, project_id, action_id, *, material_id=None, limit=100, before_revision=None):
        row = SupplementalMaterialRevisionRow
        query = select(row).where(row.project_id == project_id, row.action_id == action_id)
        if material_id is not None:
            query = query.where(row.material_id == material_id).order_by(row.revision.desc())
            if before_revision is not None:
                query = query.where(row.revision < before_revision)
        else:
            latest = select(row.material_id, func.max(row.revision).label("revision")).group_by(row.material_id).subquery()
            query = query.join(latest, (row.material_id == latest.c.material_id) & (row.revision == latest.c.revision)).order_by(row.updated_at_us.desc(), row.material_id)
        values = [self._view(item) for item in self._session.scalars(query.limit(limit + 1))]
        return values[:limit], len(values) > limit

    @staticmethod
    def _view(row):
        document = json.loads(row.document_json)
        document.pop("schema_version")
        return dict(document, material_id=row.material_id, revision=row.revision, fingerprint=row.fingerprint,
            received_at_us=row.received_at_us, updated_at_us=row.updated_at_us, withdrawn=row.withdrawn,
            record_count=len(document["records"]), association_status="USER_DECLARED" if document["claimed_resource_label"] else "UNCONFIRMED", usage="SUPPLEMENTAL_ONLY")
