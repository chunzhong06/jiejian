"""场景修订仓储；执行结果仍由既有 Run/Job 和不可变检查包拥有。"""
from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.infrastructure.storage.base import Base, _flush, ensure_storage_payload_safe
from product.protocols.checks.scenarios import BusinessScenarioRevision


class BusinessScenarioRow(Base):
    __tablename__='business_scenarios'
    scenario_id: Mapped[str]=mapped_column(String(36),primary_key=True)
    revision: Mapped[int]=mapped_column(Integer,primary_key=True)
    project_id: Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'),index=True)
    payload_json: Mapped[str]=mapped_column(Text)
    created_at_us: Mapped[int]=mapped_column(BigInteger)
    reviewed_at_us: Mapped[int|None]=mapped_column(BigInteger)


class BusinessScenarioRepository:
    def __init__(self,session,known_secrets):
        self._session,self._secrets=session,known_secrets

    def get(self,project_id,scenario_id,revision):
        row=self._session.get(BusinessScenarioRow,(scenario_id,revision))
        return None if row is None or row.project_id!=project_id else BusinessScenarioRevision.model_validate_json(row.payload_json)

    def current(self,project_id,scenario_id):
        row=self._session.scalar(select(BusinessScenarioRow).where(
            BusinessScenarioRow.project_id==project_id,BusinessScenarioRow.scenario_id==scenario_id)
            .order_by(BusinessScenarioRow.revision.desc()).limit(1))
        return None if row is None else BusinessScenarioRevision.model_validate_json(row.payload_json)

    def summaries(self,project_id):
        """目录只投影摘要；准确正文仍经 get/current 的完整协议读取。"""
        from sqlalchemy import func
        latest=select(BusinessScenarioRow.scenario_id,func.max(BusinessScenarioRow.revision).label('revision')).where(
            BusinessScenarioRow.project_id==project_id).group_by(BusinessScenarioRow.scenario_id).subquery()
        rows=self._session.execute(select(BusinessScenarioRow.scenario_id,BusinessScenarioRow.revision,
            func.json_extract(BusinessScenarioRow.payload_json,'$.label'),
            func.json_extract(BusinessScenarioRow.payload_json,'$.description'),
            func.json_array_length(BusinessScenarioRow.payload_json,'$.experiments')).join(latest,
            (BusinessScenarioRow.scenario_id==latest.c.scenario_id)&(BusinessScenarioRow.revision==latest.c.revision))
            .order_by(BusinessScenarioRow.created_at_us.desc(),BusinessScenarioRow.scenario_id).limit(128))
        return tuple(dict(id=key,revision=revision,label=label,description=description or '',experiment_count=count)
            for key,revision,label,description,count in rows)

    def latest(self,project_id):
        # 先在 SQL 限定最新修订，避免解析每份历史文档。
        from sqlalchemy import func
        latest=select(BusinessScenarioRow.scenario_id,func.max(BusinessScenarioRow.revision).label('revision')).where(
            BusinessScenarioRow.project_id==project_id).group_by(BusinessScenarioRow.scenario_id).subquery()
        rows=self._session.scalars(select(BusinessScenarioRow).join(latest,
            (BusinessScenarioRow.scenario_id==latest.c.scenario_id)&(BusinessScenarioRow.revision==latest.c.revision))
            .order_by(BusinessScenarioRow.created_at_us.desc(),BusinessScenarioRow.scenario_id).limit(128))
        return tuple(BusinessScenarioRevision.model_validate_json(row.payload_json) for row in rows)

    def add(self,document,now,*,reviewed=False):
        ensure_storage_payload_safe(document.model_dump(mode='json'),self._secrets)
        self._session.add(BusinessScenarioRow(scenario_id=document.id,revision=document.revision,
            project_id=document.project_id,payload_json=document.model_dump_json(),created_at_us=now,reviewed_at_us=now if reviewed else None))
        _flush(self._session)

    def reviewed_revision(self,project_id,scenario_id):
        from sqlalchemy import func
        return self._session.scalar(select(func.max(BusinessScenarioRow.revision)).where(
            BusinessScenarioRow.project_id==project_id,BusinessScenarioRow.scenario_id==scenario_id,
            BusinessScenarioRow.reviewed_at_us.is_not(None))) or 0

    def mark_reviewed(self,project_id,scenario_id,revision,now):
        row=self._session.get(BusinessScenarioRow,(scenario_id,revision))
        if row is None or row.project_id!=project_id:
            raise ValueError('scenario revision not found')
        if row.reviewed_at_us is None:
            row.reviewed_at_us=now
            _flush(self._session)

    def is_reviewed(self,project_id,scenario_id,revision):
        row=self._session.get(BusinessScenarioRow,(scenario_id,revision))
        return row is not None and row.project_id==project_id and row.reviewed_at_us is not None
