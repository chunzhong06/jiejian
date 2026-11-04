"""不可变试运行授权与fence关联报告；调度生命周期由Jobs拥有。"""
from sqlalchemy import String, Text, BigInteger, ForeignKey, select
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.infrastructure.storage.base import Base,_flush,ensure_storage_payload_safe
from product.protocols.preparation.flow_trial import FlowTrialRequest,FlowTrialReport


class FlowTrialRow(Base):
    __tablename__='flow_trials'
    trial_id: Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id: Mapped[str]=mapped_column(ForeignKey('projects.project_id',ondelete='RESTRICT'),nullable=False)
    request_json: Mapped[str]=mapped_column(Text,nullable=False)
    report_json: Mapped[str|None]=mapped_column(Text)
    created_at_us: Mapped[int]=mapped_column(BigInteger,nullable=False)


class FlowTrialRepository:
    def __init__(self,session,known_secrets):
        self._session,self._secrets=session,known_secrets

    def get(self,project_id,trial_id):
        row=self._session.get(FlowTrialRow,trial_id)
        if row is None or row.project_id!=project_id:return None
        return FlowTrialRequest.model_validate_json(row.request_json,strict=True)

    def report(self,project_id,trial_id):
        row=self._session.get(FlowTrialRow,trial_id)
        if row is None or row.project_id!=project_id or row.report_json is None:return None
        return FlowTrialReport.model_validate_json(row.report_json,strict=True)

    def list(self,project_id):
        rows=self._session.scalars(select(FlowTrialRow).where(FlowTrialRow.project_id==project_id).order_by(FlowTrialRow.created_at_us.desc())).all()
        return tuple(FlowTrialRequest.model_validate_json(row.request_json,strict=True) for row in rows)

    def add(self,request):
        ensure_storage_payload_safe(request.model_dump(mode='json'),self._secrets)
        self._session.add(FlowTrialRow(trial_id=request.trial_id,project_id=request.plan.flow.project_id,
            request_json=request.model_dump_json(),created_at_us=request.created_at_us))
        _flush(self._session)

    def publish(self,report):
        ensure_storage_payload_safe(report.model_dump(mode='json'),self._secrets)
        row=self._session.get(FlowTrialRow,report.trial_id)
        if row.report_json is not None:
            return FlowTrialReport.model_validate_json(row.report_json,strict=True)==report
        row.report_json=report.model_dump_json()
        _flush(self._session)
        return True
