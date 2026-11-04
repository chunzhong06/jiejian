"""接口资料修订及人工关联分开保存，重新导入不覆盖人工工作。"""
from sqlalchemy import ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.infrastructure.storage.base import Base, _flush, ensure_storage_payload_safe
from product.protocols.preparation.api_source import ApiSourceDocument, ApiImportDocument, parse_source_document
from product.backend.domain.errors import ErrorCode,JiejianError


class ApiSourceRow(Base):
    __tablename__ = 'api_sources'
    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.project_id', ondelete='RESTRICT'), index=True)
    payload: Mapped[str] = mapped_column(Text)


class SourceAnnotationRow(Base):
    __tablename__ = 'api_source_annotations'
    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.project_id', ondelete='RESTRICT'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)


class ApiImportRow(Base):
    __tablename__ = 'api_source_imports'
    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.project_id', ondelete='RESTRICT'), index=True)
    payload: Mapped[str] = mapped_column(Text)


class ApiSourceRepository:
    def __init__(self, session, known_secrets):
        self._session, self._secrets = session, known_secrets

    def import_document(self, project_id, candidate_id):
        row = self._session.get(ApiImportRow, candidate_id)
        return None if row is None or row.project_id != project_id else self._document(row,ApiImportDocument)

    @staticmethod
    def _document(row,model):
        try:
            document=parse_source_document(row.payload,model)
            identity=(document.project_id,document.candidate_id) if model is ApiImportDocument else (document.project_id,document.source_id,document.revision)
            expected=(row.project_id,row.candidate_id) if model is ApiImportDocument else (row.project_id,row.source_id,row.revision)
            if identity!=expected:
                raise ValueError('source index mismatch')
            return document
        except ValueError:
            raise JiejianError(ErrorCode.STORAGE_STATE,'接口来源修订无法读取或与索引不符') from None

    def add_import(self, document):
        ensure_storage_payload_safe(document.model_dump(mode='json'), self._secrets)
        self._session.add(ApiImportRow(candidate_id=document.candidate_id, project_id=document.project_id, payload=document.model_dump_json()))
        _flush(self._session)

    def revisions(self, project_id):
        rows = self._session.scalars(select(ApiSourceRow).where(ApiSourceRow.project_id == project_id)
            .order_by(ApiSourceRow.source_id, ApiSourceRow.revision.desc())).all()
        return tuple(self._document(row,ApiSourceDocument) for row in rows)

    def latest(self, project_id, source_id=None):
        # 目录只接受每个来源实际消费的最新修订；历史读取仍单独严格接受。
        revisions = select(ApiSourceRow.source_id, func.max(ApiSourceRow.revision).label('revision')).where(
            ApiSourceRow.project_id == project_id)
        if source_id is not None:
            revisions = revisions.where(ApiSourceRow.source_id == source_id)
        latest = revisions.group_by(ApiSourceRow.source_id).subquery()
        query = select(ApiSourceRow).join(latest, (ApiSourceRow.source_id == latest.c.source_id) &
            (ApiSourceRow.revision == latest.c.revision)).where(ApiSourceRow.project_id == project_id)
        return tuple(self._document(row, ApiSourceDocument) for row in
            self._session.scalars(query.order_by(ApiSourceRow.source_id)))

    def revision(self, project_id, source_id, revision):
        row = self._session.get(ApiSourceRow, (source_id, revision))
        return None if row is None or row.project_id != project_id else self._document(row, ApiSourceDocument)

    def add(self, document):
        ensure_storage_payload_safe(document.model_dump(mode='json'), self._secrets)
        self._session.add(ApiSourceRow(source_id=document.source_id, revision=document.revision,
            project_id=document.project_id, payload=document.model_dump_json()))
        _flush(self._session)

    def annotations(self, project_id):
        import json
        return tuple(json.loads(row.payload) for row in self._session.scalars(
            select(SourceAnnotationRow).where(SourceAnnotationRow.project_id == project_id)).all())

    def annotate(self, project_id, source_id, item_id, values):
        import json
        ensure_storage_payload_safe(values, self._secrets)
        row = self._session.get(SourceAnnotationRow, (source_id, item_id))
        if row is None:
            row = SourceAnnotationRow(project_id=project_id, source_id=source_id, item_id=item_id)
            self._session.add(row)
        row.revision, row.payload = values['revision'], json.dumps(values, ensure_ascii=False, allow_nan=False)
        _flush(self._session)
