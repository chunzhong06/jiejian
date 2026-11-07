from sqlalchemy import String,Integer,Text,BigInteger,ForeignKey,select,func,and_
from sqlalchemy.orm import Mapped,mapped_column
from product.backend.infrastructure.storage.base import Base,_flush,ensure_storage_payload_safe
from product.protocols.preparation.operation_flow import OperationFlow


class OperationFlowRow(Base):
    __tablename__='operation_flow_revisions'
    flow_id: Mapped[str]=mapped_column(String(36),primary_key=True)
    revision: Mapped[int]=mapped_column(Integer,primary_key=True)
    project_id: Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'),nullable=False)
    payload_json: Mapped[str]=mapped_column(Text,nullable=False)
    created_at_us: Mapped[int]=mapped_column(BigInteger,nullable=False)
    adopted_at_us: Mapped[int|None]=mapped_column(BigInteger)


class OperationFlowRepository:
    def __init__(self,session,known_secrets):
        self._session,self._secrets=session,known_secrets

    def get(self,flow_id,revision):
        row=self._session.get(OperationFlowRow,(flow_id,revision))
        return None if row is None else OperationFlow.model_validate_json(row.payload_json,strict=True)

    def latest(self,project_id):
        revisions=select(OperationFlowRow.flow_id,func.max(OperationFlowRow.revision).label('revision')).where(
            OperationFlowRow.project_id==project_id).group_by(OperationFlowRow.flow_id).subquery()
        rows=self._session.scalars(select(OperationFlowRow).join(revisions,and_(
            OperationFlowRow.flow_id==revisions.c.flow_id,OperationFlowRow.revision==revisions.c.revision))
            .where(OperationFlowRow.project_id==project_id)
            .order_by(OperationFlowRow.created_at_us.desc(),OperationFlowRow.flow_id))
        return [dict(document=OperationFlow.model_validate_json(row.payload_json,strict=True),
            adopted=row.adopted_at_us is not None) for row in rows]

    def latest_revision(self,project_id,flow_id):
        row=self._session.scalars(select(OperationFlowRow).where(OperationFlowRow.project_id==project_id,
            OperationFlowRow.flow_id==flow_id).order_by(OperationFlowRow.revision.desc()).limit(1)).first()
        return None if row is None else OperationFlow.model_validate_json(row.payload_json,strict=True)

    def add(self,document,now):
        ensure_storage_payload_safe(document.model_dump(mode='json'),self._secrets)
        self._session.add(OperationFlowRow(flow_id=document.id,revision=document.revision,project_id=document.project_id,payload_json=document.model_dump_json(),created_at_us=now))
        _flush(self._session)

    def adopt(self,flow_id,revision,now):
        row=self._session.get(OperationFlowRow,(flow_id,revision))
        row.adopted_at_us=now
        _flush(self._session)

    def adopted(self,flow_id,revision):
        row=self._session.get(OperationFlowRow,(flow_id,revision))
        return row is not None and row.adopted_at_us is not None
